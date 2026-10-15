#!/usr/bin/env python3
"""数据管理对象属性与关系（官方 `skdfref/chap3.html`）。

**库接口**见 `database/core/registry.py` 的 `REQUIRED_ATTRS`（库名、一句话说明、工具描述、
①② 两层入口、构建、查询、对象头、渲染）。选择器四库共用一个名字 `object`——本库的"对象"
是数据管理对象（lib / cell / view / libFile / cellFile / viewFile），原文的记法是**转置**的：
一行一个属性/关系，后面每个适用对象各占一格。

原文怎么读在 `core/`（`parse.py` ① + `decorate.py` ②，② 收尾还要**摊平**），本库自己的
声明（库名、版本、来源文档、跨对象口径、本库的构建期校验）在 `index.py` 的 `LIB`。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.render import Column, RenderSpec, render_attrs
# ①② 两层**在这里只是暴露给注册表**（`REQUIRED_ATTRS` 里的契约项，证明这棵树切了三层）；
# 本模块自己不用它们——用它们的是 `index.py` 的声明与 `core/assembly.py`。
from knowledge_virtuoso.database.dd.core.decorate import decorate  # noqa: F401
from knowledge_virtuoso.database.dd.core.parse import parse  # noqa: F401
from knowledge_virtuoso.database.dd.index import LIB

NAME = LIB.name
LABEL = "数据管理对象属性"
DOC = """搜索数据管理对象的属性与关系。按对象 + 关键词查找。

参数:
  object:  数据管理对象，取 "lib"/"cell"/"view"/"libFile"/"cellFile"/"viewFile"
           之一（大小写不敏感）。留空搜全部对象。
  keyword: 名字关键词（子串匹配）。留空列出该对象的全部属性与关系。

返回两类条目，用 kind 列区分：`attr`（属性）与 `relation`（关系，带基数 `1:1`/`1:n`）。
注意**原文没给类型也没给说明**——属性表只有"名字 | 适用对象"两列，逐条属性没有类型
（原文那张类型图例所指的图，在这套 doc 里并不存在），所以这里没有 type/desc 列，
不是解析漏了。

示例:
  object="cellFile" keyword=""     → cellFile 的全部属性与关系
  object="lib" keyword="cells"     → lib 上的 cells 关系
  object="" keyword="group"        → 所有对象中名字含 group 的
"""

build = LIB.build
# 查询入口归**查询那一层**（`core/query.py` 的 `Query`）：四库共用同一个函数对象、同一个签名。
_QUERY = query.Query(LIB)
search = _QUERY.search
describe = _QUERY.describe

# 渲染声明：只有三列（关系多一列基数）；原文没有类型也没有说明，标题后那句就是这意思。
_SPEC = RenderSpec(
    columns=(Column("name", "name", 24),
             Column("kind", "kind", 9),
             Column("cardinality", "card", 5, hide_if_null=True),
             Column("objectTypes", "适用对象", 0, join=",")),
    subject=" data management 属性/关系", selector_label="object", all_label="全部对象",
    note="（原文未给类型与说明）",
    # `header_fields` 留空：本库的对象记录里除 `id` 全是空的（原文只给了这六个名字），
    # 所以对象头就只印 `对象 lib`。
)


def render(rows: list[dict], object: str = "", keyword: str = "",  # noqa: A002
           obj: dict | None = None) -> str:
    """把属性/关系行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    return render_attrs(rows, _SPEC, selector=object, keyword=keyword, obj=obj)
