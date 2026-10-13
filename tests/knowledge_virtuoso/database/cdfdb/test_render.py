#!/usr/bin/env python3
"""CDF 属性渲染回归：直接喂 ``database/cdfdb/render.py`` 录制的行。

用例覆盖按类检索、跨类检索、零命中的提示，以及 55 字描述截断。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_cases  # noqa: E402

from knowledge_virtuoso.database.cdfdb.render import render_cdfdb_attrs  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_cases(HERE, render_cdfdb_attrs, report, update)


if __name__ == "__main__":
    report = Report("cdfdb")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
