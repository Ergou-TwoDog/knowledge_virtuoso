#!/usr/bin/env python3
"""knowledge_virtuoso.custom.catalog — 二次开发来源：外部产出的 v3 信封。

这一支**不产出索引**：信封由二次开发工具（如 skill_dev_kit）自己生成，这里只负责
发现（`VIRTUOSO_CUSTOM_INDEX`）、按契约校验、读取。所以它没有解析器，也没有从原始
材料重建的能力——坏源只能跳过。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from knowledge_virtuoso.functions.core.envelope import _canonical_index_path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# VIRTUOSO_CUSTOM_INDEX 的解析结果缓存（进程内首次调用时解析，改环境后需重启）。
_custom_paths_cache: tuple[str, ...] | None = None


_CUSTOM_INDEX_ENV = "VIRTUOSO_CUSTOM_INDEX"


def custom_index_paths() -> tuple[str, ...]:
    """额外的、与官方同构（v3 envelope）的 custom 索引路径。

    取环境变量 ``VIRTUOSO_CUSTOM_INDEX``，按 ``os.pathsep`` 分隔多项；每项可以是索引
    文件，或含若干 ``*.json`` 的目录。结果在进程内首次调用时解析并缓存（与 data_dir
    同语义：改环境后需重启），使健康查询不 stat 磁盘。

    只做本来源的事：同一份文件不当两个来源（比如把官方索引也写进环境变量）是**装配**
    的判断，在 core/index.py 里按来源计划剔除——来源树之间不互相认识。
    """
    global _custom_paths_cache
    if _custom_paths_cache is not None:
        return _custom_paths_cache
    resolved: list[str] = []
    for part in os.environ.get(_CUSTOM_INDEX_ENV, "").split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        path = Path(part).expanduser()
        if not path.is_absolute():
            # 相对路径不是"多一种写法"：abspath 的基准是**进程工作目录**，而工作目录由启动方
            # （MCP 客户端、IDE、终端）决定。它不会失败，只会静默指到别处——所以出声。
            print(f"{_CUSTOM_INDEX_ENV} 里的相对路径「{part}」按进程工作目录解析为 "
                  f"{_canonical_index_path(path)}；建议写绝对路径", file=sys.stderr)
        children = sorted(str(child) for child in path.glob("*.json")) if path.is_dir() else [str(path)]
        resolved.extend(_canonical_index_path(child) for child in children)
    seen: set[str] = set()
    unique: list[str] = []
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    _custom_paths_cache = tuple(unique)
    return _custom_paths_cache
