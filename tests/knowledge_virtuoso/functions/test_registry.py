#!/usr/bin/env python3
"""来源发现与渲染配置分派（断言式）：`registry.py`。

不读索引、不需要 doc：发现只扫 `sources/` 目录并 import 各来源包。这里锁的是
"发现了谁、顺序如何、接口齐不齐、每条记录该用哪份渲染配置"。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.functions import registry  # noqa: E402
from knowledge_virtuoso.functions.core import render  # noqa: E402


def run(report: Report, update: bool = False) -> None:
    # 发现：至少两个来源，恰好一个基准，按 ORDER 升序。
    report.truthy("发现/非空", len(registry.SOURCES) >= 2, f"实际 {len(registry.SOURCES)} 个")
    orders = [source.ORDER for source in registry.SOURCES]
    report.expect("发现/按 ORDER 升序", orders, sorted(orders))
    report.expect("发现/恰好一个基准", sum(1 for s in registry.SOURCES if s.REQUIRED), 1)
    report.expect("发现/基准是官方", registry.BASE.NAME, "official")
    report.expect("发现/可选来源（除基准外）",
                  sorted(s.NAME for s in registry.OPTIONAL), ["custom"])

    # 接口：每棵树都得齐（缺一项就不该被认）。
    for source in registry.SOURCES:
        missing = [name for name in registry.REQUIRED_ATTRS if not hasattr(source, name)]
        report.expect(f"接口/{source.NAME} 齐全", missing, [])
        report.truthy(f"接口/{source.NAME} 的 index_paths 返回字符串元组",
                      isinstance(source.index_paths(), tuple)
                      and all(isinstance(p, str) for p in source.index_paths()),
                      "路径统一成字符串，来源之间才比得了'换过源没有'")

    # 分派：按记录选来源的渲染配置；没人认领就用主干默认。
    official_profile = registry.profile_for({"type": "function", "where": {"file": "a.html"}})
    report.expect("分派/官方记录无附加标记", official_profile.digest_marks, ())
    report.expect("分派/官方记录无状态行", official_profile.status_line, None)

    custom_entry = {"origin": "custom", "origin_meta": {"custom": {"load": 'load("x.il")'}}}
    custom_profile = registry.profile_for(custom_entry)
    report.expect("分派/custom 标记", custom_profile.digest_marks, ("自定义",))
    report.expect("分派/custom 状态行取自 origin_meta",
                  custom_profile.status_line(custom_entry),
                  '状态: 自定义函数（二次开发），需先 load("x.il") 才能调用')
    report.expect("分派/custom 状态行对非 custom 记录为 None",
                  custom_profile.status_line({"type": "function"}), None)

    report.expect("分派/主干默认配置是空配置", render.DEFAULT_PROFILE.digest_marks, ())
    report.expect("分派/主干默认无状态行", render.DEFAULT_PROFILE.status_line, None)


if __name__ == "__main__":
    report = Report("functions/test_registry")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
