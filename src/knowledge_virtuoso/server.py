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

本文件只做 MCP 接线：校验参数 → 查 catalog → 交给该分类的渲染层 → 返回字符串。
输出长什么样由 functions/core/render.py 与 database/<库>/render.py 决定（各来源的差异见
functions/sources/<来源>/render.py），接线约定见 tests/README.md，
因此改渲染策略不需要动这里，改工具契约（名字、参数、docstring）也不需要动渲染层。
"""

from mcp.server.fastmcp import FastMCP

from knowledge_virtuoso.functions import registry
from knowledge_virtuoso.functions import index as skill_language
from knowledge_virtuoso.functions.core import render as skill_render
from knowledge_virtuoso.database.db.core import catalog as db_attr
from knowledge_virtuoso.database.db.render import render_db_attrs
from knowledge_virtuoso.database.techdb.core import catalog as techdb_attr
from knowledge_virtuoso.database.techdb.render import render_techdb_attrs
from knowledge_virtuoso.database.cdfdb.core import catalog as cdfdb_attr
from knowledge_virtuoso.database.cdfdb.render import render_cdfdb_attrs

mcp = FastMCP("virtuoso")

# ─── 函数查询 ───────────────────────────────────────────

@mcp.tool()
async def skill_language_search_doc(
    func_name: str, detail: str = "brief", sections: list[str] | None = None
) -> str:
    """从 IC618 文档中查询 SKILL 函数的签名、参数、返回值、示例。

    参数:
      func_name: 函数名，如 "dbCreateRect"。需是**完整名**；不确定拼法时先用
                 skill_language_search_components 搜到名字再查。未命中会给出相近名建议。
      detail:   返回粒度。**digest**=一行摘要（名字+有界签名+描述首句+返回+来源，≤900 字，
                用于在候选之间挑函数）；**skel**=调用骨架（完整签名+校验行+每个参数的
                「关键字 类型」+取值/默认原文+返回+来源，用于写调用）；brief=签名+来源+
                参数+返回(默认)；signature=仅签名；full=全部(含描述+示例)。
                任何档位省略了内容都会有 `省略: …` 一行指明去哪一档取。
      sections: 额外索取的节名列表，可选项：prerequisites、interactive_function、
                 associated_options、option_descriptions、example、additional_information、
                 related_functions、format、purpose、overview、reference。
                 描述/参数/返回值由 detail 控制，不接受显式索取。
    """
    if detail not in skill_render.DETAILS:
        raise ValueError("detail must be digest, skel, signature, brief, or full")
    info = skill_language.query_function(func_name)
    if info is None:
        return skill_render.render_not_found(func_name, skill_language.suggest_names(func_name))
    return skill_render.render_entry(info, detail, sections,
                                      profile=registry.profile_for(info))

@mcp.tool()
async def skill_language_search_components(prefix: str = "", keywords: str = "", offset: int = 0, limit: int = 30, with_digest: bool = True) -> str:
    """按前缀 + 关键词组合搜索 SKILL 函数名。推荐优先使用！

    参数:
      prefix:   前缀过滤（如 "tech"、"db"、"le"）。留空不过滤前缀。
      keywords: 空格分隔关键词（如 "find via def"）。留空返回该前缀所有函数。
      with_digest: 每行附带一行摘要（签名 + 描述首句 + 返回 + 来源），便于在候选之间挑选；
                 只要名字与来源时置 false（每行省约 100–200 字）。

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
    if not page["total"]:
        return skill_render.render_search_empty(
            prefix, keywords, skill_language.suggest_names(keywords, prefix=prefix))
    return skill_render.render_search_page(
        page, skill_language.entries(page["names"]), with_digest,
        profile_for=registry.profile_for)


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
    return render_db_attrs(db_attr.search_attr(objType=objType, keyword=keyword), objType, keyword)


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
    return render_techdb_attrs(
        techdb_attr.search_tech_attr(className=className, keyword=keyword), className, keyword)


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
    return render_cdfdb_attrs(
        cdfdb_attr.search_cdf_attr(className=className, keyword=keyword), className, keyword)


def main() -> None:
    import asyncio

    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
