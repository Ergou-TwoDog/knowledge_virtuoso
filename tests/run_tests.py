#!/usr/bin/env python3
"""跑 `tests/knowledge_virtuoso/` 下所有测试（测试树与 `src/knowledge_virtuoso/` 同构）。

用法（在仓库根执行）:

  uv run python -B tests/run_tests.py                    # 全部
  uv run python -B tests/run_tests.py functions/core     # 只跑镜像路径里含这段的
  uv run python -B tests/run_tests.py --update           # 重录 golden（只影响 golden 类检查）

**自动发现**：扫镜像树下所有 `test_*.py`，每个暴露 `run(report, update=False)`。
加测试不用登记——文件放对位置（与它测的模块同路径）即可。

不需要 IC618 doc、不需要索引、不需要网络：fixture 就是被测层的输入。
`--update` 只在**确实打算改变输出**时用——没有输出变化却重录，等于把回归网剪掉。
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

from common import MIRROR, Report  # noqa: E402


def discover() -> list[pathlib.Path]:
    return sorted(MIRROR.rglob("test_*.py"))


def load(path: pathlib.Path):
    """按路径载入测试模块。镜像目录名与真包同名，所以**不能**按包名导入——
    只按文件路径载入，模块名用镜像相对路径拼，避免与真包撞名。"""
    name = "kvtest_" + "_".join(path.relative_to(MIRROR).with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="镜像树测试（fixture + golden，逐字节；外加断言）")
    parser.add_argument("paths", nargs="*", default=[],
                        help="只跑镜像路径里含这些片段的测试（如 functions/core）")
    parser.add_argument("--update", action="store_true", help="重录 golden")
    args = parser.parse_args()

    modules = discover()
    if args.paths:
        modules = [p for p in modules
                   if any(fragment in p.relative_to(MIRROR).as_posix() for fragment in args.paths)]
    if not modules:
        parser.error("没有匹配的测试文件")

    total = Report("合计")
    for path in modules:
        label = path.relative_to(MIRROR).with_suffix("").as_posix()
        report = Report(label)
        load(path).run(report, update=args.update)
        total.merge(report)
        print(report.summary())

    if total.failures:
        print(f"\n{len(total.failures)} 处不一致：")
        for line in total.failures[:20]:
            print(f"  {line}")
        if len(total.failures) > 20:
            print(f"  ……还有 {len(total.failures) - 20} 处")
    raise SystemExit(1 if total.failures else 0)


if __name__ == "__main__":
    main()
