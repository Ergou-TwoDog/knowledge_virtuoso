#!/usr/bin/env python3
"""二次开发来源的渲染回归：1 条 custom 记录 × 五档 = 5 份 golden。

这才是"只因为来源不同"的那几行差异的回归点：`（自定义）` 标记与 `load()` 前提行。
记录取自 `fixtures/synthetic.json`（手写信封，官方没有同名函数；名是键，
`query_function` 会给记录补上 `name`）。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json  # noqa: E402

from knowledge_virtuoso.functions.core import render  # noqa: E402
from knowledge_virtuoso.functions.sources.custom.render import PROFILE  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    envelope = read_json(HERE / "fixtures" / "synthetic.json")
    name = next(iter(envelope["functions"]))
    record = {**envelope["functions"][name], "name": name}
    for detail in render.DETAILS:
        report.check(f"{name}.{detail}",
                     render.render_entry(record, detail, profile=PROFILE),
                     HERE / "golden" / f"{name}.{detail}.txt", update)


if __name__ == "__main__":
    report = Report("functions/sources/custom")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
