#!/usr/bin/env python3
"""
knowledge_virtuoso.server — MCP Server: SKILL 函数与对象属性知识库查询服务。

提供 tool:

 函数查询 (virtuoso_skill_language):
  skill_language_search_doc         — 查询函数签名（detail=signature/brief/full 控制粒度）
  skill_language_search_components  — 按前缀+关键词组合搜索函数名（推荐）

 对象属性查询——**每个属性库一个工具，由 `database/core/registry.py` 按发现的库生成**：
  db_search_attr        选择器 objType     — 设计库对象属性
  techdb_search_attr    选择器 className   — 技术库对象属性
  cdfdb_search_attr     选择器 className   — CDF 对象属性
  dd_search_attr        选择器 object      — 数据管理对象属性

 **加一个属性库 = 在 `database/` 下加一棵树**，本文件一行不用改。各库的选择器不是同一个
 概念（运行时对象类型／技术库类名／CDF 类名／数据管理对象），所以**不压成一个词**：
  registry 生成工具时按各库自己的 `SELECTOR` 造参数名。

启动方式:
  knowledge-virtuoso          （console script）
  python -m knowledge_virtuoso
  由 Claude Code 通过 .mcp.json 配置自动启动，stdin/stdout 通信。

本文件只做 MCP 接线：校验参数 → 查 catalog → 交给该分类的渲染层 → 返回字符串。
输出长什么样由 functions/core/render.py 与 database/<库>/render.py 决定（各来源的差异见
functions/sources/<来源>/render.py），接线约定见 tests/README.md，
因此改渲染策略不需要动这里，改工具契约（名字、参数、docstring）也不需要动渲染层。
"""

import asyncio
import inspect

from mcp.server.fastmcp import FastMCP

from knowledge_virtuoso.functions import index as skill_language
from knowledge_virtuoso.functions import registry
from knowledge_virtuoso.functions.core import render as skill_render
from knowledge_virtuoso.database.core import registry as attr_registry

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


# ─── 属性查询：每个属性库一个工具，由注册表生成 ────────────────
#
# 工具名 = `<库名>_search_attr`，第一个参数名用该库自己的 `SELECTOR`（objType /
# className / object）——那是四个不同的概念，压成一个词会让调用方以为它们通用。
#
# FastMCP 从 `inspect.signature` 建输入 schema，而 `inspect.signature` 认手工赋的
# `__signature__`：于是同一个实现能按库生成各自契约的工具，不必为每个库抄一遍函数。

def _attr_tool(lib):
    """库 → 一个 MCP 工具函数（参数名 = 该库的 SELECTOR + keyword）。"""
    selector = lib.SELECTOR

    def fn(**kwargs):                       # 真调用时 FastMCP 按 schema 传关键字
        value = kwargs.get(selector, "")
        keyword = kwargs.get("keyword", "")
        return lib.render(lib.search(value, keyword), value, keyword)

    fn.__name__ = attr_registry.tool_name(lib)
    fn.__doc__ = lib.DOC
    fn.__signature__ = inspect.Signature(
        [inspect.Parameter(selector, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                           default="", annotation=str),
         inspect.Parameter("keyword", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                           default="", annotation=str)],
        return_annotation=str)
    return fn


for _lib in attr_registry.LIBS:
    mcp.add_tool(_attr_tool(_lib), name=attr_registry.tool_name(_lib), description=_lib.DOC)


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
