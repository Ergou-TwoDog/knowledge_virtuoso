#!/usr/bin/env python3
"""knowledge_virtuoso.database.db.render — 设计库属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。表格本体在 `database/core/render.py`，
这里只声明**本库的列**（列宽与描述截断属于本库的表示，改它不影响别的库）。
"""

from knowledge_virtuoso.database.core.render import Column, render_table

__all__ = ["render_db_attrs"]

_COLUMNS = (
    Column("name", "name", 25),
    Column("rw", "rw", 4),
    Column("type", "type", 15),
    Column("desc", "desc", 0, truncate=60),
)


def render_db_attrs(rows: list[dict], objType: str = "", keyword: str = "") -> str:
    """把属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    return render_table(rows, _COLUMNS, subject="属性", selector_label="objType",
                        all_label="全部类型", selector=objType, keyword=keyword)
