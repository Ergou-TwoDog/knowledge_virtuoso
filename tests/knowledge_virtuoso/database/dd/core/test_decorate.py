#!/usr/bin/env python3
"""② **归一**：`database/dd/core/decorate.py`。

**与 src 一一对应**（见 `test_parse.py` 的表）。这一层测的是"**哪张表是哪张、格子怎么读、
摊到谁名下**"：

- `fixtures/html/` 的官方 doc 整节回放——比"这一节 ⇒ 六个对象各自的记录名"是否一致
  （那正是**物化**这一步要保证的）；
- 自造 HTML 钉住：**靠表头签名**在四张表里挑对两张（运算符图例、类型图例跳过）、
  空格子 = 不适用、关系的基数取到了、对象全集取自**枚举得最全的关系行**、
  **每条记录落到它适用的每个对象下**；
- **不静默**：某条记录的适用对象不在对象全集里 → 构建期就炸（摊平之后 ③ 看不见它，
  所以这条必须在这里拦）。

**③ 的事不在这**：选择器解析（四库共用的 `objects.resolve`）、容器级校验与版本号都在
`../test_index.py`。所以这里给的入口是 `decorate ∘ parse` 本身，不 import ③。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases  # noqa: E402

from knowledge_virtuoso.database.core.objects import ATTR_KEYS  # noqa: E402
from knowledge_virtuoso.database.dd.core.decorate import decorate  # noqa: E402
from knowledge_virtuoso.database.dd.core.parse import parse  # noqa: E402

# 与原文同形：四张表（运算符图例 / 类型图例 / 属性表 / 关系表），靠表头签名挑。
# `lib` 那行把 6 个对象列全（原文里它和 `parent` 就是这么写的），对象全集与顺序从这儿来。
_SYNTHETIC = (
    '<h2>Attributes of Data Management Objects</h2>'
    '<table><tr><td>(~&gt;)</td><td>To access any attribute</td></tr>'
    '<tr><td>(~&gt;?)</td><td>To see names</td></tr></table>'
    '<table><tr><td>b</td><td>a DDPI object</td></tr>'
    '<tr><td>d</td><td>an identifier</td></tr></table>'
    '<table>'
    '<tr><td>Attribute Names</td><td colspan="6">Object Types Attribute is Valid For</td></tr>'
    '<tr><td>group</td><td>libFile</td><td>cellFile</td><td>viewFile</td></tr>'
    '<tr><td>prop</td><td>lib</td><td>cell</td><td>view</td></tr>'
    '</table>'
    '<table>'
    '<tr><td>Relation names</td><td>Relationship</td><td colspan="6">Object Types</td></tr>'
    '<tr><td>cells</td><td>1:n</td><td>lib</td></tr>'
    '<tr><td>lib</td><td>1:1</td><td>lib</td><td>cell</td><td>view</td>'
    '<td>libFile</td><td>cellFile</td><td>viewFile</td></tr>'
    '<tr><td>view</td><td>1:1</td><td>libFile</td></tr>'
    '</table>'
    '<h2>下一个小节</h2>'
)


def _entry(doc_path: str) -> dict:
    """② 的入口 = ① 之后接 ②（③ 里的 `extract_all` 就是这个组合，测试自己给一份）。"""
    return decorate(parse(doc_path))


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 ②（入口收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "chap3.html"
        path.write_text(html, encoding="utf-8")
        return _entry(str(path))


def _record(payload: dict, name: str) -> dict:
    """跨对象找一个记录（同一条记录会挂在多个对象下，取到哪份都一样）。"""
    for obj in payload["objects"].values():
        for rec in obj["attrs"]:
            if rec["name"] == name:
                return rec
    raise AssertionError(f"没有这条记录：{name}")


def _owners(payload: dict, name: str) -> list[str]:
    """这条记录挂在哪些对象下。"""
    return sorted(oid for oid, obj in payload["objects"].items()
                  if any(r["name"] == name for r in obj["attrs"]))


def run(report: Report, update: bool = False) -> None:
    # ── 片段回放：官方 doc 的整节 → 六个对象各自的记录名 ──
    run_attr_parse_cases(HERE, "dd", _entry, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["dd_section"])

    # ── 自造片段：靠表头签名在四张表里挑对两张，图例表跳过 ──
    payload = parse_synthetic(_SYNTHETIC)
    names = sorted({r["name"] for o in payload["objects"].values() for r in o["attrs"]})
    report.expect("解析/属性表与关系表按表头签名认出，图例表不进结果（(～>) 与 b 都不在）",
                  names, ["cells", "group", "lib", "prop", "view"])
    report.expect("解析/kind 按来自哪张表分",
                  sorted(n for n in names if _record(payload, n)["kind"] == "relation"),
                  ["cells", "lib", "view"])
    report.expect("解析/对象全集取自**枚举得最全的关系行**（lib 那行把六个列全）",
                  list(payload["objects"]),
                  ["lib", "cell", "view", "libFile", "cellFile", "viewFile"])

    # ── 物化：每条记录落到它适用的每个对象下；空格子 = 不适用 ──
    report.expect("解析/group 只落在三个 *File 对象下（原文那一行的空格子 = 不适用）",
                  _owners(payload, "group"), ["cellFile", "libFile", "viewFile"])
    report.expect("解析/prop 只落在 lib / cell / view 下",
                  _owners(payload, "prop"), ["cell", "lib", "view"])
    report.expect("解析/关系行的基数也随记录一起摊下去了",
                  [(n, _record(payload, n)["cardinality"]) for n in ("cells", "lib", "view")],
                  [("cells", "1:n"), ("lib", "1:1"), ("view", "1:1")])
    report.expect("解析/记录里留着原文的那句话：适用对象是哪些",
                  _record(payload, "group")["objectTypes"], ["libFile", "cellFile", "viewFile"])

    # ── ② 把话说全：记录按 ATTR_KEYS 建，本库只填得进四样，其余是 None（原文没有）──
    report.expect("载荷/记录按 ATTR_KEYS 建（② 把话说全，四库同形）",
                  sorted({k for o in payload["objects"].values() for r in o["attrs"] for k in r}),
                  sorted(ATTR_KEYS))
    report.expect("载荷/属性的 cardinality 是 None、关系的才有基数（原文那列只在关系表里）",
                  [(n, _record(payload, n)["cardinality"]) for n in ("group", "prop", "cells")],
                  [("group", None), ("prop", None), ("cells", "1:n")])
    report.expect("载荷/type 与 desc 全 None（原文只有「名字 | 适用对象」两列）",
                  sorted({(r["type"], r["desc"]) for o in payload["objects"].values()
                          for r in o["attrs"]}), [(None, None)])

    # ── 不静默：某条记录的适用对象不在对象全集里 → 构建期炸 ──
    # （把 `lib` 那行收窄到四个对象，于是 group 名下的 cellFile / viewFile 无处可挂。）
    narrowed = _SYNTHETIC.replace(
        '<td>lib</td><td>cell</td><td>view</td><td>libFile</td><td>cellFile</td><td>viewFile</td>',
        '<td>lib</td><td>cell</td><td>view</td><td>libFile</td>')
    try:
        parse_synthetic(narrowed)
        report.truthy("解析/适用对象不在对象全集里 → 抛错", False, "没有抛错")
    except ValueError as exc:
        report.truthy("解析/适用对象不在对象全集里 → 抛错（不静默丢掉那条记录）",
                      "group" in str(exc), str(exc))


if __name__ == "__main__":
    report = Report("database/dd/core/test_decorate")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
