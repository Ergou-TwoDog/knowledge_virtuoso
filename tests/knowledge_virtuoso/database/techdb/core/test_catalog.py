#!/usr/bin/env python3
"""tech 库：检索 + 解析（断言式）：`database/techdb/core/catalog.py`。

- **检索**：类名怎么取成员、关键词怎么筛、行长什么样。这套逻辑与另外两个属性库共用
  `database/core/store.py`（见 `database/core/test_store.py`），本库自己的差异在这里锁住
  ——按 `classes` 取名字集合、行多一列 `classes`、缺字段的 `type` 默认是空串。
- **解析**：`fixtures/html/` 的官方 doc 片段（一个 `techID~>` 的 `<h3>` 段），外加自造 HTML
  钉住 `<h3>` 定位、`class_id` 归一、续行并入与白名单过滤——这四处在真文件里都只走一次
  分支，坏了不会有别的症状。

不读真索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.techdb.core import catalog  # noqa: E402


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 `extract_all`（它收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "appA.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_tech_attr", report)

    # ── 片段回放：官方 doc 的一个类段 → 归属名字集合与字段 ──
    run_attr_parse_cases(HERE, "techdb", catalog, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_layers", "class_viaDefs"])

    # ── 自造片段：类段语法（`<h3>` + Description / Attributes 两个 h4 小节）──
    # 表后留一个 `<h4>`：解析器的小节正则靠"到下一个 h4/h3/</body> 为止"收尾，缺了这个
    # 边界它会整节取不到（真实文件里表后本来还有别的小节）。
    synthetic = (
        '<h3><a>techID~>viaDefs (含尾注)</a></h3>'
        '<h4><a>Description</a></h4><p>手写片段的类描述。</p>'
        '<h4><a>Attributes</a></h4><table>'
        '<tr><td>firstName</td></tr>'
        '<tr><td>This row continues the description of firstName.</td></tr>'
        '<tr><td>secondName</td><td>Inline description.</td></tr>'
        '</table>'
        '<h4><a>Rules</a></h4><p>表后的小节，充当边界。</p>'
        '<h3><a>techID~>notAClass</a></h3>'
        '<h4><a>Attributes</a></h4><table><tr><td>dropped</td><td>不该出现</td></tr></table>'
        '</body>'
    )
    payload = parse_synthetic(synthetic)
    report.expect("解析/只认 techID~> 开头的 h3，并去掉类名尾注",
                  sorted(payload["classes"]), ["viaDefs"])
    report.expect("解析/类记录的形状（desc 取自白名单表 CLASS_DESC，不是原文的 Description 小节）",
                  {k: payload["classes"]["viaDefs"][k] for k in ("name", "path", "desc", "objType")},
                  {"name": "viaDefs", "path": "techID~>viaDefs", "desc": catalog.CLASS_DESC["viaDefs"],
                   "objType": catalog.CLASS_OBJTYPE.get("viaDefs")})
    report.expect("解析/名称行开新条目、续行并进上一条目的 desc（名称行没有 desc 时）",
                  [(name, payload["attributes"][name]["desc"])
                   for name in payload["classes"]["viaDefs"]["attributes"]],
                  [("firstName", "This row continues the description of firstName."),
                   ("secondName", "Inline description.")])

    # ── 白名单：`CLASS_DESC` 里没有的类整节丢弃（真文件里 11 个类都在白名单内，这一支
    #    只在文档变动或类别名改变时才走到，所以只能用自造片段钉）──
    report.truthy("解析/白名单外的类被丢弃",
                  "notAClass" not in payload["classes"]
                  and "dropped" not in payload["attributes"],
                  sorted(payload["classes"]))

    # ── 类型推断：由描述猜类型，猜不中给空串 ──
    for desc, want in (("list of database identifiers for the net", "l_objId"),
                       ("the database identifier of the shape", "objId"),
                       ("list of layer names", "l_string"),
                       ("t or nil", "boolean"),
                       ("name of the tech file", "string"),
                       ("描述里什么线索都没有", "")):
        report.expect(f"解析/infer_type({desc!r})", catalog.infer_type(desc), want)


if __name__ == "__main__":
    report = Report("database/techdb/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
