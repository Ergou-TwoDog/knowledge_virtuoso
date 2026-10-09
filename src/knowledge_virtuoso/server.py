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


def _continuation(text: str, indent: str = "    ") -> str:
    """给多行描述的续行补缩进，使其在视觉上仍归属所属条目。"""
    return text.replace("\n", "\n" + indent)


def _grouping_is_informative(groups: list[dict]) -> list[dict]:
    """只保留含真实分组信息的部分；默认单组 Arguments 不重复输出。"""
    return [
        g for g in groups
        if g.get("name") != "Arguments" or g.get("groups") or any(
            a.get("group") for a in g.get("arguments", [])
        )
    ]


@mcp.tool()
async def skill_language_search_doc(func_name: str, detail: str = "brief") -> str:
    """从 IC618 文档中查询 SKILL 函数的签名、参数、返回值、示例。

    参数:
      func_name: 函数名，如 "dbCreateRect"。需是**完整名**；不确定拼法时先用
                 skill_language_search_components 搜到名字再查。未命中会给出相近名建议。
      detail:   返回粒度。brief=签名+来源+参数+返回(默认)；signature=仅签名；full=全部(含描述+示例)
    """
    if detail not in {"signature", "brief", "full"}:
        raise ValueError("detail must be signature, brief, or full")
    info = skill_language.query_function(func_name)
    if info is None:
        hints = skill_language.suggest_names(func_name)
        if hints:
            return f"未找到函数: {func_name}\n相近的官方函数: " + "、".join(hints)
        return f"未找到函数: {func_name}"

    head = [f"函数: {info['name']}", f"签名: {info['signature']}"]
    if info.get("status") == "deprecated":
        head.append("状态: 已弃用（Cadence 文档仍保留该可调用函数）")
    if info.get("signature_note"):
        head.append("签名说明: " + info["signature_note"])

    if detail == "signature":
        return "\n".join(head)

    source = info.get("source") or {}
    origin = source.get("file") or info.get("source_file", "")
    if source.get("anchor") and source["anchor"] != info["name"]:
        origin += "#" + source["anchor"]

    lines = head[:]
    description = info.get("description", "")
    if detail != "full" and len(description) > _DESCRIPTION_LIMIT:
        cut = len(description) - _DESCRIPTION_LIMIT
        lines.append(f"描述: {description[:_DESCRIPTION_LIMIT]}"
                     f'…（已截断 {cut} 字符；detail="full" 取全文）')
    else:
        lines.append(f"描述: {description}")
    lines.append(f"来源: {origin}")

    if detail == "full":
        # 只补前面没有的信息：多声明、结构化失败时的正文 fallback、真实补充来源。
        extra_signatures = (info.get("signatures") or [])[1:]
        if extra_signatures:
            lines.append("其他签名: " + " | ".join(extra_signatures))
        if not info.get("arguments") and info.get("arguments_text"):
            lines.append("参数正文: " + _continuation(info["arguments_text"]))
        if not info.get("returns") and info.get("returns_text"):
            lines.append("返回正文: " + _continuation(info["returns_text"]))
        references = info.get("references") or {}
        links = " ".join(
            f"{link['text']}({link['href']})" for link in references.get("links", [])
        )
        summary = " ".join(part for part in (references.get("text"), links) if part)
        if summary:
            lines.append("相关: " + summary)
        extra_sources = (info.get("sources") or [])[1:]
        if extra_sources:
            lines.append("其他来源: " + ", ".join(
                f"{s['file']}#{s['anchor']}" if s.get("anchor") else s.get("file", "")
                for s in extra_sources
            ))
        basis = info.get("derivation_basis")
        if basis:
            lines.append("共享声明依据: topic=" + str(basis.get("topic", "")))
        abnormal = {k: v for k, v in info.get("field_status", {}).items() if v != "present"}
        if abnormal:
            lines.append("解析状态: " + json.dumps(abnormal, ensure_ascii=False))

    if info.get("arguments"):
        lines.append("\n参数:")
        for a in info["arguments"]:
            group = f" [{a['group']}]" if a.get("group") else ""
            lines.append(f"  {a['name']}{group} — {_continuation(a['desc'])}")
    if info.get("returns"):
        lines.append("\n返回:")
        for r in info["returns"]:
            lines.append(f"  {r['value']} — {_continuation(r['desc'])}")

    if detail == "full":
        groups = _grouping_is_informative(info.get("argument_groups") or [])
        if groups:
            lines.append("\n参数分组:")

            def append_group(group: dict, depth: int = 1) -> None:
                indent = "  " * depth
                lines.append(f"{indent}{group['name']}")
                for argument in group.get("arguments", []):
                    lines.append(f"{indent}  {argument['name']} — "
                                 f"{_continuation(argument['desc'], indent + '    ')}")
                for child in group.get("groups", []):
                    append_group(child, depth + 1)

            for group in groups:
                append_group(group)
        if info.get("example"):
            lines.append(f"\n示例:\n  {info['example']}")

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
        fpath = entry.get("file", "?")
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
