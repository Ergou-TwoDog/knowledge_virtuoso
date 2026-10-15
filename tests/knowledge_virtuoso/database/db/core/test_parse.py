#!/usr/bin/env python3
"""① **如实层**：`database/db/core/parse.py`。

**与 src 一一对应**——`tests/.../db/core/` 下每个 `test_<层>.py` 对着同名的 `<层>.py`：

    test_parse.py      ↔ db/core/parse.py       fixtures/raw/   （自造的 doc 片段）
    test_decorate.py   ↔ db/core/decorate.py    fixtures/html/  （官方 doc 的片段）
    ../test_index.py   ↔ db/index.py            fixtures/search.json

这一层测的是"解析器**看到**了什么"：标题、某标题后是哪张表、表里有哪些格子（`<br>`
分段原样保留）。**它不解释格子**，所以这里没有一条断言是关于属性名/父指针/类型的。

`fixtures/raw/*.json` 是**录下来的**——这一层没有线上对照（索引里只有 ② 归一后的形状），
所以那些期望值是**变更探测器而不是正解**：改解析器时它只说"raw 变了"，对不对得人来判。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_raw_cases  # noqa: E402

from knowledge_virtuoso.database.db.core import parse  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    # ── 自造片段 → 文档结构（标题 / h3 归属 / 表前正文 / 格子 / <br> 分段）──
    run_attr_raw_cases(HERE, parse, report)
    report.expect("raw/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "raw").glob("*.html")),
                  ["table_basics"])


if __name__ == "__main__":
    report = Report("database/db/core/test_parse")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
