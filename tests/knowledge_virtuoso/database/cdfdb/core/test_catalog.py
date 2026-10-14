#!/usr/bin/env python3
"""CDF 属性：检索 + 解析（断言式）：`database/cdfdb/core/catalog.py`。

- **检索**：类名怎么取成员、关键词怎么筛、行长什么样。与另外两个属性库共用
  `database/core/store.py`（见 `database/core/test_store.py`），本库自己的差异在这里锁住
  ——按 `classes` 取名字集合、行多一列 `classes`（同一属性可同时挂在两个 CDF 类上）。
- **解析**：`fixtures/html/` 的官方 doc 片段（一个对象类的字段区：`<h4><a>字段名</a></h4>`），
  外加自造 HTML 钉住 `not editable → ro`、手写补录属性与类型推断。

不读真索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.cdfdb.core import catalog  # noqa: E402


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 `extract_all`（它收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "chap21.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_cdf_attr", report)

    # ── 片段回放：官方 doc 的一个对象类字段区 → 归属名字集合与字段（含 desc）──
    run_attr_parse_cases(HERE, "cdfdb", catalog, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_cdfDataId", "class_cdfParamId"])

    # ── 自造片段：`<h4>` 字段 + 由 `not editable` 决定 rw ──
    synthetic = (
        '<h4><a>id</a></h4><p>The object identifier.</p>'
        '<h4><a>editable</a></h4><p>This field is not editable after the instance is created.</p>'
        '<h4><a>units</a></h4><p>The unit string shown next to the value.</p>'
    )
    payload = parse_synthetic(synthetic)
    report.expect("解析/字段正文里写 not editable → rw 记成 ro",
                  [(n, payload["attributes"][n]["rw"]) for n in ("id", "editable")],
                  [("id", "rw"), ("editable", "ro")])
    report.expect("解析/类成员表按字段出现顺序记名",
                  payload["classes"]["cdfDataId"]["attributes"][:1], ["id"])

    # ── 手写补录：`SUPPLEMENT_PARAM_ATTRS` 恒进 cdfParamId，即使片段里没有它的字段 ──
    data_only = read_json(HERE / "fixtures" / "html" / "class_cdfDataId.json")
    fragment = catalog.extract_all(str(HERE / "fixtures" / "html" / "class_cdfDataId.html"))
    report.truthy("解析/补录属性恒进 cdfParamId（片段只含 cdfDataId 的字段也一样）",
                  {"name", "parseAsNumber", "description"}
                  <= set(fragment["classes"]["cdfParamId"]["attributes"]),
                  fragment["classes"]["cdfParamId"]["attributes"])
    report.truthy("解析/片段只含 cdfDataId 的字段时，不混进 cdfParamId 的字段",
                  {"use", "paramType", "defValue"} & set(fragment["attributes"]) == set(),
                  sorted(fragment["attributes"]))
    report.truthy("解析/夹具声明的归属类与片段一致",
                  data_only["class"] == "cdfDataId", data_only["class"])

    # ── 类型推断：先按属性名，再按描述里的 "list of" ──
    for name, desc, want in (("id", "对象标识", "objId"),
                             ("parameters", "任意描述", "l_objId"),
                             ("choices", "任意描述", "l_string"),
                             ("paramType", "任意描述", "string"),
                             ("callback", "任意描述", "string"),
                             ("otherName", "a list of strings", "l_string"),
                             ("otherName", "普通描述", "")):
        report.expect(f"解析/_infer_type({name!r}, {desc!r})",
                      catalog._infer_type(name, desc), want)


if __name__ == "__main__":
    report = Report("database/cdfdb/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
