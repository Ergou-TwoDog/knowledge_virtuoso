#!/usr/bin/env python3
"""
knowledge_virtuoso.database.db.core.decorate — ② **归一**：把文档结构读成统一载荷。

①（`parse.py`）给的是"原文里有什么"，这一层回答"**它们是什么意思**"：

* 哪一格是属性名（清掉 `<br>` 之后还要过名字形状，只有一处形状定义：`objects.NAME_RE`）；
* `Note: include <父表>` 那行说的是父指针——它有**两种位置**：多数表在表里的第二行，
  `Generic widthSpacingPattern` 等 4 张表写在**表前的正文**里（`parse` 把它收在 `preamble`）；
* 名字格里的 `<br>` 是**折行**（一个名字断开）还是**一行两名**（共享同一条描述）；
* `objType` 行有没有自报运行时名（`"in this case \"cellview\""`）。

产出**七键**对象（键集见 `database/core/objects.py` 的 `OBJECT_KEYS`）：

    {"objects": {<id>: {id, title, runtime, section, desc, parent, attrs}}}

记录按 `database/core/objects.py` 的 `ATTR_KEYS` 建（`objects_mod.record`）。**本库在这里
算的两样**：

* `rw` —— 原文的 Modify 列有三个取值（`no`/`yes`/`no/yes`），收成两值（含 `yes` 即 `rw`）。
  **原文那一列照旧原样存在 `modify` 里**，两者并存：读得出"原文怎么写的"与"我们怎么呈现的"；
* `kind` —— 恒 `attr`（本库收录的只有属性）。

字符串字段里**原文那一格是空的就存 `None`**（"没给"只有一种写法，渲染层据此藏列）。
`definedIn`、`classes` 要到查询时才有（继承合并、谁声明过这个名字）——那是 `core/query.py`
的事，不在这里。校验与版本号也不在这里（那是 `index.py` 装配时的事）。
上游 `parse.py`，下游 `index.py`。
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.db.core.parse import _SUFFIX, _text

# 父指针那行。原文有三种写法（`include` 64 · `Includes` 4 · `includes` 1），
# 还有一处笔误 `include s Generic Object Attributes`，所以大小写不敏感 + 容忍多余的 `s`。
_INCLUDE_RE = re.compile(r"Note:\s*includes?\s+(?:s\s+)?(.+?)\s+Attributes\b", re.I)
# 运行时名只在对象的 `objType` 行里自报（"Type of the object: \"layer\""）。
_OBJTYPE_HINT_RE = re.compile(r"type of (?:the )?object", re.I)
_QUOTED_RE = re.compile(r'"\s*([^"\s]+)\s*"')


def _object_id(title: str) -> str:
    """表标题 → 对象 id（去掉 ` Attributes` 后缀；原文有一处 `Standard viaVariant .` 的尾巴也去掉）。"""
    oid = title[: -len(_SUFFIX)] if title.endswith(_SUFFIX) else title
    return re.sub(r"\s*\.\s*$", "", oid).strip()


def _names_in_cell(segments) -> list[str]:
    """名字格里 `<br>` 的两种含义（见 README §五 规则 8），只能靠大小写交界分辨：

    * `modifiedButNot<br>Saved`  —— 长名字被排版断开 → **一个**名字
    * `startConn<br>endConn`     —— 一行列了两个名字 → **两个**名字（共享同一条描述）

    交界处是「小写→大写」的算折行（长标识符断在驼峰处），其余算两名。
    """
    parts = [_text([s]) for s in segments if _text([s])]
    if len(parts) <= 1:
        return parts
    if all(p[-1].islower() and q[0].isupper() for p, q in zip(parts, parts[1:])):
        return ["".join(parts)]
    return parts


def _row_cells(row) -> list[list[str]]:
    """一行的非空格子；每个格子保留 `<br>` 分出的段落。"""
    return [[_text([seg]) for seg in cell] if cell else [] for cell in row]


def _parent_from(text: str) -> str | None:
    """从一段文本里认父指针（`Note: include[s] X Attributes`），认不出返回 None。

    两处都用这同一个正则，只是喂进来的文本不同：表里的那一行，或表前的正文段落。
    """
    m = _INCLUDE_RE.search(text or "")
    return _object_id(m.group(1).strip()) if m else None


def _rw_from_modify(modify: str) -> str:
    """原文的 Modify 列 → 两值的 `rw`：含 `yes` 就是可写。

    这是**本库的推法**（原文给的是 `no`/`yes`/`no/yes` 三态）。算完落在记录里，所以
    **改了这条规则就要抬载荷版本号并重建**——盘上的值是按当时的规则算出来的。
    """
    return "rw" if "yes" in (modify or "").lower() else "ro"


def decorate(raw: dict) -> dict:
    """② **归一**：把文档结构读成统一载荷（每个对象自己的属性表 + 父指针）。"""
    objects: dict[str, dict] = {}
    for sec in raw["sections"]:
        title, rows = sec["title"], sec["table"]
        if not title.endswith(_SUFFIX) or not rows:
            continue                               # 只认属性表；空表（没解析出内容）也不要
        oid = _object_id(title)
        attrs, parent, runtime = [], _parent_from(sec["preamble"]), None
        for row in rows[1:]:                       # 第 0 行是表头
            cells = [c for c in _row_cells(row) if any(c)]
            if not cells:
                continue
            head = _text(cells[0])
            if len(cells) == 1 and head.lower().startswith("note:"):
                # 绝大多数表的父指针是表里的第二行（`Note: include X Attributes`）
                parent = _parent_from(head) or parent
                continue
            if len(cells) < 3:
                continue                           # 枚举值的续行等，不是属性
            names = _names_in_cell(cells[0])
            if not names or not all(objects_mod.NAME_RE.match(n) for n in names):
                continue
            modify = _text(cells[1]) or None
            typ = _text(cells[2]) or None
            desc = (_text([" ".join(c) for c in cells[3:]]) if len(cells) > 3 else "") or None
            for name in names:
                attrs.append(objects_mod.record(name, kind="attr", type=typ,
                                                rw=_rw_from_modify(modify), desc=desc,
                                                modify=modify))
            if runtime is None and names[0] == "objType" and _OBJTYPE_HINT_RE.search(desc):
                q = _QUOTED_RE.search(desc)        # 只在对象自报时才取（"in this case \"cellview\""）
                runtime = q.group(1) if q else None
        objects[oid] = {"id": oid, "title": title, "runtime": runtime,
                        "section": sec["section"], "desc": None,   # 原文没有对象级说明
                        "parent": parent, "attrs": attrs}

    return {"objects": objects}
