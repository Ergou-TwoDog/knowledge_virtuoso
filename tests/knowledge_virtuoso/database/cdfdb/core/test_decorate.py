#!/usr/bin/env python3
"""② **归一**：`database/cdfdb/core/decorate.py`。

**与 src 一一对应**（见 `test_parse.py` 的表）。这一层测的是"**这些 h4 属于谁**"：

- `fixtures/html/` 的官方 doc 片段回放——比"片段 ⇒ 该类"与"整份文件 ⇒ 同一个类"
  是否一致（逐条比属性记录的 `name/desc/source`）；
- 自造 HTML 钉住：**手写白名单**把 h4 归到两个类下、**首锚点为空的 h4 也认得到**
  （`parseAsNumber` 靠"按文本认"才捡得回来）、两条**实参补录**标着 `source: "arg"`；
- **② 把话说全**：记录按 `ATTR_KEYS` 建，本库推的两样（`type`/`rw`）在这里算好落盘；
  原文那侧的 `desc`/`source` 照样留着，两类并存——所以要在这里逐档钉住推法（改了规则
  必须抬载荷版本号并重建）。

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
from knowledge_virtuoso.database.cdfdb.core.decorate import (  # noqa: E402
    SUPPLEMENT_PARAM_ATTRS, _rw_from_desc, _type_from_name_desc, decorate)
from knowledge_virtuoso.database.cdfdb.core.parse import parse  # noqa: E402

_SYNTHETIC = (
    '<h4><a>id</a></h4><p>The object identifier.</p>'
    '<h4><a>editable</a></h4><p>This field is not editable after the instance is created.</p>'
    '<h4><a>units</a></h4><p>The unit string shown next to the value.</p>'
    # 首个锚点为空的 h4：按形状匹配会漏，按文本匹配才认得到
    '<h4><a name="parseAsNumber"></a><a name="303193">parseAsNumber</a></h4>'
    '<p>String type parameter whose value can evaluate to a floating-point number.</p>'
)


def _entry(doc_path: str) -> dict:
    """② 的入口 = ① 之后接 ②（③ 里的 `extract_all` 就是这个组合，测试自己给一份）。"""
    return decorate(parse(doc_path))


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 ②（入口收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "chap21.html"
        path.write_text(html, encoding="utf-8")
        return _entry(str(path))


def run(report: Report, update: bool = False) -> None:
    # ── 片段回放：官方 doc 的一个对象类字段区 → 该类的全部属性记录 ──
    run_attr_parse_cases(HERE, "cdfdb", _entry, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_cdfDataId", "class_cdfParamId"])

    # ── 自造片段：白名单归类 + 空首锚点的 h4 + 实参补录 ──
    payload = parse_synthetic(_SYNTHETIC)
    _all = (payload["objects"]["cdfDataId"]["attrs"]
            + payload["objects"]["cdfParamId"]["attrs"])
    report.expect("载荷/记录按 ATTR_KEYS 建（② 把话说全，四库同形）",
                  sorted({k for a in _all for k in a}), sorted(ATTR_KEYS))
    report.expect("载荷/type 与 rw 是**算好落盘**的（原文两者都没有），desc 同时留着",
                  {(a["name"], a["type"], a["rw"]) for a in _all
                   if a["name"] in ("id", "editable")},
                  {("id", "objId", "rw"), ("editable", None, "ro")})
    report.expect("解析/字段按 _DATA_FIELDS / _PARAM_FIELDS 的顺序归到各自类下",
                  ([a["name"] for a in payload["objects"]["cdfDataId"]["attrs"]],
                   [a["name"] for a in payload["objects"]["cdfParamId"]["attrs"]]),
                  (["id"], ["units", "editable", "parseAsNumber", "name", "description"]))
    report.expect("解析/首锚点为空的 h4 也认得到（parseAsNumber 走字段区，不是补录）",
                  [a["source"] for a in payload["objects"]["cdfParamId"]["attrs"]
                   if a["name"] == "parseAsNumber"], ["field"])

    # ── 推法：这两样算完就落盘，所以在这儿逐档钉住 ──
    for name, desc, want in (("id", "任意说明", "objId"),
                             ("parameters", "任意说明", "l_objId"),
                             ("choices", "任意说明", "l_string"),
                             ("name", "任意说明", "string"),
                             ("foo", "a list of things", "l_string"),
                             ("foo", "什么线索都没有", None)):
        report.expect(f"推法/_type_from_name_desc({name!r}, {desc!r})",
                      _type_from_name_desc(name, desc), want)
    report.expect("推法/rw 从散文里的 \"not editable\" 推（原文没有读写列）",
                  [_rw_from_desc(d) for d in ("The object identifier.",
                                              "This field is not editable.",
                                              None)],
                  ["rw", "ro", "rw"])

    # ── 补录：只在 `cdfCreateParam` 实参里出现的那两条，标出来源；原文没给说明就是 None ──
    report.expect("解析/补录两条带 source=arg，name 取原文实参说明、description 原文没给",
                  [(a["name"], a["source"], a["desc"]) for a in SUPPLEMENT_PARAM_ATTRS],
                  [("name", "arg", "The name of the parameter."),
                   ("description", "arg", None)])
    data_only = _entry(str(HERE / "fixtures" / "html" / "class_cdfDataId.html"))
    report.expect("解析/片段只含 cdfDataId 的字段时，cdfParamId 只剩那两条补录",
                  [a["name"] for a in data_only["objects"]["cdfParamId"]["attrs"]],
                  ["name", "description"])


if __name__ == "__main__":
    report = Report("database/cdfdb/core/test_decorate")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
