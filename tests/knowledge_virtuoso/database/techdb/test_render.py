#!/usr/bin/env python3
"""技术库属性渲染回归：走库接口 ``database/techdb`` 的 ``render``。

用例覆盖按类检索、跨类检索、零命中，以及 ``rw`` 列的两支（该库索引里 ``rw`` 恒为
``?``，所以"显示 rw 列"那一支靠 `fixtures/rw_shown.json` 里的手写行覆盖）。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_cases  # noqa: E402

from knowledge_virtuoso.database import techdb  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_cases(HERE, techdb.render, report, update)


if __name__ == "__main__":
    report = Report("techdb")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
