#!/usr/bin/env python3
"""CDF 库：检索 + 解析（断言式）：`database/cdfdb/core/catalog.py`。

载荷 = **两个 SKILL 对象类各存自己那份属性**（`g_cdfDataId` 9 条、`g_cdfParamId` 16 条）。
两类零重名，所以逐类存储在这里只统一形状、不改结果。

本文件锁住：

- **检索**：类名怎么认、关键词怎么筛、行多一列 `classes`。
- **解析**：`fixtures/html/` 的官方 doc 片段 + 自造 HTML 钉住三处：
  ① 字段正文里写 `not editable` → `rw` 记成 `ro`；
  ② **`parseAsNumber` 这种"首个锚点为空"的 h4**（原文写作
     `<h4><a name="parseAsNumber"></a><a name="303193">parseAsNumber</a></h4>`）
     必须按 **h4 文本**认出来，否则会整条漏掉、只能靠手写补录混进来；
  ③ 两条**只在 `cdfCreateParam` 实参里出现**的属性带 `source: "arg"`，其中
     `description` 原文没给说明，如实留空。
- **构建期校验**：空类 / 类内重名抛错，通过时打上格式版本。

不读真索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.cdfdb.core import catalog  # noqa: E402

_SYNTHETIC = (
    '<h4><a>id</a></h4><p>The object identifier.</p>'
    '<h4><a>editable</a></h4><p>This field is not editable after the instance is created.</p>'
    '<h4><a>units</a></h4><p>The unit string shown next to the value.</p>'
    # 首个锚点为空的 h4：按形状匹配会漏，按文本匹配才认得到
    '<h4><a name="parseAsNumber"></a><a name="303193">parseAsNumber</a></h4>'
    '<p>String type parameter whose value can evaluate to a floating-point number.</p>'
)


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 `extract_all`（它收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "chap21.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_cdf_attr", report)

    # ── 片段回放：官方 doc 的一个对象类字段区 → 该类的全部属性记录 ──
    run_attr_parse_cases(HERE, "cdfdb", catalog, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_cdfDataId", "class_cdfParamId"])

    # ── 自造片段 ──
    payload = parse_synthetic(_SYNTHETIC)
    report.expect("解析/字段正文里写 not editable → rw 记成 ro",
                  {a["name"]: a["rw"] for a in payload["objects"]["cdfDataId"]["attrs"]
                   + payload["objects"]["cdfParamId"]["attrs"] if a["name"] in ("id", "editable")},
                  {"id": "rw", "editable": "ro"})
    report.expect("解析/字段按 _DATA_FIELDS / _PARAM_FIELDS 的顺序归到各自类下",
                  ([a["name"] for a in payload["objects"]["cdfDataId"]["attrs"]],
                   [a["name"] for a in payload["objects"]["cdfParamId"]["attrs"]]),
                  (["id"], ["units", "editable", "parseAsNumber", "name", "description"]))
    report.expect("解析/首锚点为空的 h4 也认得到（parseAsNumber 走字段区，不是补录）",
                  [a["source"] for a in payload["objects"]["cdfParamId"]["attrs"]
                   if a["name"] == "parseAsNumber"], ["field"])

    # ── 补录：只在 `cdfCreateParam` 实参里出现的那两条，标出来源；原文没给说明就留空 ──
    report.expect("解析/补录两条带 source=arg，name 取原文实参说明、description 原文没给",
                  [(a["name"], a["source"], a["desc"]) for a in catalog.SUPPLEMENT_PARAM_ATTRS],
                  [("name", "arg", "The name of the parameter."),
                   ("description", "arg", "")])
    data_only = catalog.extract_all(str(HERE / "fixtures" / "html" / "class_cdfDataId.html"))
    report.expect("解析/片段只含 cdfDataId 的字段时，cdfParamId 只剩那两条补录",
                  [a["name"] for a in data_only["objects"]["cdfParamId"]["attrs"]],
                  ["name", "description"])

    # ── 类型推断：先按属性名，再按描述里的 "list of" ──
    for name, desc, want in (("id", "任意说明", "objId"),
                             ("parameters", "任意说明", "l_objId"),
                             ("choices", "任意说明", "l_string"),
                             ("name", "任意说明", "string"),
                             ("foo", "a list of things", "l_string"),
                             ("foo", "什么线索都没有", "")):
        report.expect(f"解析/_infer_type({name!r}, {desc!r})",
                      catalog._infer_type(name, desc), want)

    # ── 构建期校验 + 格式版本 ──
    def _bad(cls) -> bool:
        try:
            catalog._validated({"objects": cls})
            return False
        except ValueError:
            return True

    report.expect("校验/一个属性都没有的类要抛错",
                  _bad({"x": {"id": "x", "attrs": []}}), True)
    report.expect("校验/类内属性名重复要抛错",
                  _bad({"x": {"id": "x", "attrs": [{"name": "a", "rw": "rw", "type": "",
                                                    "desc": "", "source": "field"}] * 2}}), True)
    report.expect("校验/通过时打上格式版本",
                  catalog._validated({"objects": {"x": {"id": "x", "attrs": [
                      {"name": "a", "rw": "rw", "type": "", "desc": "", "source": "field"}]}}})
                  ["version"], catalog._PAYLOAD_VERSION)


if __name__ == "__main__":
    report = Report("database/cdfdb/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
