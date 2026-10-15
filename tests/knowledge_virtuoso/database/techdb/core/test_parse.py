#!/usr/bin/env python3
"""① **如实层**：`database/techdb/core/parse.py`。

**与 src 一一对应**——`tests/.../database/<库>/` 下的每个 `test_<层>.py` 对着同名的
`<层>.py`：

    core/test_parse.py     ↔ techdb/core/parse.py      fixtures/raw/   （自造片段）
    core/test_decorate.py  ↔ techdb/core/decorate.py   fixtures/html/  （官方 doc 片段）
    ../test_index.py       ↔ techdb/index.py           fixtures/search.json

这一层测的是"解析器**看到**了什么"：每个 h3 小节（**所有**小节，含不是类的）、
它的 `Description` 正文、`Attributes` 表的格子。**不解释格子**——判哪一格是属性名、
合并续行、认 `techID~>` 前缀都在 ②。

`fixtures/raw/*.json` 是**录下来的**（这一层没有线上对照），变更探测器而非正解。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_raw_cases  # noqa: E402

from knowledge_virtuoso.database.techdb.core import parse  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_raw_cases(HERE, parse, report)
    report.expect("raw/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "raw").glob("*.html")),
                  ["section_basics"])


if __name__ == "__main__":
    report = Report("database/techdb/core/test_parse")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
