#!/usr/bin/env python3
"""设计库：解析 + 检索（断言式）：`database/db/core/catalog.py`。

设计见 `src/knowledge_virtuoso/database/db/core/README.md`。本文件锁三类东西：

- **检索**：选择器怎么认（表标题／运行时名／忽略大小写与空格／兼容别名）、继承怎么合
  （子覆盖父、`definedIn` 记归属）。载荷是 `fixtures/search.json`（**手写**，不引厂商原文）。
- **片段回放**：`fixtures/html/` 的官方 doc 片段 —— 比"片段 ⇒ 对象"与"整份文件 ⇒
  同一个对象"是否一致（切片边界、两种父写法都在这露头）。
- **用自造 HTML 钉住那些"一坏就是几十条属性静默消失"的形状**：`include` 的三种拼法、
  `<br>` 的两种含义、大写开头的属性名、以及 `name`/`value` 这种**曾被噪声词表吃掉**的名字。

不读真索引、不需要 doc：载荷手写，片段随仓库。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.db.core import catalog  # noqa: E402

# ── 自造 HTML ──────────────────────────────────────────────
_HEADER = "<tr><td>Attribute</td><td>Modify</td><td>Type</td><td>Description</td></tr>"


def _row(name_html: str, modify: str, typ: str, desc: str = "") -> str:
    return (f"<tr><td><p><a>{name_html}</a></p></td><td><p><a>{modify}</a></p></td>"
            f"<td><p><a>{typ}</a></p></td><td><p><a>{desc}</a></p></td></tr>")


def _include(name: str, word: str = "include") -> str:
    """表里的父指针行 —— 原文有 `include` / `Includes` / `includes` 三种写法。"""
    return f"<tr><td><p><a>Note: {word} {name} Attributes</a></p></td></tr>"


def _obj(name: str, *rows: str, pre: str = "", section: str = "节") -> str:
    """一个对象 = `<h4>X Attributes</h4>` + （可选前导正文）+ 第一张表。"""
    return (f"<h3>{section}</h3><h4><a>{name} Attributes</a></h4>{pre}"
            f"<table>{_HEADER}{''.join(rows)}</table>")


def _parse(html: str) -> dict:
    """把自造 HTML 写成文件喂给 `extract_all`（它收路径），返回对象表。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "attrib.html"
        path.write_text("<html><body>" + html + "</body></html>", encoding="utf-8")
        return catalog.extract_all(str(path))["objects"]


def _objects() -> dict:
    """`fixtures/search.json` 里的手写对象表（供纯函数断言用，不碰磁盘索引）。"""
    return read_json(HERE / "fixtures" / "search.json")["payload"]["objects"]


def run(report: Report, update: bool = False) -> None:
    # ── 检索：手写载荷 → 选择器与合并 ──
    run_attr_search_cases(HERE, catalog, "search_attr", report)

    # ── 片段回放：官方 doc 的片段 → 该对象的父与自身属性 ──
    run_attr_parse_cases(HERE, "db", catalog, report)
    report.expect("片段/夹具齐全（少一份就少一处的覆盖）",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["section_cellview", "section_inst", "shape_pathSeg", "shape_rect_note_only"])

    # ── 对象 id：去掉 ` Attributes`；原文 `Standard viaVariant . Attributes` 的尾巴也去掉 ──
    report.expect("解析/对象 id 去掉后缀",
                  [catalog._object_id("Marker Attributes"), catalog._object_id("Standard viaVariant . Attributes")],
                  ["Marker", "Standard viaVariant"])

    # ── 名字格里的 <br>：折行 vs 一行两名 ──
    report.expect("解析/<br> 折行算一个名字",
                  catalog._names_in_cell(["modifiedButNot", "Saved"]), ["modifiedButNotSaved"])
    report.expect("解析/<br> 一行两名算两个",
                  catalog._names_in_cell(["startConn", "endConn"]), ["startConn", "endConn"])

    # ── 父指针的三种拼法 + 那处 `include s` 笔误 ──
    report.expect("解析/父指针认大小写与单复数、容忍笔误",
                  [catalog._parent_from("Note: include Generic Object Attributes"),
                   catalog._parent_from("Note: Includes Generic Object Attributes ."),
                   catalog._parent_from("Note: includes Generic Object Attributes"),
                   catalog._parent_from("Note: include s Generic Object Attributes"),
                   catalog._parent_from("这里没有父指针")],
                  ["Generic Object"] * 4 + [None])

    # ── 端到端（自造）：根 / 前导正文里的父 / 表里的父 / 曾被噪声词吃掉的名字 ──
    html = (
        _obj("Generic Object", _row("cellView", "no", "objId", "c"),
             _row("name", "no", "string", "n"), _row("value", "no", "string", "v")),
        # 父指针写在小节正文里（原文 4 张 widthSpacing 表就是这么写的），且用 `Includes`
        _obj("Generic Shape", _row("layerName", "yes", "string", "l"),
             pre="<p><strong>Note: </strong>Includes <a>Generic Object Attributes</a>.</p>"),
        _obj("Rectangle", _include("Generic Shape")),          # 自身 0 条，全靠继承
        _obj("Foo", _include("Generic Shape"),
             _row("modifiedButNot<br>Saved", "no", "Boolean", "x"),
             _row("DBUPerUU", "yes", "float", "d"),
             _row("layerName", "no", "string", "子覆盖父：改读写")),
    )
    objects = _parse("".join(html))
    report.expect("解析/只认 h4 级 `… Attributes`，共 4 个对象",
                  sorted(objects), ["Foo", "Generic Object", "Generic Shape", "Rectangle"])
    report.expect("解析/父指针：根 / 正文里的 / 表里的",
                  [objects["Generic Object"]["parent"], objects["Generic Shape"]["parent"],
                   objects["Rectangle"]["parent"], objects["Foo"]["parent"]],
                  [None, "Generic Object", "Generic Shape", "Generic Shape"])

    merged = objects_mod.merged(objects, "Foo")
    report.expect("解析/继承合并后拿到整条链上的属性（含曾被噪声词吃掉的 name/value）",
                  sorted(merged), ["DBUPerUU", "cellView", "layerName", "modifiedButNotSaved", "name", "value"])
    report.expect("解析/纯转发对象自身 0 条，合并后 4 条",
                  (len(objects["Rectangle"]["attrs"]), len(objects_mod.merged(objects, "Rectangle"))), (0, 4))
    report.expect("解析/子覆盖父：Foo 的 layerName 取代 Shape 的",
                  (merged["layerName"]["modify"], merged["layerName"]["definedIn"],
                   merged["cellView"]["definedIn"]),
                  ("no", "Foo", "Generic Object"))

    # ── 构建期校验：父认不出 / 成环都要炸，不许静默 ──
    for label, bad in [("父不在索引里", {"A": {"id": "A", "parent": "Nope", "attrs": []}}),
                       ("继承链成环", {"A": {"id": "A", "parent": "B", "attrs": []},
                                   "B": {"id": "B", "parent": "A", "attrs": []}})]:
        try:
            objects_mod.validate_objects(bad)
            report.truthy(f"校验/{label} → 抛错", False, "没有抛错")
        except ValueError:
            report.truthy(f"校验/{label} → 抛错", True)

    # ── 选择器：表标题 / 运行时名 / 忽略大小写与空格 / 兼容别名 / 不认识 ──
    objs = _objects()
    report.expect("检索/选择器解析的几条路径",
                  [objects_mod.resolve(objs, "Cellview"), objects_mod.resolve(objs, "cellview"),
                   objects_mod.resolve(objs, "CELLVIEW"), objects_mod.resolve(objs, "rect", catalog._ALIASES),
                   objects_mod.resolve(objs, "Rectangle"), objects_mod.resolve(objs, "没有这个")],
                  ["Cellview", "Cellview", "Cellview", "Rectangle", "Rectangle", None])


if __name__ == "__main__":
    report = Report("database/db/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
