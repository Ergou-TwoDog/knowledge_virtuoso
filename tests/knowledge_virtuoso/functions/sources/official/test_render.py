#!/usr/bin/env python3
"""官方来源的渲染回归：27 条记录 × 五档 = 135 份 golden，逐字节比。

**直调** `core/render.py` + 官方来源自己的 PROFILE（空配置）：不经 MCP、不读索引、
不需要 IC618 doc——fixture 就是渲染层的输入。所以这一份锁的是"官方来源的记录 → 文本"，
解析改坏了不会在这里报错（那是 `test_catalog` 的事）。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json  # noqa: E402

from knowledge_virtuoso.functions.core import render  # noqa: E402
from knowledge_virtuoso.functions.sources.official.render import PROFILE  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    for fixture in sorted((HERE / "fixtures").glob("*.json")):
        record = read_json(fixture)
        for detail in render.DETAILS:
            report.check(f"{fixture.stem}.{detail}",
                         render.render_entry(record, detail, profile=PROFILE),
                         HERE / "golden" / f"{fixture.stem}.{detail}.txt", update)


if __name__ == "__main__":
    report = Report("functions/sources/official")
    run(report, update="--update" in sys.argv)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
