#!/usr/bin/env python3
"""技术库对象类及其 `~>` 属性（官方 `sktechfile/appA.html`）。

**库接口**见 `database/core/registry.py` 的 `REQUIRED_ATTRS`（库名、一句话说明、工具描述、
①② 两层入口、构建、查询、对象头、渲染）。选择器四库共用一个名字 `object`——技术库的
"对象"是 `techID~>` 的成员；本库额外认哪些写法见 `DOC` 与 `index.py` 的 `LIB.aliases`。

原文怎么读在 `core/`（`parse.py` ① + `decorate.py` ②），本库自己的声明（库名、版本、
来源文档、别名、跨对象口径、本库的构建期校验）在 `index.py` 的 `LIB`。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.render import Column, RenderSpec, render_attrs
# ①② 两层**在这里只是暴露给注册表**（`REQUIRED_ATTRS` 里的契约项，证明这棵树切了三层）；
# 本模块自己不用它们——用它们的是 `index.py` 的声明与 `core/assembly.py`。
from knowledge_virtuoso.database.techdb.core.decorate import decorate  # noqa: F401
from knowledge_virtuoso.database.techdb.core.parse import parse  # noqa: F401
from knowledge_virtuoso.database.techdb.index import LIB

NAME = LIB.name
LABEL = "技术库对象属性"
DOC = """搜索 tech 数据库对象属性。按类 + 关键词查找属性名、类型和所属类。

参数:
  object:   tech 对象类名，如 "techID"/"layers"/"lps"/"viaDefs"/"siteDefs"。
            留空搜全部类。
  keyword:  属性名关键词（子串匹配）。留空列出该类全部属性。

注意：原文的 Attributes 表只有"属性名 | 说明"两列，**没有类型列**，所以 type 列是从
该类自己的说明里推出来的（推不出来就是空的）。

示例:
  object="viaDefs" keyword=""       → 列出 viaDefs 全部属性
  object="lps" keyword="valid"      → lps 属性中带 "valid" 的
  object="" keyword="objType"       → 所有类中名为 objType 的属性
"""

build = LIB.build
# 查询入口归**查询那一层**（`core/query.py` 的 `Query`）：四库共用同一个函数对象、同一个签名。
_QUERY = query.Query(LIB)
search = _QUERY.search
describe = _QUERY.describe

# 渲染声明：`rw` 在本库里恒为 `None`（原文没有读写列），整列无值时不占列。
# 对象头印 `title`（原文的写法 `techID~>x`）与 `desc`（**原文自己的 Description 小节**）
# ——后者以前存了却没有任何地方显示，LLM 根本看不到。
_SPEC = RenderSpec(
    columns=(Column("name", "name", 25),
             Column("rw", "rw", 2, hide_if_null=True),
             Column("type", "type", 10),
             Column("classes", "所属类", 0, join=",")),
    subject=" tech 属性", selector_label="object", all_label="全部类",
    header_fields=(("title", "title"), ("desc", "desc")),
)


def render(rows: list[dict], object: str = "", keyword: str = "",  # noqa: A002
           obj: dict | None = None) -> str:
    """把 tech 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。

    `obj` 由调用方给（`describe`）：问的是别名（如 `stdViaDef`）时靠它回显解析到的类。
    """
    return render_attrs(rows, _SPEC, selector=object, keyword=keyword, obj=obj)
