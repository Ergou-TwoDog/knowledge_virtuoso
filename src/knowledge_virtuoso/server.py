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
    "option_descriptions": "brief",
    "example": "full",
    "additional_information": "full",
    "related_functions": "full",
    "format": "full",
    "purpose": "full",
    "overview": "full",
    "errors": "full",
}
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
        links = " ".join(f"{link['text']}({link['href']})"
                         for link in reference.get("links", []))
        summary = " ".join(part for part in (reference.get("text"), links) if part)
        if summary:
            lines.append("相关: " + summary)
        if info.get("also_at"):
            lines.append("其他来源: " + ", ".join(
                f"{s['file']}#{s['anchor']}" if s.get("anchor") else s.get("file", "")
                for s in info["also_at"]))
        abnormal = {k: v for k, v in info.get("field_status", {}).items() if v != "present"}
        if abnormal:
            lines.append("解析状态: " + json.dumps(abnormal, ensure_ascii=False))

    # 参数：根参数 + 子参数列表（ROD 等函数）；子列表嵌在根参数之后缩进输出。
    arguments = content.get("arguments")
    if arguments:
        root = arguments.get("root", {})
        lists = arguments.get("lists", [])
        if root.get("items") or lists:
            lines.append("\n参数:")
            if root.get("title"):
                lines.append(f"  [{root['title']}]")
            for item in root.get("items", []):
                lines.append(f"  {item['name']} — {_continuation(item['desc'])}")
                for value in item.get("values") or []:
                    lines.append(f"      取值 {value['value']} — "
                                 f"{_continuation(value['desc'], '      ')}")
            for group in lists:
                parent = group.get("parent") or {}
                if parent.get("arg"):
                    link = f"（属于 {parent['arg']}）"
                elif group.get("list_type"):
                    link = "（未连接到根参数）"
                else:
                    link = ""
                lines.append(f"  子参数 [{group['title']}]{link}:")
                for item in group.get("items", []):
                    lines.append(f"    {item['name']} — {_continuation(item['desc'], '      ')}")
        elif detail == "full" and arguments.get("text"):
            lines.append("\n参数正文:\n  " + _continuation(arguments["text"], "  "))

    returns = content.get("returns") or {}
    if returns.get("items"):
        lines.append("\n返回:")
        for item in returns["items"]:
            lines.append(f"  {item['value']} — {_continuation(item['desc'])}")
    elif detail == "full" and returns.get("text"):
        lines.append("\n返回正文:\n  " + _continuation(returns["text"], "  "))

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
