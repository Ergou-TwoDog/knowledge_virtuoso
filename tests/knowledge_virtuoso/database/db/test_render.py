#!/usr/bin/env python3
"""设计库属性渲染回归：走库接口 ``database/db`` 的 ``render``（列声明在 ``__init__.py``）。

用例覆盖列宽与 60 字截断、跨类型检索、按 objType 检索、零命中的提示。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_cases  # noqa: E402

from knowledge_virtuoso.database import db  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_cases(HERE, db.render, report, update)


if __name__ == "__main__":
    report = Report("db")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
