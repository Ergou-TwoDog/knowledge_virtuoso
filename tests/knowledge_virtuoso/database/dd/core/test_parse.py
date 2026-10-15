#!/usr/bin/env python3
"""① **如实层**：`database/dd/core/parse.py`。

**与 src 一一对应**——`tests/.../database/<库>/` 下的每个 `test_<层>.py` 对着同名的
`<层>.py`：

    core/test_parse.py     ↔ dd/core/parse.py      fixtures/raw/
    core/test_decorate.py  ↔ dd/core/decorate.py   fixtures/html/
    ../test_index.py       ↔ dd/index.py           fixtures/search.json

这一层测的是"解析器**看到**了什么"：那个 h2 小节里有哪几张表、每张表有哪些格子（空格子
在这一层就没了）。**不解释**——判哪张是属性表、算对象全集、看基数，全在 ②。

`fixtures/raw/*.json` 是**录下来的**（这一层没有线上对照），变更探测器而非正解。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_raw_cases  # noqa: E402

from knowledge_virtuoso.database.dd.core import parse  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_raw_cases(HERE, parse, report)
    report.expect("raw/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "raw").glob("*.html")),
                  ["section_tables"])


if __name__ == "__main__":
    report = Report("database/dd/core/test_parse")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
