#!/usr/bin/env python3
"""二次开发来源的路径发现（断言式）：`VIRTUOSO_CUSTOM_INDEX` 怎么解析。

只碰临时目录。锁的是"哪些路径会被收、什么顺序、去不去重、相对路径会不会出声、
缓存是否按进程生效"——按索引内容读得对不对在 `test_render` 与 `core/test_*` 里。
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import tempfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.functions.core import envelope  # noqa: E402
from knowledge_virtuoso.functions.sources import custom as source  # noqa: E402
from knowledge_virtuoso.functions.sources.custom import catalog  # noqa: E402


def resolve(value: str):
    """在给定环境变量下解析一次，返回 (路径元组, stderr 文本)。

    先清模块级缓存——缓存是按进程生效的（改环境必须重启服务），测试里要模拟"新进程"。
    """
    catalog._custom_paths_cache = None
    stderr = io.StringIO()
    with mock.patch.dict(os.environ, {"VIRTUOSO_CUSTOM_INDEX": value}):
        with contextlib.redirect_stderr(stderr):
            paths = catalog.custom_index_paths()
    return paths, stderr.getvalue()


def run(report: Report, update: bool = False) -> None:
    canonical = envelope._canonical_index_path
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        a, b = root / "a.json", root / "b.json"
        for path in (a, b):
            path.write_text("{}", encoding="utf-8")
        (root / "notes.txt").write_text("x", encoding="utf-8")   # 非 .json：不该被收
        sub = root / "sub"
        sub.mkdir()
        c = sub / "c.json"
        c.write_text("{}", encoding="utf-8")

        paths, err = resolve("")
        report.expect("空值/零个来源", paths, ())
        report.expect("空值/不出声", err, "")

        paths, err = resolve(str(a))
        report.expect("单文件/收下", paths, (canonical(str(a)),))
        report.expect("绝对路径/不出声", err, "")

        sep = os.pathsep
        paths, _ = resolve(f"{b}{sep}{a}")
        report.expect("pathsep/多项且保持顺序", paths, (canonical(str(b)), canonical(str(a))))

        paths, _ = resolve(str(root))
        report.expect("目录/收其下全部 *.json（按名排序、不收非 json）",
                      paths, (canonical(str(a)), canonical(str(b))))
        report.expect("目录/不收子目录", canonical(str(c)) in paths, False)

        paths, _ = resolve(f"{a}{sep}{a}")
        report.expect("去重/同一文件写两遍只收一次", paths, (canonical(str(a)),))

        paths, _ = resolve(str(root / "nope.json"))
        report.expect("不存在的路径/照收（发现不等于存在，读取时才失败）",
                      paths, (canonical(str(root / "nope.json")),))

        # 相对路径不需要真文件——发现只做词法解析，"存在与否"归读取阶段。
        relative = os.path.join("some", "rel.json")
        expected = canonical(str(pathlib.Path.cwd() / relative))
        paths, err = resolve(relative)
        report.expect("相对路径/解析到工作目录下的绝对路径", paths, (expected,))
        report.truthy("相对路径/出警告并附解析结果",
                      "相对路径" in err and expected in err,
                      "相对路径会被静默换到别处，必须出声")

        # 缓存：同一进程内改环境变量不生效（要靠重启服务）。
        catalog._custom_paths_cache = None
        with mock.patch.dict(os.environ, {"VIRTUOSO_CUSTOM_INDEX": str(a)}):
            first = catalog.custom_index_paths()
        with mock.patch.dict(os.environ, {"VIRTUOSO_CUSTOM_INDEX": str(b)}):
            second = catalog.custom_index_paths()
        report.expect("缓存/进程内首次解析后不再看环境", (first, second),
                      ((canonical(str(a)),), (canonical(str(a)),)))

    catalog._custom_paths_cache = None      # 收尾清缓存：别把临时路径泄漏给别的测试模块

    # 认领：`origin == "custom"` 才是本来源的记录。
    report.expect("owns/认领 custom", source.owns({"origin": "custom"}), True)
    report.expect("owns/不认领官方", source.owns({"type": "function"}), False)
    report.expect("owns/不认领其它来源", source.owns({"origin": "project"}), False)


if __name__ == "__main__":
    report = Report("functions/sources/custom/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
