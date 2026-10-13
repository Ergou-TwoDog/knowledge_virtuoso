#!/usr/bin/env python3
"""来源发现：扫描 `functions/sources/`，不再手工登记。

**加一个来源 = 在 `sources/` 下加一棵树**，实现 `sources/official/__init__.py` 里那套
接口（`NAME` / `LABEL` / `REQUIRED` / `ORDER` / `CORPUS` / `index_paths` / `read` /
`rebuild` / `owns`，加上 `render.py` 里的 `PROFILE`）——`core/` 与这个文件都不用改。

顺序由各来源自己的 ``ORDER`` 决定（大者覆盖小者）——**绝不用目录名字母序**：改个目录名
不该改变"谁覆盖谁"。发现失败的来源（导入出错、接口不全）**警告并跳过**，一棵坏树不拖垮
服务；`python -m knowledge_virtuoso.functions --sources` 可以把发现结果打出来看。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

from knowledge_virtuoso.functions import sources as SOURCES_PACKAGE
from knowledge_virtuoso.functions.core import render

# 来源接口：缺一项就不认这棵树。宁可不加载，也不要半残的来源在跑。
REQUIRED_ATTRS = ("NAME", "LABEL", "REQUIRED", "ORDER", "CORPUS",
                  "index_paths", "read", "rebuild", "owns", "PROFILE")


def _discover() -> tuple:
    found = []
    for info in pkgutil.iter_modules(SOURCES_PACKAGE.__path__):
        if not info.ispkg:
            continue
        try:
            module = importlib.import_module(f"{SOURCES_PACKAGE.__name__}.{info.name}")
        except Exception as exc:  # 一棵树写坏了，别的来源照常工作
            print(f"来源 {info.name} 跳过（导入失败 {type(exc).__name__}: {exc}）", file=sys.stderr)
            continue
        missing = [name for name in REQUIRED_ATTRS if not hasattr(module, name)]
        if missing:
            print(f"来源 {info.name} 跳过（接口不全，缺 {', '.join(missing)}）", file=sys.stderr)
            continue
        found.append(module)
    return tuple(sorted(found, key=lambda module: module.ORDER))


SOURCES = _discover()

_BASES = tuple(source for source in SOURCES if source.REQUIRED)
if len(_BASES) != 1:
    raise RuntimeError(
        "必须有且只有一个基准来源（REQUIRED=True）；现在是 "
        f"{len(_BASES)} 个：{[source.NAME for source in _BASES]}"
    )

# 基准来源：索引不可用时报错，并尝试从原始材料重建。
BASE = _BASES[0]

# 可选来源：索引不可用/损坏或契约不符时跳过并警告，不拖垮服务；ORDER 大的优先。
OPTIONAL = tuple(source for source in SOURCES if not source.REQUIRED)


def profile_for(entry: dict) -> render.Profile:
    """按记录找所属来源的渲染配置；没人认领就用主干默认（空配置）。"""
    for source in reversed((BASE, *OPTIONAL)):
        if source.owns(entry):
            return source.PROFILE
    return render.DEFAULT_PROFILE
