#!/usr/bin/env python3
"""knowledge_virtuoso.database.cdfdb.render — CDF 属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_cdf_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。表格本体在 `database/core/render.py`，
这里只声明**本库的列**（描述截断 55 与本库的列宽一样，属于本库的表示）。
"""

from knowledge_virtuoso.database.core.render import Column, render_table

__all__ = ["render_cdfdb_attrs"]

_COLUMNS = (
    Column("name", "name", 25),
    Column("rw", "rw", 4),
    Column("type", "type", 10),
    Column("desc", "desc", 0, truncate=55, sep=40),
)


def render_cdfdb_attrs(rows: list[dict], className: str = "", keyword: str = "") -> str:
    """把 CDF 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    return render_table(rows, _COLUMNS, subject=" CDF 属性", selector_label="类",
                        all_label="全部类", selector=className, keyword=keyword)
