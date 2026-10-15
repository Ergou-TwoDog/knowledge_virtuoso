#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.core.decorate — ② **归一**：把文档结构读成统一载荷。

①（`parse.py`）给的是"原文里有什么"，这一层回答"**它们是什么意思**"：

* 哪一节是类——标题以 `techID~>` 开头才算（**类集合来自标题**，不靠手写白名单）；
* 标题尾巴的注解要去掉（`techID~>viaDefs (含尾注)` → `viaDefs`）；
* 表首列哪一格像属性名（`_is_name_token`）——不像的是**说明折行成的续行**，并回上一条；
* 类内同名属性只留第一条（原文里会有重复列）。

产出**七键**对象（键集见 `database/core/objects.py` 的 `OBJECT_KEYS`），记录按同处的
`ATTR_KEYS` 建（`objects_mod.record`）。**本库在这里算的两样**：

* `type` —— 原文的 Attributes 表只有"属性名 | 说明"两列，**没有类型列**，类型是
  从**该类自己的说明**里推的（`_type_from_desc`，推不出就是 `None`）。这是弱信号，
  所以记录里同时留着 `desc`（推它所依据的原文），读得出这个类型是怎么来的；
* `kind` —— 恒 `attr`（本库收录的只有属性）。`rw` 原文没有读写列，恒 `None`。

`desc` 存全、不截断（截断是渲染列的事）。上游 `parse.py`，下游 `index.py`。
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import objects as objects_mod

# 表首列里这些词不是属性名（它们出现在表头、`Note:` 行等处）。**这张表是脆的**：
# 真要吃准，应该换成"位置规则"（表头行、`include` 行按位置认）——db 那边就是那么做的，
# 而这里本文档实测无误伤，故暂不动。
_NOISE = {"attribute", "note", "include", "modify", "object", "the"}


def _is_name_token(tok: str) -> bool:
    """表首列像不像属性名。

    **形状偏脆**：`^[a-z]` 拒大写开头的名字、`_NOISE` 是词表——两者都可能误伤（`db` 那边
    就吃过亏：`DBUPerUU` 与 `value` 被吃掉）。本文档里实测无误伤，故暂不动；真要改，
    应先把 `_NOISE` 换成"位置规则"（表头行、`include` 行按位置认）再动正则。
    """
    return bool(re.match(r'^[a-z][a-zA-Z0-9]*$', tok)) and tok.lower() not in _NOISE


def _type_from_desc(desc: str) -> str | None:
    """从**该类自己的说明文字**里推类型；推不出返回 `None`。

    这是本库的弱信号——原文没有类型列（见模块说明）。它是**本库的推法**，算完落在记录
    里，所以**改了规则就要抬载荷版本号并重建**。
    """
    d = (desc or "").lower()
    if "list of database identifiers" in d or "list of database ids" in d:
        return "l_objId"
    if "the database identifier" in d:
        return "objId"
    if "list of " in d and ("names" in d or "layers" in d or "purposes" in d):
        return "l_string"
    if any(k in d for k in ("true or false", "t or nil", "flag", "whether ")):
        return "boolean"
    if "name of the " in d:
        return "string"
    return None


def _class_id(heading: str) -> str:
    """小节标题 → 类名（`techID~>viaDefs (含尾注)` → `viaDefs`）。"""
    cid = heading.replace("techID~>", "").rstrip("~> ").strip()
    cid = re.sub(r'\s*\(.*?\)\s*$', '', cid).strip()
    return cid or "techID"


def _merge_continuations(rows: list[list[str]]) -> list[dict]:
    """把 Attributes 表的格子读成属性记录：认名字格、把折行的说明并回上一条。"""
    attrs, pending = [], None
    for tds in rows:
        first = tds[0].lstrip('*')
        if _is_name_token(first):
            if pending:
                attrs.append(pending)
            pending = {"name": first,
                       "desc": re.sub(r'\s+', ' ', ' '.join(tds[1:])).strip()}
        else:
            # 说明折行成的续行：并进上一条（仅当上一条还没有说明）
            if pending and not pending["desc"]:
                pending["desc"] = re.sub(r'\s+', ' ', ' '.join(tds)).strip()
    if pending:
        attrs.append(pending)
    return attrs


def decorate(raw: dict) -> dict:
    """② **归一**：只留 `techID~>` 类，读成统一载荷。

    `desc` 取原文自己的 `Description` 小节，不是手写的类说明。
    """
    objects: dict[str, dict] = {}
    for sec in raw["sections"]:
        heading = sec["heading"]
        if not heading.startswith("techID~>"):
            continue
        cid = _class_id(heading)
        seen: dict[str, dict] = {}
        for a in _merge_continuations(sec["rows"]):
            seen.setdefault(a["name"], a)
        objects[cid] = {
            "id": cid,
            "title": "techID~>" if cid == "techID" else f"techID~>{cid}",
            "runtime": None,          # 本库原文不报运行时名
            "section": None,          # 本附录里没有更有用的分组（类就是 h3 本身）
            "desc": sec["description"],         # 原文自己的 Description 小节，存全
            "parent": None,           # 本库原文没有继承：全是根节点
            "attrs": [objects_mod.record(a["name"], kind="attr",
                                         type=_type_from_desc(a["desc"]),
                                         desc=a["desc"] or None)
                      for a in seen.values()],
        }
    return {"objects": objects}
