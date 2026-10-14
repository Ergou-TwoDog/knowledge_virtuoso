#!/usr/bin/env python3
"""属性库共用的对象模型：`database/core/objects.py`。

db / techdb / cdfdb 的载荷是同一套（`{version, objects: {id: {id, title, parent, attrs}}}`），
"谁与谁共享什么"由这个模块承担，所以它自己的行为要单独钉住——三库各自的 `test_catalog.py`
只覆盖"我这一库能不能正确用上它"。

这里锁四件：**校验的不变量**、**选择器的解析次序**、**继承合并（含"无父即自身"的塌缩）**、
**名字→声明它的对象**。不读索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402


def _attr(name: str, **kw) -> dict:
    return {"name": name, **kw}


def _obj(oid: str, attrs, parent=None, **kw) -> dict:
    return {"id": oid, "title": oid, "parent": parent, "attrs": attrs, **kw}


def run(report: Report, update: bool = False) -> None:
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
    report.expect("解析/空选择器返回 None（「没给」与「认不出」分开）",
                  objects_mod.resolve(objs, ""), None)
    report.expect("解析/没有 runtime 字段的库跳过这一步（techdb/cdfdb 就是）",
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
