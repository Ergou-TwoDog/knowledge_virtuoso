#!/usr/bin/env python3
"""数据管理对象库：渲染层 golden（走库接口 ``database/dd`` 的 ``render``）。

一进一出同目录同 stem：`cases/<名>.json` 是输入（`{params, rows}`），`cases/<名>.txt` 是期望文本。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_cases  # noqa: E402

from knowledge_virtuoso.database import dd  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    run_attr_cases(HERE, dd.render, report, update)


if __name__ == "__main__":
    report = Report("database/dd/test_render")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
