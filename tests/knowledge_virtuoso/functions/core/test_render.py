#!/usr/bin/env python3
"""`core/render.py` 的对外入口：未命中、搜索零命中、搜索页正文。

这三条是渲染主干里**不经过来源**的入口（`render_not_found` / `render_search_empty` /
`render_search_page`），fixture 就是它们的参数。记录级的五档渲染在
`../sources/official/` 与 `../sources/custom/` 各自的 test_render.py 里。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json  # noqa: E402

from knowledge_virtuoso.functions import registry  # noqa: E402
from knowledge_virtuoso.functions.core import render  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    # 一进一出同目录同 stem：`cases/x.json` 输入、`cases/x.txt` 期望输出（扩展名分角色）。
    for fixture in sorted((HERE / "cases").glob("*.json")):
        case = read_json(fixture)
        if "page" in case:
            if case["page"]["total"]:
                # 搜索页每行的摘要按记录现取来源配置（与 server.py 走同一条路）。
                got = render.render_search_page(case["page"], case["records"], case["with_digest"],
                                                profile_for=registry.profile_for)
            else:
                got = render.render_search_empty(case["prefix"], case["keywords"], case["hints"])
        else:
            got = render.render_not_found(case["func_name"], case["hints"])
        report.check(fixture.stem, got, HERE / "cases" / f"{fixture.stem}.txt", update)


if __name__ == "__main__":
    report = Report("functions/core")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
