#!/usr/bin/env python3
"""
knowledge_virtuoso.functions.core.render — 函数库的渲染主干。

**只做"记录 → 文本"**：入参是索引里的一条记录（dict）与渲染参数，出参是字符串。
这里不 import ``mcp``、不 import catalog、不读索引、不做 I/O——查询留在 catalog，
组装留在 ``server.py``。渲染切成独立接缝之后，五档输出可以脱离整条加载链单独测
（见 tests/knowledge_virtuoso/functions/）。

**与来源无关**：主干不认识"官方"或"二次开发"，来源自己的那几行差异（digest 里的
标记、头部的状态行）由各自的 ``<来源>/render.py`` 以 ``Profile`` 传进来。

工具层的取舍都在这张策略表与这些上限里：索引如实收录官方 doc 的全部节，哪个节进
哪个 ``detail`` 档由 ``_SECTION_POLICY`` 决定，**改它不需要重建索引**。依据见
``functions/README.md``「渲染主干（`core/render.py`）的取舍」。
"""

import re
from dataclasses import dataclass
from typing import Callable

__all__ = [
    "DEFAULT_PROFILE",
    "DETAILS",
    "Profile",
    "digest_of",
    "render_entry",
    "render_not_found",
    "render_search_empty",
    "render_search_page",
]


# brief 模式下描述保留的字符数；超出时明确标注截断，不静默丢弃。
_DESCRIPTION_LIMIT = 600

# 工具层取舍策略：索引如实收录 doc 的全部节，这里决定哪些节进哪个粒度档。
# 依据见 functions/README.md「渲染主干（`core/render.py`）的取舍」——brief 放"缺了就写错或写不出调用"的节
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
# 合法档位的唯一真相源：MCP 层按它校验 detail，免得两处各写一遍合法值。
DETAILS = ("digest", "skel", "signature", "brief", "full")


@dataclass(frozen=True)
class Profile:
    """一个来源对渲染的附加影响——主干与来源之间唯一的接缝。

    ``digest_marks``：该来源条目在 digest 的括号里追加的标记（排在"已弃用""共享声明"
    之后，顺序即输出顺序）。``status_line``：该来源条目的状态行（如二次开发函数的
    ``load()`` 前提），返回 ``None`` 表示不加。官方来源两者都为空。
    """

    digest_marks: tuple[str, ...] = ()
    status_line: Callable[[dict], str | None] | None = None


DEFAULT_PROFILE = Profile()


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

# brief 档参数块的字数预算：超过则把说明续文移入 full，但**保留参数名、允许取值与 Default**。
# 实测超预算的只有 4 个函数（rodCreatePath、rodCreateRect、hiCreateAppForm、
# hiCreateReportField）；参数密集但无长散文的（如 hnlInitMap）不受影响。
_ARGS_BUDGET = 12000
# 取值/默认值所在的行（brief 预算据此保留、skel 据此片段截取）：判据必须只有一个，
# 否则"brief 留下的"与"skel 保留的"会各说各话。见 _fact_fragments 的两条实测教训。
_FACT_WORD_RE = re.compile(r"\b[Dd]efaults?\b|\b[Vv]alid [Vv]alues?\b|默认|取值")
_FACT_LINE_RE = _FACT_WORD_RE

# 解析状态用面向读者的措辞，不暴露内部字段名与枚举值。
_STATE_TEXT = {
    "text_fallback": "官方原文保留但未结构化",
    "unparsed": "官方原文未能可靠提取",
    "shared_declaration": "声明取自共享主题",
}


def _arg_entry(item: dict, indent: str) -> tuple[str, list[str]]:
    """把一个参数条目拆成「首行 + 续行」，供 brief 档按预算裁剪说明续文。"""
    desc_lines = (item.get("desc") or "").split("\n")
    head = f"{indent}{item['name']} — {desc_lines[0]}"
    cont = [indent + "  " + line for line in desc_lines[1:]]
    for value in item.get("values") or []:
        desc = (value.get("desc") or "").replace("\n", "\n" + indent + "    ")
        cont.append(f"{indent}    取值 {value['value']} — {desc}")
    return head, cont


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


# ─── 两个省 token 的新档位 ─────────────────────────────────────────
# digest：选函数用的一行摘要，长度与文档体量脱钩（硬上限 900 字，全库实测 max 737）。
# skel：写调用用的骨架，只给"关键字 类型 + 取值/默认（逐字）+ 返回 + 来源 + 校验行"，
#       说明正文一律移出并给出指针。两者都只重排/筛选已有内容，不新造信息。
_DIGEST_MAX = 900
_SIG_BOUND = 320          # digest/skel 里的签名上限（超出截断并标注）
_SIG_WIDTH = 88           # 签名折行宽度
_POINTER = "省略: "        # 统一的省略指针前缀，便于程序化识别


def _reflow(text: str) -> str:
    """把官方签名里的换行与多余空白压平（仅新档位使用；老档位逐字保留原文）。"""
    return re.sub(r"\s+", " ", text or "").strip()


def _wrap(text: str, width: int = _SIG_WIDTH, indent: str = "      ") -> list[str]:
    """按宽度折行；续行缩进，使"签名:"块读起来是一个整体。"""
    lines, current = [], ""
    for word in text.split(" "):
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return [lines[0]] + [indent + x for x in lines[1:]] if lines else []


def _sig_block(declaration: dict, bound: int | None = _SIG_BOUND) -> list[str]:
    """新档位的签名块：压平原文换行后折行。

    digest 有 900 字硬上限，故按 `bound` 截断并标注；**skel 不截断**——它是"写调用"
    那一档，签名必须完整（实测有 2 个函数的签名超出 320 字，截断会让签名里的 ?参数
    无处可查）。
    """
    signature = _reflow(declaration.get("text", ""))
    if bound and len(signature) > bound:
        signature = signature[:bound].rstrip() + "…（签名截断）"
    lines = _wrap(signature)
    lines[0] = "签名: " + lines[0]
    if declaration.get("shared_from"):
        lines.append(f"      （取自共享主题 {declaration['shared_from']}，非本函数单独文档化的签名）")
    return lines


def digest_of(name: str, entry: dict, *, profile: Profile = DEFAULT_PROFILE) -> str:
    """一行摘要：名字（状态标记）+ 有界签名 + 描述首句 + 返回 + 来源。"""
    declaration = (entry.get("decl") or [{}])[0]
    signature = _reflow(declaration.get("text", ""))
    if len(signature) > _SIG_BOUND:
        signature = signature[:_SIG_BOUND].rstrip() + "…"
    content = entry.get("sections") or {}
    description = _reflow(_section_text(content, "description") or _section_text(content, "definition"))
    first_sentence = re.split(r"(?<=[.;])\s", description, maxsplit=1)[0] if description else ""
    returns = ", ".join(row.get("value", "")
                        for row in ((content.get("returns") or {}).get("items") or [])[:3])
    marks = []
    if entry.get("status") == "deprecated":
        marks.append("已弃用")
    if declaration.get("shared_from"):
        marks.append("共享声明")
    # 来源自己的标记由各自的 <来源>/render.py 提供，主干不认识任何具体来源。
    marks.extend(profile.digest_marks)
    line = " | ".join(part for part in (
        name + (f"（{'、'.join(marks)}）" if marks else ""),
        signature,
        first_sentence,
        f"返回: {returns}" if returns else "",
        (entry.get("where") or {}).get("file", ""),
    ) if part)
    if len(line) > _DIGEST_MAX:
        line = line[:_DIGEST_MAX].rstrip() + "…"
    return line


def _arg_plan(root: dict, lists: list[dict]) -> list:
    """参数块按输出顺序的渲染计划：字符串=分组标题行，元组=(条目首行, 续行列表)。"""
    plan: list = []
    for item in root.get("items") or []:
        plan.append(_arg_entry(item, "  "))
    for group in lists:
        parent = group.get("parent") or {}
        if parent.get("arg"):
            link = f"（属于 {parent['arg']}）"
        elif group.get("list_type"):
            link = "（未连接到根参数）"
        else:
            link = ""
        plan.append(f"  子参数 [{group['title']}]{link}:")
        for item in group.get("items") or []:
            plan.append(_arg_entry(item, "    "))
    return plan


def _omit(fragments: list[str], target: str) -> str:
    """统一的省略指针：`省略: <省了什么> → detail="X"`，任何省略都必须有这一行。"""
    return f"{_POINTER}{'；'.join(fragments)} → {target}"


_FACT_SENTENCE_CAP = 160


def _fact_fragments(desc: str) -> list[str]:
    """参数说明里含默认值/允许取值的片段（逐字）。

    两条实测教训：

    1. **大小写与写法都要认**。官方混用 ``Default:``、``The default value is 0.``、
       ``By default,``、``Defaults to``；上一版只匹 `Default`，导致 674 个参数（391 个函数）
       的默认值在 skel 里消失（如 abeLayerGrow 的 `?north`、abeElapsedTime 的 `?reset`）。
    2. **词边界**。用 `\\b` 才不会把 `formDefaultAction`、`g_defaultValue` 这类标识符里的
       "Default" 当成事实，凭空保留一整行脱节的表格碎片。

    首行的片段从**句子开头**截取（上限 160 字），续行整行保留——保证片段读得通。
    """
    out = []
    for index, line in enumerate((desc or "").split("\n")):
        match = _FACT_WORD_RE.search(line)
        if not match:
            continue
        if index:
            out.append(line)
            continue
        start = 0
        for boundary in re.finditer(r"(?<=[.;:])\s", line[:match.start()]):
            start = boundary.end()
        if match.start() - start > _FACT_SENTENCE_CAP:
            start = match.start()
        out.append(line[start:])
    return out


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

# ─── 渲染入口 ──────────────────────────────────────────────────────

def render_entry(entry: dict, detail: str = "brief", sections: list[str] | None = None,
                 *, profile: Profile = DEFAULT_PROFILE) -> str:
    """把一条记录渲染成文本。

    任何档位只要省略了内容都会输出一行 ``省略: …`` 指针，省略的部分一律能在指明的
    档位里逐字取回；``digest``/``skel`` 重排的只有签名的换行。``detail`` 的合法性
    由调用方（``server.py``）按 ``DETAILS`` 校验。
    """
    declaration = entry["decl"][0]
    content = entry.get("sections", {})
    sections = sections or []
    if detail == "digest":
        # 选函数用：一行，长度与文档体量脱钩；省略什么由指针行说明——
        # 只在签名真的被截断时才说"完整签名"，否则消费方会为不存在的剩余签名再多拉一次。
        omitted = ["参数说明", "示例与补充说明"]
        if len(_reflow(declaration.get("text", ""))) > _SIG_BOUND:
            omitted.insert(0, "完整签名")
        return "\n".join([
            digest_of(entry["name"], entry, profile=profile),
            _omit(omitted, 'detail="skel" / "brief" / "full"'),
        ])
    head = [f"函数: {entry['name']}", f"签名: {declaration['text']}"]
    if entry.get("status") == "deprecated":
        head.append("状态: 已弃用（Cadence 文档仍保留该可调用函数）")
    if declaration.get("shared_from"):
        head.append(f"签名说明: 该声明取自共享主题 {declaration['shared_from']}，"
                    "不是本函数单独文档化的签名")
    source_note = profile.status_line(entry) if profile.status_line else None
    if source_note:
        head.append(source_note)
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

    where = entry.get("where", {})
    origin = where.get("file", "")
    if where.get("anchor") and where["anchor"] != entry["name"]:
        origin += "#" + where["anchor"]
    lines.append(f"来源: {origin}")

    # 参数/返回值先算好：正文块的标题会写明解析状态，所以 `解析状态` 行不再重复列这两节。
    field_status = entry.get("field_status") or {}
    arguments = content.get("arguments") or {}
    root = arguments.get("root") or {}
    lists = arguments.get("lists") or []
    arg_items = list(root.get("items") or [])
    for group in lists:
        arg_items += list(group.get("items") or [])
    args_residual = _uncovered_lines(arguments.get("text", ""), arg_items)
    returns = content.get("returns") or {}
    ret_items = returns.get("items") or []
    ret_residual = _uncovered_lines(returns.get("text", ""), ret_items)
    labeled = {key for key, residual in (("arguments", args_residual), ("returns", ret_residual))
               if len(residual) >= _MIN_RESIDUAL and field_status.get(key) in _STATE_TEXT}

    if detail == "full":
        extra_declarations = [d["text"] for d in entry["decl"][1:] if d.get("text")]
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
            # 锚点（页内 `#787126` 与跨页 `…#PCRE_CASELESS`）是文档工具生成的定位标记，
            # 对使用函数无信息量；跨页链接保留文件名，页内链接只留名字。
            # 文件名用方括号而非圆括号：`nconc(list.html)` 会被读成"函数调用"，
            # 且与同一行里的裸名字形式不一致；`nconc [list.html]` 与 `来源: 文件[#锚点]`
            # 的方括号约定一致，切分规则只剩"名字 + 可选 [文件]"。
            href = (link.get("href") or "").split("#")[0]
            rendered_links.append(f"{text} [{href}]" if href else text)
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
        if entry.get("also_at"):
            lines.append("其他来源: " + ", ".join(
                f"{s['file']}#{s['anchor']}" if s.get("anchor") else s.get("file", "")
                for s in entry["also_at"]))
        # 只报需要留意的解析异常，且用面向读者的措辞（不暴露内部字段名与枚举值）。
        # `not_documented`/`documented_none` 是"官网上没有"而非异常，不列。
        # 参数/返回值正文块的标题已经写明了状态，这里不重复列这两节。
        abnormal = {k: v for k, v in entry.get("field_status", {}).items()
                    if v in _STATE_TEXT and k not in labeled}
        if abnormal:
            parts = [_STATE_TEXT[v] if k == "decl"
                     else f"{_SECTION_TITLES.get(k, k)}节{_STATE_TEXT[v]}"
                     for k, v in abnormal.items()]
            lines.append("解析状态: " + "；".join(parts))

    # 参数：根参数 + 子参数列表（ROD 等函数）；子列表嵌在根参数之后缩进输出。
    # 条目之外若还有正文（老式排版的散排单元格、散文段落），补在条目后——否则整段到不了 LLM。
    arg_plan = _arg_plan(root, lists)
    if detail == "skel":
        out = [f"函数: {entry['name']}"] + _sig_block(declaration, bound=None)
        if source_note:
            out.append(source_note)
        out.append(f"来源: {origin}")
        check = _param_check(declaration["text"], arg_items)
        entries = [e for e in arg_plan if isinstance(e, tuple)]
        if arg_plan:
            out.append("")
            out.append("参数:")
            if check:
                out.append("  " + check)
            for entry in arg_plan:
                if isinstance(entry, str):
                    out.append(entry)
                    continue
                head_line, cont = entry
                name_part = head_line.split(" — ", 1)[0]
                out.append(name_part)
                pad = " " * (len(name_part) - len(name_part.lstrip()) + 2)
                head_desc = head_line.split(" — ", 1)[1] if " — " in head_line else ""
                out += [pad + frag for frag in _fact_fragments(head_desc)]
                out += [x for x in cont if _FACT_LINE_RE.search(x)]
        if ret_items:
            out.append("")
            out.append("返回: " + " / ".join(x.get("value", "") for x in ret_items))
        elif ret_residual:
            out.append("")
            out.append(f'{_POINTER}返回值是原文散文（{len(ret_residual):,} 字） → detail="brief"')
        total_desc = kept_desc = params_with_desc = 0
        for head_line, cont in entries:
            head_desc = head_line.split(" — ", 1)[1] if " — " in head_line else ""
            desc_all = head_desc + "\n".join([""] + cont)
            if desc_all.strip():
                params_with_desc += 1
            total_desc += len(desc_all)
            kept_desc += sum(len(f) for f in _fact_fragments(head_desc)) \
                + sum(len(x) for x in cont if _FACT_LINE_RE.search(x))
        omitted_chars = max(0, total_desc - kept_desc)
        if omitted_chars or args_residual:
            out.append("")
            out.append(f'{_POINTER}参数说明 {params_with_desc} 条共 {omitted_chars:,} 字 → detail="brief"；'
                       f'示例、补充说明、相关函数、选项说明 → detail="full"')
        return "\n".join(out)

    moved_notes = 0
    if arg_items or lists:
        lines.append("\n参数:")
        check = _param_check(declaration["text"], arg_items)
        if check:
            lines.append("  " + check)
        if root.get("title"):
            lines.append(f"  主参数组 [{root['title']}]:")
        size = sum(len(e[0]) + sum(len(x) for x in e[1])
                   for e in arg_plan if isinstance(e, tuple))
        trim = detail != "full" and size > _ARGS_BUDGET
        for entry in arg_plan:
            if isinstance(entry, str):
                lines.append(entry)
                continue
            head, cont = entry
            lines.append(head)
            kept = [x for x in cont if _FACT_LINE_RE.search(x)] if trim else cont
            if trim and len(kept) != len(cont):
                moved_notes += 1
            lines.extend(kept)
        if moved_notes:
            lines.append("")
            lines.append(_omit([f"参数说明续文 {moved_notes} 条共 {size - sum(len(x) for e in arg_plan if isinstance(e, tuple) for x in e[1] if _FACT_LINE_RE.search(x)):,} 字"],
                               'detail="full"') + "（参数名、允许取值与 Default 已保留）")
    residual = args_residual
    if len(residual) >= _MIN_RESIDUAL:
        label = _body_label("参数正文", field_status.get("arguments"), bool(arg_items))
        lines.append(f"\n{label}:\n  " + _continuation(_capped(residual, detail), "  "))
    elif not arg_items and not lists and field_status.get("arguments") == "not_documented":
        # 有签名参数、官方却没给参数说明：说清是"没文档"而不是"不吃参数"。
        count = len(_sig_params(declaration["text"]))
        if count:
            lines.append(f"\n参数:（官方未提供参数说明；签名含 {count} 个 ?参数，见来源原文）")

    returns = content.get("returns") or {}
    if ret_items:
        lines.append("\n返回:")
        for item in ret_items:
            lines.append(f"  {item['value']} — {_continuation(item['desc'])}")
        residual = ret_residual
        if len(residual) >= _MIN_RESIDUAL:
            label = _body_label("返回正文", field_status.get("returns"), True)
            lines.append(f"\n{label}:\n  " + _continuation(_capped(residual, detail), "  "))
    else:
        residual = ret_residual
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
            lines.append(_omit([f"{title} {count} 条共 {size:,} 字"],
                               f'detail="full" 或 sections=["{key}"]'))

    return "\n".join(lines)


def render_not_found(func_name: str, hints: list[str]) -> str:
    """未命中时的提示；``hints`` 为空就只说没找到。"""
    if hints:
        return f"未找到函数: {func_name}\n相近的官方函数: " + "、".join(hints)
    return f"未找到函数: {func_name}"


def render_search_empty(prefix: str, keywords: str, hints: list[str]) -> str:
    """搜索零命中时的提示（"prefix 与 keywords 都留空"的守卫不在这层，属接口参数校验）。"""
    ctx = f"prefix='{prefix}'" if prefix else ""
    ctx += " " if prefix and keywords else ""
    ctx += f"keywords='{keywords}'" if keywords else ""
    message = f"未找到匹配 {ctx} 的函数。"
    if hints:
        message += "\n相近的官方函数: " + "、".join(hints)
    return message


def render_search_page(page: dict, records: list[dict], with_digest: bool = True,
                       *, profile_for: Callable[[dict], Profile] | None = None) -> str:
    """搜索页的正文：页头 + 每行的摘要（或名字与来源）。

    合并视图里两类条目的摘要都走这里，所以标记按记录现取（``profile_for``）。

    ``records`` 与 ``page["names"]`` 同序——调用方用 ``catalog.entries(names)`` 取，
    渲染层不碰索引。
    """
    matches = page["names"]
    lines = [f"匹配总数 {page['total']}；offset={page['offset']}，本页 {len(matches)} 个，limit={page['limit']}"]
    if page["next_offset"] is not None:
        lines.append(f"下一页: offset={page['next_offset']}, limit={page['limit']}")
    if with_digest:
        lines.append('（每行 = 摘要；完整签名与参数说明用 skill_language_search_doc '
                     'detail="skel"/"brief"）')
    for name, entry in zip(matches, records):
        if with_digest:
            lines.append("  " + digest_of(
                name, entry, profile=profile_for(entry) if profile_for else DEFAULT_PROFILE))
        else:
            fpath = (entry.get("where") or {}).get("file", "?")
            lines.append(f"  {name:45s} {fpath}")
    return "\n".join(lines)
