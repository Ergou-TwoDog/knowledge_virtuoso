#!/usr/bin/env python3
"""属性库共用的对象模型：`database/core/objects.py`。

四个库的载荷是同一套（对象层 `OBJECT_KEYS` + 记录层 `ATTR_KEYS`），"谁与谁共享什么"由
这个模块承担，所以它自己的行为要单独钉住——四库各自的 `test_index.py` 只覆盖"我这一库
能不能正确用上它"，查询机制本身在 `test_query.py`。

这里锁五件：**校验的不变量**、**记录的构造**（键集全给、空缺补 `null`、写错键名当场炸）、
**选择器的解析次序**、**继承合并（含"无父即自身"的塌缩）**、**名字→声明它的对象**。
不读索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.core.objects import ATTR_KEYS, record  # noqa: E402


def _attr(name: str, **kw) -> dict:
    """一条**记录**：键集全给（`ATTR_KEYS`），没写的一律 `null`——校验只认这个形状。"""
    return record(name, kind="attr", **kw)


def _obj(oid: str, attrs, parent=None, **kw) -> dict:
    """七键对象：`validate_objects` 管键集，构造器必须给全（缺一个键就该炸）。"""
    return {"id": oid, "title": oid, "runtime": None, "section": None, "desc": None,
            "parent": parent, "attrs": attrs, **kw}


def run(report: Report, update: bool = False) -> None:
    # ── 记录的构造：键集、顺序、补 null ──
    report.expect("构造/没写的键补 null，且照 ATTR_KEYS 的顺序落（顺序即落盘字节）",
                  tuple(record("x")), ATTR_KEYS)
    report.expect("构造/写了的键原样留着（原文那一侧与推的那一侧并存）",
                  {k: v for k, v in record("x", kind="relation", cardinality="1:n",
                                           modify="no").items()
                   if v is not None},
                  {"name": "x", "kind": "relation", "cardinality": "1:n", "modify": "no"})
    try:
        record("x", 拼错了="v")
        report.truthy("构造/写错键名 → 抛错", False, "没有抛错")
    except ValueError as exc:
        report.truthy("构造/写错键名 → 抛错（不许静默多出一个没人读的字段）",
                      "拼错了" in str(exc), str(exc))

    # ── 顶层：三键，且 `lib` 必须与它所在的库一致（类型区分字段）──
    def _pbad(payload: dict, lib: str) -> bool:
        try:
            objects_mod.validate_payload(payload, lib)
            return False
        except ValueError:
            return True

    report.expect("顶层/键集固定（顺序即落盘顺序）",
                  objects_mod.PAYLOAD_KEYS, ("version", "lib", "objects"))
    good = {"version": 5, "lib": "db", "objects": {"a": _obj("a", [_attr("x")])}}
    report.expect("顶层/干净的一份通过", _pbad(good, "db"), False)
    report.expect("顶层/少一个键要抛错",
                  _pbad({"lib": "db", "objects": good["objects"]}, "db"), True)
    report.expect("顶层/多一个键要抛错", _pbad({**good, "多出来的": 1}, "db"), True)
    report.expect("顶层/lib 与它所在的库不符要抛错（索引放错目录了？）",
                  _pbad({**good, "lib": "dd"}, "db"), True)

    # ── 构建期不变量 ──
    def _bad(objects: dict) -> bool:
        try:
            objects_mod.validate_objects(objects)
            return False
        except ValueError:
            return True

    report.expect("校验/干净的对象表通过",
                  _bad({"a": _obj("a", [_attr("x")])}), False)
    report.expect("校验/属性名可以用大写开头（原文里 DBUPerUU 是合法属性名）",
                  _bad({"a": _obj("a", [_attr("DBUPerUU")])}), False)
    report.expect("校验/对象 id 可以是带空格的表标题（db 那家就是这样）",
                  _bad({"Generic Object": _obj("Generic Object", [_attr("x")])}), False)
    report.expect("校验/对象内属性名重复要抛错",
                  _bad({"a": _obj("a", [_attr("x"), _attr("x")])}), True)
    report.expect("校验/属性名形状不对要抛错",
                  _bad({"a": _obj("a", [_attr("9bad")])}), True)
    report.expect("校验/父对象不在表里要抛错",
                  _bad({"a": _obj("a", [_attr("x")], parent="没有这个")}), True)
    report.expect("校验/继承链成环要抛错",
                  _bad({"a": _obj("a", [_attr("x")], parent="b"),
                        "b": _obj("b", [_attr("y")], parent="a")}), True)
    report.expect("校验/**空的属性表是合法的**（db 的纯转发对象自身就是 0 条）",
                  _bad({"Rectangle": _obj("Rectangle", [])}), False)
    # 两层键集各一条：这是**唯一同时看见四库载荷**的地方，缺项必须在这儿炸
    report.expect("校验/对象键集不全要抛错",
                  _bad({"a": {"id": "a", "title": "a", "attrs": [_attr("x")]}}), True)
    report.expect("校验/记录键集不全要抛错",
                  _bad({"a": _obj("a", [{k: v for k, v in _attr("x").items() if k != "rw"}])}),
                  True)
    report.expect("校验/记录里多出一个没定义的键也要抛错",
                  _bad({"a": _obj("a", [{**_attr("x"), "拼错了": 1}])}), True)

    # ── 选择器解析：精确 → 运行时名 → 忽略大小写与空格 → 别名 ──
    objs = {"Generic Shape": _obj("Generic Shape", [_attr("layerName")], runtime="shape"),
            "Marker": _obj("Marker", [_attr("severity")])}
    report.expect("解析/四条路径与认不出",
                  [objects_mod.resolve(objs, "Marker"),
                   objects_mod.resolve(objs, "shape"),                  # 原文自报的运行时名
                   objects_mod.resolve(objs, "generic  shape"),         # 忽略大小写与空格
                   objects_mod.resolve(objs, "mark", {"mark": "Marker"}),  # 别名
                   objects_mod.resolve(objs, "没有这个")],
                  ["Marker", "Generic Shape", "Generic Shape", "Marker", None])
    report.expect("解析/空格与下划线一视同仁（dd 用上共用件后因此多认一种写法）",
                  [objects_mod.resolve(objs, "generic_shape"),
                   objects_mod.resolve({"libFile": _obj("libFile", [])}, "lib file")],
                  ["Generic Shape", "libFile"])
    report.expect("解析/空选择器返回 None（「没给」与「认不出」分开）",
                  objects_mod.resolve(objs, ""), None)
    report.expect("解析/没有 runtime 字段的库跳过这一步（techdb/cdfdb/dd 就是）",
                  objects_mod.runtime_matches({"layers": _obj("layers", [])}, "layers"), None)

    # ── 继承合并：子覆盖父、记 definedIn、无父塌缩成自身 ──
    tree = {"Root": _obj("Root", [_attr("a", type="1"), _attr("b")]),
            "Leaf": _obj("Leaf", [_attr("b", type="2"), _attr("c")], parent="Root")}
    merged = objects_mod.merged(tree, "Leaf")
    report.expect("合并/子先到先占（子覆盖父），并记下每条来自哪一层",
                  [(n, merged[n].get("type"), merged[n]["definedIn"]) for n in sorted(merged)],
                  [("a", "1", "Root"), ("b", "2", "Leaf"), ("c", None, "Leaf")])
    flat = {"only": _obj("only", [_attr("x"), _attr("y")])}
    report.expect("合并/**没有父时塌缩成自身**（另两库全靠这一步，不需要特判）",
                  sorted(objects_mod.merged(flat, "only")), ["x", "y"])
    report.expect("合并/塌缩后 definedIn 全指向自己",
                  {v["definedIn"] for v in objects_mod.merged(flat, "only").values()}, {"only"})

    # ── 名字 → 声明它的对象（表里有"所属对象"列的行靠它）──
    d = objects_mod.declared_in({"a": _obj("a", [_attr("x")]),
                                 "b": _obj("b", [_attr("x"), _attr("y")])})
    report.expect("归属/同一个名字在多个对象里各记一笔", (d["x"], d["y"]), (["a", "b"], ["b"]))


if __name__ == "__main__":
    report = Report("database/core/test_objects")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
