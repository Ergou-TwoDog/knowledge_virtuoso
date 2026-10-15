#!/usr/bin/env python3
"""
knowledge_virtuoso.database.cdfdb.core.decorate — ② **归一**：把文档结构读成统一载荷。

①（`parse.py`）给的是"每个 h4 小节里有什么"，这一层回答"**它们属于谁**"：

* **手写白名单**（`_DATA_FIELDS`/`_PARAM_FIELDS`）把 h4 归到两个 SKILL 对象类下——
  `g_cdfDataId`（描述对象）与 `g_cdfParamId`（参数对象）。白名单是**我们**的判断，
  所以在这一层；
* `cdfDataId` 的 `Displaying Parameters` 表按名字形状挑行；
* 两条**不在字段区**的属性（`name`/`description`）只有 `cdfCreateParam` 的实参形式，
  由 `SUPPLEMENT_PARAM_ATTRS` 补进来并标 `source: "arg"`——它们**不是原文的结构**，
  所以 ① 不掺和，从这里补。

产出**七键**对象（键集见 `database/core/objects.py` 的 `OBJECT_KEYS`），记录按同处的
`ATTR_KEYS` 建（`objects_mod.record`）。**本库在这里算的两样**（原文既没有类型列、也没有
读写列，两者都是推的）：

* `type` —— 按名字优先、说明兜底（`_type_from_name_desc`），推不出就是 `None`；
* `rw` —— 从散文里的 "not editable" 推（`_rw_from_desc`）。

原文那一侧留下 `desc`（存全、不截断）与 `source`（出处）——**推法所依据的与推出来的
并存**，读得出区别。上游 `parse.py`，下游 `index.py`。
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import objects as objects_mod

# ─── 类的成员：字段区里的 h4 小节 ───
_DATA_FIELDS = ("id", "type", "parameters", "doneProc", "formInitProc")
_PARAM_FIELDS = ("use", "paramType", "defValue", "value", "prompt", "choices",
                 "units", "editable", "callback", "parseAsNumber", "dontSave",
                 "parseAsCEL", "storeDefault", "display")

# ─── 没有独立 h4 小节、只在 `cdfCreateParam` 实参里出现的属性 ───
# 说明取自原文实参表：`?name t_name The name of the parameter.`；
# `?description t_description` **原文没给说明**，所以是 `None`。
SUPPLEMENT_PARAM_ATTRS = [
    {"name": "name", "desc": "The name of the parameter.", "source": "arg"},
    {"name": "description", "desc": None, "source": "arg"},
]


def _type_from_name_desc(name: str, desc: str | None) -> str | None:
    """推类型：**按名字优先、说明兜底**；推不出 `None`。

    原文没有类型列，所以这是本库的推法。算完落在记录里，`desc` 同时留着——
    改规则要抬载荷版本号并重建。
    """
    d = (desc or "").lower()
    if name == "id":
        return "objId"
    if name == "parameters":
        return "l_objId"
    if name == "choices":
        return "l_string"
    if name in ("paramType", "type", "name", "prompt", "units", "callback"):
        return "string"
    if "list of" in d:
        return "l_string"
    return None


def _rw_from_desc(desc: str | None) -> str:
    """可编辑性写在散文里（"This field is not editable."）→ 两值的 `rw`。

    推的时候用**完整的说明**，不能只看开头那段——这正是 `desc` 存全不截断的原因
    （曾经截断过一次，"not editable" 那句被截掉，推出来的 `rw` 因此无据可依）。
    """
    return "ro" if "not editable" in (desc or "").lower() else "rw"


def decorate(raw: dict) -> dict:
    """② **归一**：按手写白名单把 h4 小节归到两个 SKILL 类下，读成统一载荷。"""
    fields = raw["fields"]

    def _field(fieldname: str) -> dict | None:
        """一个字段小节的记录：`{name, desc, source, section}`（**说明存全，不截断**）。"""
        found = fields.get(fieldname)
        if not found:
            return None
        return {"name": fieldname, "desc": found["text"],
                "source": "field", "section": found["section"]}

    def _display_rows() -> list[dict]:
        """`Displaying Parameters` 表里的行（fieldWidth 等）。"""
        found = fields.get("Displaying Parameters")
        if not found:
            return []
        out = []
        for tds in found["rows"]:
            if not re.match(r'^[a-z][a-zA-Z]+$', tds[0]):
                continue
            out.append({"name": tds[0], "desc": ' '.join(tds[1:]),
                        "source": "field", "section": found["section"]})
        return out

    def _record(attr: dict) -> dict:
        """一条记录（`ATTR_KEYS`）：原文的 `desc`/`source` 与推出来的 `type`/`rw` 并存。"""
        desc = attr.get("desc") or None
        return objects_mod.record(attr["name"], kind="attr",
                                  type=_type_from_name_desc(attr["name"], desc),
                                  rw=_rw_from_desc(desc), desc=desc,
                                  source=attr.get("source", "field"))

    data_attrs = [f for f in (_field(fn) for fn in _DATA_FIELDS) if f]
    data_attrs.extend(_display_rows())

    param_attrs = [f for f in (_field(fn) for fn in _PARAM_FIELDS) if f]
    param_attrs.extend(dict(a) for a in SUPPLEMENT_PARAM_ATTRS)   # 手写补录，见模块说明

    def _object(cid: str, title: str, attrs: list[dict]) -> dict:
        return {"id": cid,
                "title": title,          # 原文对这个对象的称呼（`g_cdfDataId` 是它的运行时名）
                "runtime": None,         # 本库不单列运行时名，原文的称呼就在 title 里
                "section": (attrs[0].get("section") or None) if attrs else None,  # 字段所属 h3
                "desc": None,            # 原文没有对象级说明
                "parent": None,          # 本库原文没有继承：全是根节点
                "attrs": [_record(a) for a in attrs]}

    return {"objects": {
        "cdfDataId": _object("cdfDataId", "g_cdfDataId", data_attrs),
        "cdfParamId": _object("cdfParamId", "g_cdfParamId", param_attrs),
    }}
