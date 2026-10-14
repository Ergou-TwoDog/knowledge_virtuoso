#!/usr/bin/env python3
"""knowledge_virtuoso.database.dd.render — 数据管理对象属性/关系表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_dd_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。表格本体在 `database/core/render.py`，
这里只声明**本库的列**。

**只有三列**（关系多一列基数）：原文的属性表只有"名字 | 适用对象"，没有类型也没有说明
——所以这里没有 desc/type 列，不是漏了；标题后那句说明就是这个意思。
"""

from knowledge_virtuoso.database.core.render import Column, render_table

__all__ = ["render_dd_attrs"]

_COLUMNS = (
    Column("name", "name", 24),
    Column("kind", "kind", 9),                       # attr / relation
    Column("cardinality", "card", 5, hide_if_all=""),  # 只有关系有基数，全空就不占列
    Column("objectTypes", "适用对象", 0, join=","),
)


def render_dd_attrs(rows: list[dict], object: str = "", keyword: str = "") -> str:
    """把属性/关系行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    return render_table(rows, _COLUMNS, subject=" data management 属性/关系",
                        selector_label="对象", all_label="全部对象",
                        selector=object, keyword=keyword,
                        note="（原文未给类型与说明）")
