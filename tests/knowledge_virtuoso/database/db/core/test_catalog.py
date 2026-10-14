#!/usr/bin/env python3
"""设计库：检索 + 解析（断言式）：`database/db/core/catalog.py`。

- **检索**：哪个类型取哪些名字、关键词怎么筛、行长什么样。这套逻辑与另外两个属性库共用
  `database/core/store.py`（见 `database/core/test_store.py`），本库自己的差异在这里锁住
  ——载荷用 `expanded` 展开、行**没有** `classes` 列、缺字段默认 `?`/`?`/``。
- **解析**：`fixtures/html/` 的官方 doc 片段（同类片段的出处见该目录 README），外加用自造
  HTML 直接钉住几处**靠位置硬编码的脆技巧**——它们一坏就是"几十个属性静默消失"。

不读真索引、不需要 doc：载荷来自 `fixtures/search.json`（手写），片段是随仓库的 HTML。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.db.core import catalog  # noqa: E402


def parse_synthetic(html: str) -> dict:
    """把自造 HTML 写成文件喂给 `extract_all`（它收路径），返回解析结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "attrib.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def cellview_section(body: str) -> str:
    """一个 `Attributes of Cellviews` 节（自造）：短语 → 表格 → 下一个 `<h3` 边界。"""
    return (f'<h3><a>Attributes of Cellviews</a></h3><table>{body}</table>')


def row(name: str, cells: str) -> str:
    return f"<tr><td>{name}</td>{cells}</tr>"


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_attr", report)

    # ── 片段回放：官方 doc 的节片段 → 归属名字集合与字段 ──
    run_attr_parse_cases(HERE, "db", catalog, report)
    report.expect("片段/夹具齐全（少一份就少一节的覆盖）",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["section_cellview", "section_inst", "shape_pathSeg", "shape_rect_note_only"])

    # ── 节短语定位：**取第 3 次出现**（真实文件里是目录 + 页首 + 正文各一次）──
    # 前两次的表格必须被忽略；只有第 3 次的属性进结果。
    locator = (cellview_section(row("firstOnly", "<td>ro</td><td>string</td>"))
               + cellview_section(row("secondOnly", "<td>ro</td><td>string</td>"))
               + cellview_section(row("thirdOnly", "<td>ro</td><td>string</td>"))
               + "<h3>边界</h3>")
    got = parse_synthetic(locator)
    report.expect("解析/节短语取第 3 次出现（前两次当目录/页首）",
                  sorted({"firstOnly", "secondOnly", "thirdOnly"} & set(got)), ["thirdOnly"])

    # ── 行形状：噪声词行与不足 3 格的行都要丢；`rw` 由 Modify 列是否含 yes 决定 ──
    shapes = cellview_section(
        row("note", "<td>yes</td><td>string</td>")               # 噪声词（表头残留）→ 丢
        + row("onlyTwo", "<td>yes</td>")                         # 只有 2 格 → 丢
        + row("writable", "<td>yes</td><td>string</td>")         # Modify=yes → rw
        + row("readonly", "<td>no</td><td>integer</td>")         # 否则 → ro
        + "<h3>边界</h3>")
    got = parse_synthetic(shapes)
    report.expect("解析/噪声词行与不足 3 格的行被丢，其余留下且 rw 按 Modify 列判",
                  (sorted({"note", "onlyTwo", "writable", "readonly"} & set(got)),
                   (got.get("writable", {}).get("rw"), got.get("readonly", {}).get("rw")),
                   got.get("readonly", {}).get("type")),
                  (["readonly", "writable"], ("rw", "ro"), "integer"))

    # ── Generic 合成层：同名属性取**更长的 desc**，并追加 `_generic` 归属 ──
    generic_desc = [a for a in catalog.GENERIC_ATTRS["Generic Figure"] if a["name"] == "bBox"][0]["desc"]
    short = cellview_section(row("bBox", "<td>ro</td><td>bBox</td><td>短</td>") + "<h3>边界</h3>")
    got = parse_synthetic(short)
    report.expect("解析/Generic 层同名取更长 desc，并追加 _generic 归属",
                  (got["bBox"]["desc"] == generic_desc, got["bBox"]["objTypes"]),
                  (True, ["cellview", "_generic"]))

    # ── 继承链展开：形状类型自己的属性 + Generic 层属性合在一起 ──
    expanded = catalog.expand_objtype({"myRect": {"name": "myRect", "objTypes": ["rect"]}})
    report.truthy("解析/expand_objtype 把自身归属与 Generic 层并进该类型",
                  {"myRect", "layerName", "lpp"} <= set(expanded["rect"]),
                  sorted(expanded["rect"])[:8])


if __name__ == "__main__":
    report = Report("database/db/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
