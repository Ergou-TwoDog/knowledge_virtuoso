#!/usr/bin/env python3
"""② **归一**：`database/db/core/decorate.py`。

**与 src 一一对应**（见 `test_parse.py` 的表）。这一层测的是"格子的**意思**"：

- `fixtures/html/` 的官方 doc 片段回放——比"片段 ⇒ 对象"与"整份文件 ⇒ 同一个对象"
  是否一致（切片边界、表内/表前两种父写法都在这露头）；
- 自造 HTML 钉住那些"一坏就是几十条属性静默消失"的形状：`include` 的三种拼法、
  `<br>` 的两种含义、大写开头的属性名、曾被噪声词表吃掉的 `name`/`value`；
- **② 把话说全**：记录按 `ATTR_KEYS` 建，原文的 `modify` 列与推出来的 `rw` **并存**
  （推法改了要抬载荷版本号并重建，所以在这里钉住）；
- 构建期校验：父认不出、继承链成环都要炸。

**③ 的事不在这**：继承合并（`merged`）与选择器解析在 `../test_index.py`——那边跑在
`fixtures/search.json` 的手写载荷上。查询机制本身在 `core/test_query.py`。
所以这里给入口是 `decorate ∘ parse` 本身，不 import ③。

不读真索引、不需要 doc：片段随仓库，自造 HTML 现写。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.core.objects import ATTR_KEYS  # noqa: E402
from knowledge_virtuoso.database.db.core.decorate import (  # noqa: E402
    decorate, _names_in_cell, _object_id, _parent_from, _rw_from_modify)
from knowledge_virtuoso.database.db.core.parse import parse  # noqa: E402

# ── 自造 HTML ──────────────────────────────────────────────
_HEADER = "<tr><td>Attribute</td><td>Modify</td><td>Type</td><td>Description</td></tr>"


def _entry(doc_path: str) -> dict:
    """② 的入口 = ① 之后接 ②（③ 里的 `extract_all` 就是这个组合，测试自己给一份）。"""
    return decorate(parse(doc_path))


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
    """把自造 HTML 写成文件喂给 ②（入口收路径），返回对象表。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "attrib.html"
        path.write_text("<html><body>" + html + "</body></html>", encoding="utf-8")
        return _entry(str(path))["objects"]


def run(report: Report, update: bool = False) -> None:
    # ── 片段回放：官方 doc 的片段 → 该对象的父与自身属性记录 ──
    run_attr_parse_cases(HERE, "db", _entry, report)
    report.expect("片段/夹具齐全（少一份就少一处的覆盖）",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["section_cellview", "section_inst", "shape_pathSeg", "shape_rect_note_only"])

    # ── 对象 id：去掉 ` Attributes`；原文 `Standard viaVariant . Attributes` 的尾巴也去掉 ──
    report.expect("解析/对象 id 去掉后缀",
                  [_object_id("Marker Attributes"),
                   _object_id("Standard viaVariant . Attributes")],
                  ["Marker", "Standard viaVariant"])

    # ── 名字格里的 <br>：折行 vs 一行两名 ──
    report.expect("解析/<br> 折行算一个名字",
                  _names_in_cell(["modifiedButNot", "Saved"]), ["modifiedButNotSaved"])
    report.expect("解析/<br> 一行两名算两个",
                  _names_in_cell(["startConn", "endConn"]), ["startConn", "endConn"])

    # ── 父指针的三种拼法 + 那处 `include s` 笔误 ──
    report.expect("解析/父指针认大小写与单复数、容忍笔误",
                  [_parent_from("Note: include Generic Object Attributes"),
                   _parent_from("Note: Includes Generic Object Attributes ."),
                   _parent_from("Note: includes Generic Object Attributes"),
                   _parent_from("Note: include s Generic Object Attributes"),
                   _parent_from("这里没有父指针")],
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
    report.expect("解析/自身属性记录：折行名拼回一个、大写开头保留、曾被噪声词吃掉的 name/value 都在",
                  sorted((a["name"], a["modify"])
                         for oid in ("Foo", "Generic Object") for a in objects[oid]["attrs"]),
                  sorted([("modifiedButNotSaved", "no"), ("DBUPerUU", "yes"),
                          ("layerName", "no"), ("cellView", "no"),
                          ("name", "no"), ("value", "no")]))

    # ── ② 把话说全：记录按 ATTR_KEYS 建；原文的 `modify` 与推出来的 `rw` 并存 ──
    report.expect("载荷/记录按 ATTR_KEYS 建（② 把话说全，四库同形）",
                  sorted({k for a in objects["Foo"]["attrs"] for k in a}), sorted(ATTR_KEYS))
    report.expect("载荷/原文的 Modify 列与推出来的 rw 并存（子覆盖父时改读写也看得见）",
                  [(a["name"], a["modify"], a["rw"]) for a in objects["Foo"]["attrs"]],
                  [("modifiedButNotSaved", "no", "ro"), ("DBUPerUU", "yes", "rw"),
                   ("layerName", "no", "ro")])
    report.expect("推法/_rw_from_modify（原文三态：no / yes / no/yes）",
                  [_rw_from_modify(m) for m in ("no", "yes", "no/yes", "NO", None)],
                  ["ro", "rw", "rw", "ro", "ro"])

    # ── 构建期校验：父认不出 / 成环都要炸，不许静默 ──
    # 对象给**齐七键**：缺键本来就会炸（另一条断言管那个），那就测不出这两条了。
    # （名字避开模块级的 `_obj`——那个造的是 HTML。）
    def _obj7(oid: str, parent: str | None) -> dict:
        return {"id": oid, "title": oid, "runtime": None, "section": None,
                "desc": None, "parent": parent, "attrs": []}

    for label, bad in [("父不在索引里", {"A": _obj7("A", "Nope")}),
                       ("继承链成环", {"A": _obj7("A", "B"), "B": _obj7("B", "A")})]:
        try:
            objects_mod.validate_objects(bad)
            report.truthy(f"校验/{label} → 抛错", False, "没有抛错")
        except ValueError:
            report.truthy(f"校验/{label} → 抛错", True)


if __name__ == "__main__":
    report = Report("database/db/core/test_decorate")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
