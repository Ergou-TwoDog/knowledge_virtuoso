#!/usr/bin/env python3
"""knowledge_virtuoso.database.techdb.render — 技术库属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_tech_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。表格本体在 `database/core/render.py`，
这里只声明**本库的列**：`rw` 在该索引里恒为 `?`，无信息量时不占列。
"""

from knowledge_virtuoso.database.core.render import Column, render_table

__all__ = ["render_techdb_attrs"]

_COLUMNS = (
    Column("name", "name", 25),
    Column("rw", "rw", 2, hide_if_all="?"),      # 全列都是 `?` 就不占列
    Column("type", "type", 10),
    Column("classes", "所属类", 0, join=","),     # 同一名字可能挂在多个类下
)


def render_techdb_attrs(rows: list[dict], className: str = "", keyword: str = "") -> str:
    """把 tech 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    return render_table(rows, _COLUMNS, subject=" tech 属性", selector_label="类",
                        all_label="全部类", selector=className, keyword=keyword)
