#!/usr/bin/env python3
"""CDF 对象属性（官方 `skartistref/chap21.html`）。

**库接口**见 `database/core/registry.py` 的 `REQUIRED_ATTRS`（库名、一句话说明、工具描述、
①② 两层入口、构建、查询、对象头、渲染）。选择器四库共用一个名字 `object`——CDF 的"对象"
是两个 SKILL 类（`g_cdfDataId` / `g_cdfParamId`）；本库**没有别名表**（类名就是选择器）。

原文怎么读在 `core/`（`parse.py` ① + `decorate.py` ②），本库自己的声明（库名、版本、
来源文档、跨对象口径、本库的构建期校验）在 `index.py` 的 `LIB`。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.render import Column, RenderSpec, render_attrs
# ①② 两层**在这里只是暴露给注册表**（`REQUIRED_ATTRS` 里的契约项，证明这棵树切了三层）；
# 本模块自己不用它们——用它们的是 `index.py` 的声明与 `core/assembly.py`。
from knowledge_virtuoso.database.cdfdb.core.decorate import decorate  # noqa: F401
from knowledge_virtuoso.database.cdfdb.core.parse import parse  # noqa: F401
from knowledge_virtuoso.database.cdfdb.index import LIB

NAME = LIB.name
LABEL = "CDF 对象属性"
DOC = """搜索 CDF 对象属性。按类 + 关键词查找属性名、描述和所属类。

参数:
  object:   CDF 对象类名，如 "cdfDataId"/"cdfParamId"。留空搜全部类。
  keyword:  属性名关键词（子串匹配）。留空列出该类全部属性。

注意：原文没有类型列也没有读写列，type 与 rw 两列都是推出来的（推不出来就是空的）。

示例:
  object="cdfParamId" keyword=""           → 列出 cdfParamId 全部属性
  object="cdfDataId" keyword="param"       → cdfDataId 属性中带 "param" 的
  object="" keyword="value"                → 所有类中名为 value 的属性
"""

build = LIB.build
# 查询入口归**查询那一层**（`core/query.py` 的 `Query`）：四库共用同一个函数对象、同一个签名。
_QUERY = query.Query(LIB)
search = _QUERY.search
describe = _QUERY.describe

# 渲染声明：描述截断 55、末列分隔线 40 属于本库的表示。
# 对象头印 `title`——本库的 title 就是原文的运行时名（`g_cdfDataId`），这正是要回显的。
_SPEC = RenderSpec(
    columns=(Column("name", "name", 25),
             Column("rw", "rw", 4),
             Column("type", "type", 10),
             Column("desc", "desc", 0, truncate=55, sep=40)),
    subject=" CDF 属性", selector_label="object", all_label="全部类",
    header_fields=(("title", "title"), ("section", "section")),
)


def render(rows: list[dict], object: str = "", keyword: str = "",  # noqa: A002
           obj: dict | None = None) -> str:
    """把 CDF 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。

    `obj` 由调用方给（`describe`）：靠它回显解析到的类与它在原文里叫什么。
    """
    return render_attrs(rows, _SPEC, selector=object, keyword=keyword, obj=obj)
