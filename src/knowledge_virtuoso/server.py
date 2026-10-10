#!/usr/bin/env python3
"""
knowledge_virtuoso.server — MCP Server: SKILL 函数知识库查询服务。

提供 tool:

 函数查询 (virtuoso_skill_language):
  skill_language_search_doc         — 查询函数签名（detail=signature/brief/full 控制粒度）
  skill_language_search_components  — 按前缀+关键词组合搜索函数名（推荐）

 设计库对象属性查询 (virtuoso_db):
  db_search_attr        — 按 objType + 关键词搜索属性

 tech 数据库对象属性查询 (virtuoso_techdb):
  techdb_search_attr         — 按类 + 关键词搜索 tech 属性

 CDF 对象属性查询 (virtuoso_cdfdb):
  cdfdb_search_attr          — 按类（cdfDataId/cdfParamId）+ 关键词搜索 CDF 属性

启动方式:
  knowledge-virtuoso          （console script）
  python -m knowledge_virtuoso
  由 Claude Code 通过 .mcp.json 配置自动启动，stdin/stdout 通信。
"""

import json
import re

from mcp.server.fastmcp import FastMCP
from knowledge_virtuoso.functions.core import catalog as skill_language
from knowledge_virtuoso.database.db.core import catalog as db_attr
from knowledge_virtuoso.database.techdb.core import catalog as techdb_attr
from knowledge_virtuoso.database.cdfdb.core import catalog as cdfdb_attr

mcp = FastMCP("virtuoso")

# brief 模式下描述保留的字符数；超出时明确标注截断，不静默丢弃。
_DESCRIPTION_LIMIT = 600

# 工具层取舍策略：索引如实收录 doc 的全部节，这里决定哪些节进哪个粒度档。
# 依据见 docs/index-v3-design.md 5.1——brief 放"缺了就写错或写不出调用"的节
# （前置条件、交互式提示、选项字典），full 放澄清语义与导航类。改这张表零重建。
_SECTION_POLICY = {
    "prerequisites": "brief",
    "interactive_function": "brief",
    "associated_options": "brief",
    # 选项说明是"选项字典"，abs* 家族里单函数可达 4.8 万字；进 brief 会让 brief 无上界
    # （absAbstract brief 50,958 字 ≈ full）。它属于澄清语义，与 example 同类，移到 full；
    # 关联选项（选项名 + 一行说明）留在 brief——那才是"缺了就写不出调用"的部分。
    "option_descriptions": "full",
    "example": "full",
    "additional_information": "full",
    "related_functions": "full",
    "format": "full",
    "purpose": "full",
    "overview": "full",
    "errors": "full",
}

# 参数/返回值的正文块在 brief 档被略去时给一行指针，免得"选项说明没给"被读成"没有选项"。
_POINTER_SECTIONS = {"option_descriptions": "选项说明"}
_SECTION_TITLES = {
    "prerequisites": "前置条件",
    "interactive_function": "交互式函数",
    "associated_options": "关联选项",
    "option_descriptions": "选项说明",
    "example": "示例",
    "reference": "参考链接",
    "additional_information": "补充说明",
    "related_functions": "相关函数",
    "format": "格式",
    "purpose": "用途",
    "overview": "总览",
    "errors": "错误",
}
_LEVEL = {"signature": 0, "brief": 1, "full": 2}


def _continuation(text: str, indent: str = "    ") -> str:
    """给多行描述的续行补缩进，使其在视觉上仍归属所属条目。"""
    return text.replace("\n", "\n" + indent)


def _capped(text: str, detail: str) -> str:
    """brief 档截断长正文，并明确标注截断字符数，不静默丢弃。"""
    if detail != "full" and len(text) > _DESCRIPTION_LIMIT:
        return (f"{text[:_DESCRIPTION_LIMIT]}"
                f'…（已截断 {len(text) - _DESCRIPTION_LIMIT} 字符；detail="full" 取全文）')
    return text


def _uncovered_lines(text: str, items: list[dict]) -> str:
    """参数/返回值正文里**没有被结构化条目覆盖**的部分。

    索引如实收录每节正文；其中老式排版（hiSetCursor 的连续 ``<p>`` 单元格、纯散文段落）
    没有条目承载，此前在"有条目就不打正文"的取舍下整段到不了 LLM。这里逐行消去已渲染过的
    条目文本，返回剩下的部分——既补上散文，又不与条目重复。
    """
    pieces = sorted(
        {piece.strip() for item in items for field in ("name", "desc")
         for piece in (item.get(field) or "").split("\n") if len(piece.strip()) >= 3},
        key=len, reverse=True,
    )
    rendered_blob = " ".join(pieces)
    out = []
    for line in (text or "").split("\n"):
        rest = " ".join(line.split()).strip()
        if not rest:
            continue
        for piece in pieces:
            if piece in rest:
                rest = " ".join(rest.replace(piece, " ").split())
        rest = rest.strip(" -–—\t")
        # 已被条目渲染过的（含作为某条目说明前缀的短行）不再重复输出。
        if len(rest) < 3 or rest in rendered_blob or _SEPARATOR_RE.fullmatch(rest):
            continue
        out.append(rest)
    return "\n".join(out)


# 正文残段小于这个长度就不输出（分隔线、表头单词一类不值得占上下文）。
_MIN_RESIDUAL = 40
_SEPARATOR_RE = re.compile(r"[-–—]{1,2}")


def _sig_params(decl_text: str) -> list[str]:
    """签名里的 ?参数 名（按出现顺序去重）。"""
    out: list[str] = []
    for match in re.finditer(r"\?([A-Za-z_]\w*)", decl_text or ""):
        if match.group(1) not in out:
            out.append(match.group(1))
    return out


def _table_params(items: list[dict]) -> list[str]:
    """参数表里的 ?参数 名（按出现顺序去重；位置参数不计）。"""
    out: list[str] = []
    for item in items:
        match = re.search(r"\?([A-Za-z_]\w*)", item.get("name", ""))
        if match and match.group(1) not in out:
            out.append(match.group(1))
    return out


def _near(a: str, b: str) -> bool:
    """编辑距离 ≤ 1（官方笔误多是少写/多写一个字母）。"""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(long)):
        if long[:i] + long[i + 1:] == short:
            return True
    return False


def _param_check(decl_text: str, items: list[dict]) -> str:
    """签名里的 ?参数 与参数表名字对账。

    官方文档偶有笔误、漏列或单复数不一致（实测 67 个函数：`?cvId` 在表里写作 `?cdId`、
    `?beginExt` 写作 `?beginnExt`、`?recreateAll` 写作 `?g_recreateAll`）。渲染器同时握着
    `decl` 与参数表，这一行能直接挡住"照参数表写却对不上签名"的坏调用。
    """
    sig, table = _sig_params(decl_text), _table_params(items)
    if not sig or not table:
        return ""
    only_sig = [name for name in sig if name not in table]
    only_table = [name for name in table if name not in sig]
    if not only_sig and not only_table:
        return ""
    paired_sig: set[str] = set()
    paired_table: set[str] = set()
    notes = []
    for name in only_sig:
        for other in only_table:
            if other in paired_table:
                continue
            if name in other or other in name or _near(name, other):
                notes.append(f"?{name} 在参数表写作 ?{other}")
                paired_sig.add(name)
                paired_table.add(other)
                break
    parts = [f"签名 {len(sig)} 个 ?参数 / 参数表 {len(table)} 条"]
    if notes:
        parts.append("；".join(notes) + "（疑官方笔误，以原文为准）")
    missing = [name for name in only_sig if name not in paired_sig]
    if missing:
        parts.append("签名有而参数表未列: " + " ".join(f"?{n}" for n in missing))
    extra = [name for name in only_table if name not in paired_table]
    if extra:
        parts.append("参数表有而签名未见: " + " ".join(f"?{n}" for n in extra))
    return "校验: " + "；".join(parts)


def _body_label(kind: str, state: str | None, with_items: bool) -> str:
    """正文块的标题：把解析状态说给读者，也避免"条目之外的散文"被误读成参数条目。"""
    if state in {"text_fallback", "unparsed"}:
        why = "官方原文未结构化" if state == "text_fallback" else "官方原文未能可靠提取"
        return f"{kind}（{why}，以下照录原文）"
    if with_items:
        return f"{kind}（条目之外，原文散文，非结构化条目）"
    return kind


def _section_text(sections: dict, key: str) -> str:
    return (sections.get(key) or {}).get("text", "")


def _render_section(key: str, section: dict) -> list[str]:
    """把一节渲染成带节名的行；表格行按「名 — 说明」输出，避免错位阅读。"""
    lines = [f"\n{_SECTION_TITLES.get(key, key)}:"]
    if section.get("text"):
        lines.append("  " + _continuation(section["text"].strip(), "  "))
    for row in section.get("items", []):
        name = row.get("name") or row.get("value", "")
        lines.append(f"  {name} — {_continuation(row.get('desc', ''), '    ')}")
    return lines


@mcp.tool()
async def skill_language_search_doc(
    func_name: str, detail: str = "brief", sections: list[str] | None = None
) -> str:
    """从 IC618 文档中查询 SKILL 函数的签名、参数、返回值、示例。

    参数:
      func_name: 函数名，如 "dbCreateRect"。需是**完整名**；不确定拼法时先用
                 skill_language_search_components 搜到名字再查。未命中会给出相近名建议。
      detail:   返回粒度。brief=签名+来源+参数+返回(默认)；signature=仅签名；full=全部(含描述+示例)
      sections: 额外索取的节名列表，可选项：prerequisites、interactive_function、
                 associated_options、option_descriptions、example、additional_information、
                 related_functions、format、purpose、overview、reference。
                 描述/参数/返回值由 detail 控制，不接受显式索取。
    """
    if detail not in _LEVEL:
        raise ValueError("detail must be signature, brief, or full")
    info = skill_language.query_function(func_name)
    if info is None:
        hints = skill_language.suggest_names(func_name)
        if hints:
            return f"未找到函数: {func_name}\n相近的官方函数: " + "、".join(hints)
        return f"未找到函数: {func_name}"

    declaration = info["decl"][0]
    content = info.get("sections", {})
    sections = sections or []
    head = [f"函数: {info['name']}", f"签名: {declaration['text']}"]
    if info.get("status") == "deprecated":
        head.append("状态: 已弃用（Cadence 文档仍保留该可调用函数）")
    if declaration.get("shared_from"):
        head.append(f"签名说明: 该声明取自共享主题 {declaration['shared_from']}，"
                    "不是本函数单独文档化的签名")
    if detail == "signature":
        return "\n".join(head)

    lines = head[:]
    # 描述：description 缺失时用 definition 顶上——取舍在工具层，索引里两节各留各的。
    body = _section_text(content, "description") or _section_text(content, "definition")
    if detail != "full" and len(body) > _DESCRIPTION_LIMIT:
        cut = len(body) - _DESCRIPTION_LIMIT
        lines.append(f"描述: {body[:_DESCRIPTION_LIMIT]}"
                     f'…（已截断 {cut} 字符；detail="full" 取全文）')
    else:
        lines.append(f"描述: {body}")

    where = info.get("where", {})
    origin = where.get("file", "")
    if where.get("anchor") and where["anchor"] != info["name"]:
        origin += "#" + where["anchor"]
    lines.append(f"来源: {origin}")

    if detail == "full":
        extra_declarations = [d["text"] for d in info["decl"][1:] if d.get("text")]
        if extra_declarations:
            lines.append("其他声明: " + " | ".join(extra_declarations))
        reference = content.get("reference") or {}
        seen_links: set[str] = set()
        rendered_links = []
        for link in reference.get("links", []):
            text = (link.get("text") or "").strip()
            if not text or text in seen_links:
                continue
            seen_links.add(text)
            href = link.get("href") or ""
            # 页内数字锚点（#787126）是文档工具生成的定位标记，对使用函数无信息量；同名链接去重。
            rendered_links.append(f"{text}({href})" if href and not href.startswith("#") else text)
        reference_text = (reference.get("text") or "").strip()
        # 正文常常就是同一批链接名的罗列（还带换行，会把一行撑成多行）：与链接合并去重，
        # 免得同一批函数名出现两遍；正文里链接没覆盖到的名字并入链接。
        text_names = re.findall(r"[A-Za-z_]\w*", reference_text)
        if text_names and rendered_links:
            covered = sum(1 for name in text_names if name in seen_links)
            if covered >= 0.6 * len(text_names):
                rendered_links += [name for name in text_names if name not in seen_links]
                reference_text = ""
        summary = " ".join(part for part in (reference_text, " ".join(rendered_links)) if part)
        if summary:
            lines.append("相关: " + " ".join(summary.split()))
        if info.get("also_at"):
            lines.append("其他来源: " + ", ".join(
                f"{s['file']}#{s['anchor']}" if s.get("anchor") else s.get("file", "")
                for s in info["also_at"]))
        # 只报需要留意的解析异常：正文保留但未结构化、未能可靠提取、声明取自共享主题。
        # `not_documented`/`documented_none` 是"官网上没有"而非异常，全量列出会让 full 档
        # 多出十几条噪声（小函数里能占全文三成），需要时可回查索引的 field_status。
        abnormal = {k: v for k, v in info.get("field_status", {}).items()
                    if v in {"text_fallback", "unparsed", "shared_declaration"}}
        if abnormal:
            lines.append("解析状态: " + json.dumps(abnormal, ensure_ascii=False))

    # 参数：根参数 + 子参数列表（ROD 等函数）；子列表嵌在根参数之后缩进输出。
    # 条目之外若还有正文（老式排版的散排单元格、散文段落），补在条目后——否则整段到不了 LLM。
    field_status = info.get("field_status") or {}
    arguments = content.get("arguments") or {}
    root = arguments.get("root") or {}
    lists = arguments.get("lists") or []
    arg_items = list(root.get("items") or [])
    for group in lists:
        arg_items += list(group.get("items") or [])
    rendered_items: list[dict] = []
    if arg_items or lists:
        lines.append("\n参数:")
        check = _param_check(declaration["text"], arg_items)
        if check:
            lines.append("  " + check)
        if root.get("title"):
            lines.append(f"  主参数组 [{root['title']}]:")
        for item in root.get("items") or []:
            lines.append(f"  {item['name']} — {_continuation(item['desc'])}")
            for value in item.get("values") or []:
                lines.append(f"      取值 {value['value']} — "
                             f"{_continuation(value['desc'], '      ')}")
            rendered_items.append(item)
        for group in lists:
            parent = group.get("parent") or {}
            if parent.get("arg"):
                link = f"（属于 {parent['arg']}）"
            elif group.get("list_type"):
                link = "（未连接到根参数）"
            else:
                link = ""
            lines.append(f"  子参数 [{group['title']}]{link}:")
            for item in group.get("items") or []:
                lines.append(f"    {item['name']} — {_continuation(item['desc'], '      ')}")
                rendered_items.append(item)
    residual = _uncovered_lines(arguments.get("text", ""), rendered_items)
    if len(residual) >= _MIN_RESIDUAL:
        label = _body_label("参数正文", field_status.get("arguments"), bool(rendered_items))
        lines.append(f"\n{label}:\n  " + _continuation(_capped(residual, detail), "  "))
    elif not arg_items and not lists and field_status.get("arguments") == "not_documented":
        # 有签名参数、官方却没给参数说明：说清是"没文档"而不是"不吃参数"。
        count = len(_sig_params(declaration["text"]))
        if count:
            lines.append(f"\n参数:（官方未提供参数说明；签名含 {count} 个 ?参数，见来源原文）")

    returns = content.get("returns") or {}
    if returns.get("items"):
        lines.append("\n返回:")
        for item in returns["items"]:
            lines.append(f"  {item['value']} — {_continuation(item['desc'])}")
        residual = _uncovered_lines(returns.get("text", ""), returns["items"])
        if len(residual) >= _MIN_RESIDUAL:
            label = _body_label("返回正文", field_status.get("returns"), True)
            lines.append(f"\n{label}:\n  " + _continuation(_capped(residual, detail), "  "))
    else:
        residual = _uncovered_lines(returns.get("text", ""), [])
        if len(residual) >= _MIN_RESIDUAL:
            label = _body_label("返回正文", field_status.get("returns"), False)
            lines.append(f"\n{label}:\n  " + _continuation(_capped(residual, detail), "  "))

    level = _LEVEL[detail]
    rendered: set[str] = set()
    for key in _SECTION_POLICY:
        section = content.get(key)
        if not section or _LEVEL[_SECTION_POLICY[key]] > level:
            continue
        lines.extend(_render_section(key, section))
        rendered.add(key)
    # 显式索取：sections=[...] 把指定节拉进本次返回，不改策略表、不需重建索引。
    requestable = set(_SECTION_TITLES) | {"reference"}
    for key in sections:
        if key in rendered or key not in requestable:
            continue
        section = content.get(key)
        if section:
            lines.extend(_render_section(key, section))
            rendered.add(key)

    # 本档略去、但属参数信息的节给一行指针（abs* 家族参数表为空，选项字典是唯一载体），
    # 免得"选项说明没给"被读成"没有选项"。
    for key, title in _POINTER_SECTIONS.items():
        section = content.get(key)
        if not section or key in rendered or _LEVEL[_SECTION_POLICY[key]] <= level:
            continue
        size = len(section.get("text") or "") + sum(
            len(row.get("name", "")) + len(row.get("desc", ""))
            for row in section.get("items") or [])
        if size >= _MIN_RESIDUAL:
            count = len(section.get("items") or [])
            lines.append(f'{title}:（{count} 条，{size} 字；detail="full" 或 '
                         f'sections=["{key}"] 取）')

    return "\n".join(lines)


@mcp.tool()
async def skill_language_search_components(prefix: str = "", keywords: str = "", offset: int = 0, limit: int = 30) -> str:
    """按前缀 + 关键词组合搜索 SKILL 函数名。推荐优先使用！

    参数:
      prefix:   前缀过滤（如 "tech"、"db"、"le"）。留空不过滤前缀。
      keywords: 空格分隔关键词（如 "find via def"）。留空返回该前缀所有函数。

    关键词按**驼峰自动拆词**，且对无边界写法兜底——"createRect"、"create rect"、
    "createrect"、完整名 "dbCreateRect" 都能命中，不必手动拆分；多个词是“都要命中”的交集。
    未命中时会给出相近名建议（若指定了 prefix，则限同前缀内）。

    示例:
      prefix="tech" keywords="find via def"  → techFindViaDefByName
      prefix="db" keywords="createRect"      → dbCreateRect（驼峰自动拆开）
      prefix="db" keywords="create path"     → dbCreatePath
      prefix="tech" keywords=""              → 列出所有 tech 前缀函数（最多30）
    """
    if not prefix and not keywords:
        return "请至少指定 prefix 或 keywords 中的一个。"

    page = skill_language.search_page(prefix, keywords, offset, limit)
    matches = page["names"]
    if not page["total"]:
        ctx = f"prefix='{prefix}'" if prefix else ""
        ctx += " " if prefix and keywords else ""
        ctx += f"keywords='{keywords}'" if keywords else ""
        message = f"未找到匹配 {ctx} 的函数。"
        hints = skill_language.suggest_names(keywords, prefix=prefix)
        if hints:
            message += "\n相近的官方函数: " + "、".join(hints)
        return message

    lines = [f"匹配总数 {page['total']}；offset={offset}，本页 {len(matches)} 个，limit={limit}"]
    if page["next_offset"] is not None:
        lines.append(f"下一页: offset={page['next_offset']}, limit={limit}")
    for name in matches:
        entry = skill_language._index.get(name, {})
        fpath = (entry.get("where") or {}).get("file", "?")
        lines.append(f"  {name:45s} {fpath}")
    return "\n".join(lines)


# ─── 属性查询 ──────────────────────────────────────────────

@mcp.tool()
async def db_search_attr(objType: str = "", keyword: str = "") -> str:
    """搜索数据库对象属性。按 objType + 关键词查找属性名、类型和读写权限。

    参数:
      objType: ~>objType 返回值，如 "rect"/"inst"/"stdVia"。留空搜全部类型。
      keyword: 属性名关键词（子串匹配）。留空列出该类型的全部属性。

    示例:
      objType="rect" keyword=""       → 列出 rect 全部属性
      objType="inst" keyword="name"   → inst 属性中带 "name" 的
      objType="" keyword="bBox"       → 所有类型中名为 bBox 的属性
    """
    results = db_attr.search_attr(objType=objType, keyword=keyword)
    if not results:
        ctx = f"objType='{objType}'" if objType else "全部类型"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的属性。"
    lines = [f"匹配 {len(results)} 个属性:"]
    lines.append(f"  {'name':25s} {'rw':4s} {'type':15s} desc")
    lines.append(f"  {'-'*25} {'-'*4} {'-'*15} {'-'*30}")
    for r in results:
        desc = r["desc"] if len(r["desc"]) <= 60 else r["desc"][:59] + "…"
        lines.append(f"  {r['name']:25s} {r['rw']:4s} {r['type']:15s} {desc}")
    return "\n".join(lines)


# ─── tech 数据库对象属性查询 ──────────────────────────────────

@mcp.tool()
async def techdb_search_attr(className: str = "", keyword: str = "") -> str:
    """搜索 tech 数据库对象属性。按类 + 关键词查找属性名、描述和所属类。

    参数:
      className: tech 对象类名，如 "techID"/"layers"/"lps"/"viaDefs"/"siteDefs"。
                 留空搜全部类。
      keyword:   属性名关键词（子串匹配）。留空列出该类全部属性。

    示例:
      className="viaDefs" keyword=""            → 列出 viaDefs 全部属性
      className="lps" keyword="valid"           → lps 属性中带 "valid" 的
      className="" keyword="objType"            → 所有类中名为 objType 的属性
    """
    results = techdb_attr.search_tech_attr(className=className, keyword=keyword)
    if not results:
        ctx = f"类='{className}'" if className else "全部类"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的 tech 属性。"
    # rw 在该索引里恒为 "?"，无信息量时不占列。
    show_rw = any(r["rw"] != "?" for r in results)
    lines = [f"匹配 {len(results)} 个 tech 属性:"]
    if show_rw:
        lines.append(f"  {'name':25s} {'rw':2s} {'type':10s} 所属类")
        lines.append(f"  {'-'*25} {'-'*2} {'-'*10} {'-'*30}")
    else:
        lines.append(f"  {'name':25s} {'type':10s} 所属类")
        lines.append(f"  {'-'*25} {'-'*10} {'-'*30}")
    for r in results:
        if show_rw:
            lines.append(f"  {r['name']:25s} {r['rw']:2s} {r['type']:10s} {','.join(r['classes'])}")
        else:
            lines.append(f"  {r['name']:25s} {r['type']:10s} {','.join(r['classes'])}")
    return "\n".join(lines)


# ─── CDF 对象属性查询 ──────────────────────────────────

@mcp.tool()
async def cdfdb_search_attr(className: str = "", keyword: str = "") -> str:
    """搜索 CDF 对象属性。按类 + 关键词查找属性名、描述和所属类。

    参数:
      className: CDF 对象类名，如 "cdfDataId"/"cdfParamId"。留空搜全部类。
      keyword:   属性名关键词（子串匹配）。留空列出该类全部属性。

    示例:
      className="cdfParamId" keyword=""        → 列出 cdfParamId 全部属性
      className="cdfDataId" keyword="param"    → cdfDataId 属性中带 "param" 的
      className="" keyword="value"             → 所有类中名为 value 的属性
    """
    results = cdfdb_attr.search_cdf_attr(className=className, keyword=keyword)
    if not results:
        ctx = f"类='{className}'" if className else "全部类"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的 CDF 属性。"
    lines = [f"匹配 {len(results)} 个 CDF 属性:"]
    lines.append(f"  {'name':25s} {'rw':4s} {'type':10s} desc")
    lines.append(f"  {'-'*25} {'-'*4} {'-'*10} {'-'*40}")
    for r in results:
        desc = r["desc"] if len(r["desc"]) <= 55 else r["desc"][:54] + "…"
        lines.append(f"  {r['name']:25s} {r['rw']:4s} {r['type']:10s} {desc}")
    return "\n".join(lines)


def main() -> None:
    import asyncio

    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
