#!/usr/bin/env python3
"""属性库共用的表格渲染：四个库的差异**全在"声明"里**，机制收在这一份。

    db       name(25) rw(4)  type(15) desc(截 60)
    cdfdb    name(25) rw(4)  type(10) desc(截 55)
    techdb   name(25) [rw(2)] type(10) 所属类            ← 整列 rw 都是 None 就藏列
    dd       name(24) kind(9) [card(5)] 适用对象          ← 整列 card 都是 None 就藏列

没有一处是结构差异，所以"换个库要不要重写"这条判据在这里的答案是**不用**——那就该抽。
（解析器那边答案相反：四份文档记法各不相同，换个库得重写，所以四库的 `core/parse.py`
与 `core/decorate.py` 仍然各写各的。）

分工：各库在自己的 `__init__.py` 里声明一份 `RenderSpec`（列 + 提示语），
渲染入口只有 `render_attrs()` 一个；`render_table()` 是它的表格本体，
**永远不知道"对象"这回事**。

**只做"行 → 文本"**：不 import `mcp`、不 import 库、不读索引、不做 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Column", "RenderSpec", "render_table", "render_attrs"]


@dataclass(frozen=True)
class Column:
    """一列：取值键、表头、宽度，外加三样可选行为。"""

    key: str                       # 行里的字段名（列表值配 `join`）
    title: str                     # 表头文字
    width: int                     # 定宽（最后一列的表头不补齐，与既有输出一致）
    truncate: int = 0              # >0：超长截到该宽度并加 `…`
    hide_if_null: bool = False     # 整列都是 None 时**不占列**（techdb 的 `rw`、dd 的基数）
    join: str = ""                 # 值是列表时用什么拼（`classes` / `objectTypes` 用 `","`）
    sep: int = 30                  # 最后一列的分隔线宽度（各库历史上就是不同的）


def _cell(value, column: Column) -> str:
    text = column.join.join(value) if isinstance(value, list) else ("" if value is None else str(value))
    if column.truncate and len(text) > column.truncate:
        return text[: column.truncate - 1] + "…"
    return text


def _visible(rows: list[dict], columns: tuple[Column, ...]) -> list[Column]:
    """藏掉"整列都是 `None`"的列。没有行时按声明全给（"未找到"不列表头）。

    归一之后"没有这一项"一律写成 `None`（见 `objects.py` 的 `ATTR_KEYS`），所以判据只需
    这一条——techdb 以前用 `"?"`、dd 用 `""` 当占位符，那两个值现在都不存在了。
    键缺失与 `None` 同样处理（`r.get(c.key)`），免得"少了键"被读成"有值"。
    """
    if not rows:
        return list(columns)
    return [c for c in columns
            if not c.hide_if_null or any(r.get(c.key) is not None for r in rows)]


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


@dataclass(frozen=True)
class RenderSpec:
    """一个属性库的渲染**声明**：印哪些列、提示语怎么写、对象头印哪几项。

    各库在自己的 `__init__.py` 里给出一份，库之间再无结构差异——
    "换个库要不要重写"的答案因此是"只换一份声明"。
    """

    columns: tuple[Column, ...]
    subject: str                   # 标题与提示里的主语（中英交界那个空格一起写进来）
    selector_label: str            # 提示里的上下文，如 `类`
    all_label: str                 # 没给选择器时提示里写什么，如 `全部类`
    note: str = ""                 # 标题后那句补充（如 dd 的"原文未给类型与说明"）
    header_fields: tuple[tuple[str, str], ...] = ()   # (标签, 对象键)；() = 不印对象头


# 对象头里每个字段最多印这么长——它是"这次问的是谁"的一行回声，不是数据本身。
_HEADER_VALUE = 80


def _obj_header(obj: dict, fields: tuple[tuple[str, str], ...]) -> str:
    """`对象 Rectangle  title=Rectangle Attributes  section=Shape Attributes`。

    **原文没给的项整项略去**（`null`/`""` 都不印），所以每个库印几项由它自己的原文决定。
    """
    parts = [f"对象 {obj.get('id', '')}"]
    for label, key in fields:
        value = obj.get(key)
        if not value:
            continue
        text = str(value)
        if len(text) > _HEADER_VALUE:
            text = text[:_HEADER_VALUE - 1] + "…"
        parts.append(f"{label}={text}")
    return "  ".join(parts)


def render_attrs(rows: list[dict], spec: RenderSpec, *,
                 selector: str = "", keyword: str = "", obj: dict | None = None) -> str:
    """行 → 文本：本层唯一的渲染入口。

    `obj` 是**调用方**（`server.py`）从索引里取来的对象记录——渲染层自己不读索引。
    给了就在最前面加一行对象头，把"这次问的是谁"回显出来：**选择器是别名或运行时名时
    这一点尤其要紧**（问 `rect` 要能看见解析成了 `Rectangle`）。选择器为空（跨对象查询）
    或压根没解析到时，`obj` 是 `None`，不加这一行——三种情形因此分得开：

    * 解析到了、有匹配   → 对象头 + 表格
    * 解析到了、筛完没匹配 → 对象头 + "未找到匹配…"（**这是新信息**：认出来了）
    * 没解析到           → 只有"未找到匹配…"

    对象头里印哪几项由 `spec.header_fields` 决定；**它可以是空的**，那就只印 `对象 <id>`
    （原文没给那几项时，比如 dd 的六个对象，只剩 id 也是有用的回显）。
    """
    body = render_table(rows, spec.columns, subject=spec.subject,
                        selector_label=spec.selector_label, all_label=spec.all_label,
                        selector=selector, keyword=keyword, note=spec.note)
    if obj is None:
        return body
    return _obj_header(obj, spec.header_fields) + "\n" + body
