#!/usr/bin/env python3
"""② **归一**：`database/techdb/core/decorate.py`。

**与 src 一一对应**（见 `test_parse.py` 的表）。这一层测的是"格子的**意思**"：

- `fixtures/html/` 的官方 doc 片段回放——比"片段 ⇒ 该类"与"整份文件 ⇒ 同一个类"
  是否一致（逐条比属性记录的 `name/desc`）；
- 自造 HTML 钉住类段的语法：**类集合来自标题**（没有白名单）、类名尾注要去掉、
  名称行开新条目、续行并进上一条、表后要有下一个 h4 当边界；
- **② 把话说全**：记录按 `ATTR_KEYS` 建，本库推的那一样（`type`，从该类自己的说明里推）
  在这里算好落盘，`desc` 同时留着；`rw` 原文没有读写列，恒 `None`。推法改了必须抬
  载荷版本号并重建，所以在这里逐档钉住。

**③ 的事不在这**：选择器解析、构建期校验与版本号都在 `../test_index.py`。所以这里给入口
是 `decorate ∘ parse` 本身，不 import ③。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases  # noqa: E402

from knowledge_virtuoso.database.core.objects import ATTR_KEYS  # noqa: E402
from knowledge_virtuoso.database.techdb.core.decorate import (  # noqa: E402
    _type_from_desc, decorate)
from knowledge_virtuoso.database.techdb.core.parse import parse  # noqa: E402

_SYNTHETIC = (
    '<h3><a>techID~>viaDefs (含尾注)</a></h3>'
    '<h4><a>Description</a></h4><p>Retrieves via definitions. 手写的第二句不算数。</p>'
    '<h4><a>Attributes</a></h4><table>'
    '<tr><td>firstName</td></tr>'
    '<tr><td>This row continues the description of firstName.</td></tr>'
    '<tr><td>secondName</td><td>A list of via names.</td></tr>'
    '</table>'
    '<h4><a>Rules</a></h4><p>表后的小节，充当边界。</p>'
    # 类集合来自标题：这一节没有"白名单"挡着，它就该成为一个类
    '<h3><a>techID~>anotherClass</a></h3>'
    '<h4><a>Attributes</a></h4><table><tr><td>kept</td><td>不再被丢弃</td></tr></table>'
    '</body>'
)


def _entry(doc_path: str) -> dict:
    """② 的入口 = ① 之后接 ②（③ 里的 `extract_all` 就是这个组合，测试自己给一份）。"""
    return decorate(parse(doc_path))


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 ②（入口收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "appA.html"
        path.write_text(html, encoding="utf-8")
        return _entry(str(path))


def run(report: Report, update: bool = False) -> None:
    # ── 片段回放：官方 doc 的一个类段 → 该类的全部属性记录 ──
    run_attr_parse_cases(HERE, "techdb", _entry, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_layers", "class_viaDefs"])

    # ── 自造片段：类段语法（`<h3>` + Description / Attributes 两个 h4 小节）──
    # 表后留一个 `<h4>`：解析器的小节正则靠"到下一个 h4/h3/</body> 为止"收尾，缺了这个
    # 边界它会整节取不到（真实文件里表后本来还有别的小节）。
    payload = parse_synthetic(_SYNTHETIC)
    report.expect("解析/只认 techID~> 开头的 h3，去掉类名尾注，且**类集合来自标题**",
                  sorted(payload["objects"]), ["anotherClass", "viaDefs"])
    report.expect("解析/类记录的形状（desc 取自原文的 Description 小节，不是手写表）",
                  {k: payload["objects"]["viaDefs"][k] for k in ("id", "title", "desc")},
                  {"id": "viaDefs", "title": "techID~>viaDefs",
                   "desc": "Retrieves via definitions. 手写的第二句不算数。"})
    report.expect("解析/名称行开新条目、续行并进上一条目的 desc（名称行没有 desc 时）",
                  [(a["name"], a["desc"]) for a in payload["objects"]["viaDefs"]["attrs"]],
                  [("firstName", "This row continues the description of firstName."),
                   ("secondName", "A list of via names.")])

    # ── ② 把话说全：记录按 ATTR_KEYS 建，推出来的与原文的并存 ──
    _all = [a for c in payload["objects"].values() for a in c["attrs"]]
    report.expect("载荷/记录按 ATTR_KEYS 建（② 把话说全，四库同形）",
                  sorted({k for a in _all for k in a}), sorted(ATTR_KEYS))
    report.expect("载荷/type 由该类自己的说明推出并落盘；desc 留着（推它所依据的）",
                  [(a["name"], a["type"], a["desc"] == "A list of via names.") for a in _all],
                  [("firstName", None, False), ("secondName", "l_string", True),
                   ("kept", None, False)])
    report.expect("载荷/rw 恒 None（原文没有读写列）",
                  sorted({a["rw"] for a in _all}), [None])

    # ── 推法：算完就落盘，所以逐档钉住 ──
    for desc, want in (("list of database identifiers for the net", "l_objId"),
                       ("the database identifier of the shape", "objId"),
                       ("list of layer names", "l_string"),
                       ("t or nil", "boolean"),
                       ("name of the tech file", "string"),
                       ("描述里什么线索都没有", None),
                       (None, None)):
        report.expect(f"推法/_type_from_desc({desc!r})", _type_from_desc(desc), want)


if __name__ == "__main__":
    report = Report("database/techdb/core/test_decorate")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
