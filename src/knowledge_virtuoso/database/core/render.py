#!/usr/bin/env python3
"""属性库共用的表格渲染：四份渲染器**同构**，差的全在"列"上。

    db       name(25) rw(4)  type(15) desc(截 60)
    cdfdb    name(25) rw(4)  type(10) desc(截 55)
    techdb   name(25) [rw(2)] type(10) 所属类            ← 整列 rw 都是 `?` 就藏列
    dd       name(24) kind(9) [card(5)] 适用对象          ← 整列 card 都空就藏列

没有一处是结构差异，所以"换个库要不要重写"这条判据在这里的答案是**不用**——那就该抽。
（解析器那边答案相反：四份文档记法各不相同，换个库得重写，所以三库的 `core/catalog.py`
仍然各写各的。）

**只做"行 → 文本"**：不 import `mcp`、不 import 库、不读索引、不做 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Column", "render_table"]

# "这一列不该隐藏"的默认值——用不着 object() 那种哨兵，因为 False 之类都可能当值。
_SENTINEL = "\x00never"


@dataclass(frozen=True)
class Column:
    """一列：取值键、表头、宽度，外加三样可选行为。"""

    key: str                       # 行里的字段名（列表值配 `join`）
    title: str                     # 表头文字
    width: int                     # 定宽（最后一列的表头不补齐，与既有输出一致）
    truncate: int = 0              # >0：超长截到该宽度并加 `…`
    hide_if_all: object = _SENTINEL  # 整列都等于它时**不占列**（techdb 的 `rw="?"`、dd 的空基数）
    join: str = ""                 # 值是列表时用什么拼（`classes` / `objectTypes` 用 `","`）
    sep: int = 30                  # 最后一列的分隔线宽度（各库历史上就是不同的）


def _cell(value, column: Column) -> str:
    text = column.join.join(value) if isinstance(value, list) else ("" if value is None else str(value))
    if column.truncate and len(text) > column.truncate:
        return text[: column.truncate - 1] + "…"
    return text


def _visible(rows: list[dict], columns: tuple[Column, ...]) -> list[Column]:
    """藏掉"整列都是那个占位值"的列。没有行时按声明全给（"未找到"不列表头）。"""
    if not rows:
        return list(columns)
    return [c for c in columns
            if c.hide_if_all is _SENTINEL
            or any(str(r.get(c.key, "")) != str(c.hide_if_all) for r in rows)]


def render_table(rows: list[dict], columns: tuple[Column, ...], *,
                 subject: str, selector_label: str, all_label: str,
                 selector: str = "", keyword: str = "", note: str = "") -> str:
    """行 → 对齐表格；无行时按查询条件给"未找到"提示。

    `subject` 在标题与提示里各出现一次（`匹配 N 个<subject>:` / `…的<subject>。`）——
                                                     ↑ 中英之间那个空格
    **连空格一起写进 `subject`**（如 `" tech 属性"`、`"属性"`），因为它是中英混排的交界，
    各库怎么断句是它自己的事。
    `selector_label`/`all_label` 是提示里的上下文（如 `类` / `全部类`），`note` 是标题后那句
    补充（如 dd 的"原文未给类型与说明"）。
    """
    if not rows:
        ctx = f"{selector_label}='{selector}'" if selector else all_label
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的{subject}。"

    cols = _visible(rows, columns)
    head = " ".join(f"{c.title:<{c.width}s}" for c in cols[:-1])
    lines = [f"匹配 {len(rows)} 个{subject}{note}:",
             f"  {head + ' ' if head else ''}{cols[-1].title}",
             "  " + " ".join([*(f"{'-' * c.width}" for c in cols[:-1]), "-" * cols[-1].sep])]
    for r in rows:
        cells = [_cell(r.get(c.key, ""), c) for c in cols]
        body = " ".join(f"{v:<{c.width}s}" for v, c in zip(cells[:-1], cols[:-1]))
        lines.append(f"  {body + ' ' if body else ''}{cells[-1]}")
    return "\n".join(lines)
