#!/usr/bin/env python3
"""数据管理对象库：检索 + 解析（断言式）：`database/dd/core/catalog.py`。

原文（`skdfref/chap3.html` 的 "Attributes of Data Management Objects"）记法与另外三库都不同：
**转置**——一行一个属性，后面每个适用对象各占一格；再加一张关系表（带基数 `1:1`/`1:n`）。
**没有继承**，也**没有类型与说明**（属性表只有"名字 | 适用对象"两列）。

本文件锁住：

- **检索**：对象名怎么认（精确 / 忽略大小写）、关键词怎么筛、属性与关系一起返回、
  行里 `kind`/`cardinality`/`objects` 三样。
- **解析**：`fixtures/html/` 的官方 doc 片段 + 自造 HTML 钉住四处脆技巧——
  ① 靠**表头签名**在四张表里认出属性表与关系表（本节还有运算符表与类型图例表）；
  ② 对象全集从**枚举得最全的关系行**取（表 19-1 的适用列没有列名，顺序只能从这儿来）；
  ③ 空格子 = 不适用；
  ④ 关系行的基数列。
- **构建期校验**：空全集 / 适用对象不在全集里 / 基数不像 `1:n` / 属性名与关系名撞车，
  都要抛错——本节靠"表头签名 + 最全的那行"解析，排版一变就可能悄悄错位。

不读真索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.dd.core import catalog  # noqa: E402

# 与原文同形：四张表（运算符图例 / 类型图例 / 属性表 / 关系表），靠表头签名挑。
_SYNTHETIC = (
    '<h2>Attributes of Data Management Objects</h2>'
    '<table><tr><td>(~&gt;)</td><td>To access any attribute</td></tr>'
    '<tr><td>(~&gt;?)</td><td>To see names</td></tr></table>'
    '<table><tr><td>b</td><td>a DDPI object</td></tr>'
    '<tr><td>d</td><td>an identifier</td></tr></table>'
    '<table>'
    '<tr><td>Attribute Names</td><td colspan="3">Object Types Attribute is Valid For</td></tr>'
    '<tr><td>group</td><td>libFile</td><td>cellFile</td><td>viewFile</td></tr>'
    '<tr><td>prop</td><td>lib</td><td>cell</td><td>view</td></tr>'
    '</table>'
    '<table>'
    '<tr><td>Relation names</td><td>Relationship</td><td colspan="3">Object Types</td></tr>'
    '<tr><td>cells</td><td>1:n</td><td>lib</td></tr>'
    '<tr><td>lib</td><td>1:1</td><td>lib</td><td>cell</td><td>view</td><td>libFile</td></tr>'
    '<tr><td>view</td><td>1:1</td><td>libFile</td></tr>'
    '</table>'
    '<h2>下一个小节</h2>'
)


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 `extract_all`（它收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "chap3.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_dd_attr", report)

    # ── 片段回放：官方 doc 的整节 → 对象全集 / 属性 / 关系 ──
    run_attr_parse_cases(HERE, "dd", catalog, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["dd_section"])

    # ── 自造片段：靠表头签名在四张表里挑对两张，图例表跳过 ──
    payload = parse_synthetic(_SYNTHETIC)
    report.expect("解析/属性表与关系表按表头签名认出，图例表不进结果",
                  (sorted(payload["attributes"]), sorted(payload["relations"])),
                  (["group", "prop"], ["cells", "lib", "view"]))
    report.expect("解析/空格子 = 不适用（group 只适用三个 *File 对象）",
                  payload["attributes"]["group"]["objectTypes"], ["libFile", "cellFile", "viewFile"])
    report.expect("解析/关系行的基数列取到了",
                  [(n, payload["relations"][n]["cardinality"])
                   for n in ("cells", "lib", "view")],
                  [("cells", "1:n"), ("lib", "1:1"), ("view", "1:1")])
    report.expect("解析/对象全集取自**枚举得最全的关系行**（lib 那行列出四个）",
                  payload["objectTypes"], ["lib", "cell", "view", "libFile"])

    # ── 构建期校验：这一节靠"表头签名 + 最全的那行"解析，排版一变就可能悄悄错位 ──
    def _bad(p: dict) -> bool:
        try:
            catalog._validated(p)
            return False
        except ValueError:
            return True

    base = {"objectTypes": ["lib"], "attributes": {"a": {"name": "a", "kind": "attr", "objectTypes": ["lib"]}},
            "relations": {}}
    report.expect("校验/对象全集为空要抛错",
                  _bad({**base, "objectTypes": []}), True)
    report.expect("校验/适用对象不在全集里要抛错",
                  _bad({**base, "attributes": {"a": {"name": "a", "kind": "attr",
                                                     "objectTypes": ["没有这个"]}}}), True)
    report.expect("校验/关系基数不像 `1:n` 要抛错",
                  _bad({**base, "relations": {"r": {"name": "r", "kind": "relation",
                                                    "cardinality": "很多", "objectTypes": ["lib"]}}}), True)
    report.expect("校验/属性名与关系名撞车要抛错",
                  _bad({**base, "relations": {"a": {"name": "a", "kind": "relation",
                                                    "cardinality": "1:1", "objectTypes": ["lib"]}}}), True)
    report.expect("校验/通过时打上格式版本",
                  catalog._validated(base)["version"], catalog._PAYLOAD_VERSION)

    # ── 选择器：精确 → 忽略大小写 → 不认识 ──
    report.expect("检索/对象选择器解析的几条路径",
                  [catalog._resolve(["libFile", "cellFile"], "libFile"),
                   catalog._resolve(["libFile", "cellFile"], "LIBFILE"),
                   catalog._resolve(["libFile", "cellFile"], "没有这个"),
                   catalog._resolve(["libFile"], "")],
                  ["libFile", "libFile", None, None])


if __name__ == "__main__":
    report = Report("database/dd/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
