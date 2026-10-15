#!/usr/bin/env python3
"""
knowledge_virtuoso.database.dd.core.decorate — ② **归一**：把文档结构读成载荷。

①（`parse.py`）给的是"这一节里有哪几张表、每张表有哪些格子"，这一层回答"**哪张是哪张、
格子怎么读**"：

* **按表头签名挑表**——同节四张表里，属性表的首格是 `Attribute Names`、关系表的首格是
  `Relation names`（运算符图例与类型图例靠这个避掉）。位置会随排版变，表头不会；
* **对象全集与顺序**取"枚举得最全的那些关系行"（原文里 `lib` 与 `parent` 把 6 个对象
  依次列全）——属性表的 6 个适用列**没有列名**，顺序只能从这儿来；
* 关系多一列**基数**（原文只有 `1:1` 与 `1:n`）。

**这一层做的是"物化"**：原文一条记录只说一遍、后面列适用对象（转置）；这里把它**摊成
和另三个库一样的容器**——每个对象一张表，表里是适用于它的全部记录：

    {"objects": {"lib": {id, title, runtime, section, desc, parent, attrs}, …}}

记录同样按 `database/core/objects.py` 的 `ATTR_KEYS` 建（`objects_mod.record`）：本库
只填 `name`/`kind`/`cardinality`/`objectTypes` 四样，其余是 `None`——那是因为**原文没有**：
属性表只有"名字 | 适用对象"两列，没有类型列、也没有逐条说明（见 `core/README.md`）。

代价是**副本**：22 条记录摊成 6 个对象共 **74 条**（3.36×）。这么做的理由是**口径统一**——
上层（`database/index.py` 的联合、渲染的对象头、`validate_objects` 的校验）对四个库
一视同仁，代价只是几 KB 的重复；而"原文是转置的"这件事由 `core/README.md` 与
`parse.py` 如实记着，没丢。

`objectTypes` **每条都留着**：它是原文的原话（"这条适用于哪几个对象"）；行里的
「适用对象」列也才有东西可印。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import objects as objects_mod

_ATTR_HEADER = "Attribute Names"
_RELATION_HEADER = "Relation names"


def _pick(tables: list[list[list[str]]], header: str) -> list[list[str]]:
    """按**表头签名**挑表：本节里还有运算符表与类型图例表，靠表头避掉。"""
    for rows in tables:
        if rows and rows[0] and rows[0][0] == header:
            return rows[1:]
    raise ValueError(f"找不到表头为 {header!r} 的表")


def _universe(relations: dict) -> list[str]:
    """对象全集与顺序：取**枚举得最全的那些关系行**（原文里 `lib` 与 `parent` 把 6 个
    对象依次列全），并要求它们彼此一致。表 19-1 的 6 个适用列没有列名，顺序只能从这儿来。
    """
    counts = [(len(r["objectTypes"]), r) for r in relations.values()]
    if not counts:
        return []
    widest = max(n for n, _ in counts)
    full = [r["objectTypes"] for n, r in counts if n == widest]
    first = full[0]
    if any(o != first for o in full[1:]):
        raise ValueError(f"对象全集的候选行彼此不一致：{full}")
    return list(first)


def _object(oid: str, attrs: list[dict]) -> dict:
    """七键对象（键集见 `database/core/objects.py` 的 `OBJECT_KEYS`）。

    四个字段为什么是空的：原文对这六个对象**只给了名字**——没有另外的称呼（`id` 就是原文
    的叫法）、不报运行时名、没有按节分组、也没有对象级的说明。
    """
    return {"id": oid, "title": None, "runtime": None, "section": None,
            "desc": None, "parent": None,      # 本库原文没有继承：全是平铺的
            "attrs": attrs}


def decorate(raw: dict) -> dict:
    """② **归一**：挑出两张表、读出记录，再**摊到每个适用对象下**（见模块说明）。"""
    tables = raw["tables"]

    # 照原文读：一条记录只说一遍（转置的那个形状）
    records: dict[str, dict] = {}
    for cells in _pick(tables, _ATTR_HEADER):
        records[cells[0]] = objects_mod.record(cells[0], kind="attr",
                                               objectTypes=cells[1:])
    relations: dict[str, dict] = {}
    for cells in _pick(tables, _RELATION_HEADER):
        relations[cells[0]] = objects_mod.record(
            cells[0], kind="relation",
            cardinality=(cells[1] if len(cells) > 1 else None) or None,
            objectTypes=cells[2:])

    object_types = _universe(relations)
    all_records = list(records.values()) + list(relations.values())

    # 适用对象必须在全集里——**在这里查**：摊平之后 ③ 只看得到挂上去的那些，一条"只挂在
    # 全集之外"的记录会连影子都没有。宁可构建失败，也不要静默漏掉一条。
    known = set(object_types)
    for rec in all_records:
        unknown = [o for o in rec["objectTypes"] if o not in known]
        if unknown:
            raise ValueError(f"{rec['name']!r} 的适用对象不在对象全集里：{unknown}")

    objects = {oid: _object(oid, []) for oid in object_types}
    # 摊平：属性在前、关系在后（原文两张表的顺序），每条放进它适用的每个对象下
    for rec in all_records:
        for oid in rec["objectTypes"]:
            objects[oid]["attrs"].append(dict(rec))
    return {"objects": objects}
