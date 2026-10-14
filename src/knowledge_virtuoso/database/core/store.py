#!/usr/bin/env python3
"""knowledge_virtuoso.database.core.store — 三个属性库共用的索引存取。

属性库的索引机制逐字相同，真正的差异只有四样：索引路径、默认来源文档、警告与报错里怎么
称呼自己、解析出的载荷形状。在此之前 `_load`/`_rebuild`/`build_from_html` 是**三份复制**
——改一处要记得改三处（三份的提示文案已经漂过一次）。

**这不是"来源"抽象**：属性库没有多来源（见 CLAUDE.md「三个属性库暂不分来源」），这里只把
"读 JSON → 坏了从官方 doc 重建 → 原子写回 + 进程内缓存 + 锁"这一件事收敛成一份。

行形状（`query_rows` 收的 `row` 工厂）**不抽**：db 查的列与 techdb/cdfdb 不同（没有
`classes` 列），那是各库自己的表示。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from threading import RLock
from typing import Callable

from knowledge_virtuoso._paths import atomic_write_json

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

__all__ = ["Store", "query_rows"]


class Store:
    """一个属性库的索引：在哪、怎么称呼自己、默认来源文档、怎么解析、载荷怎么包。"""

    def __init__(self, *, index_path, label: str, lib: str, doc_parts,
                 parse: Callable[[str], dict], payload: Callable[[dict], dict] | None = None):
        self.index_path = index_path          # 落盘位置（str 或 Path）
        self.label = label                    # 警告与报错里对自己的称呼，如 "db_attr"
        self.lib = lib                        # 修复提示里的构建子命令，如 "db"
        self.doc_parts = tuple(doc_parts)     # VIRTUOSO_DOC_DIR 下的默认来源文档
        self.parse = parse                    # 来源 HTML → 解析结果
        self.payload = payload or (lambda parsed: parsed)   # 解析结果 → 要落盘的载荷
        self._data: dict | None = None
        self._lock = RLock()

    def load(self) -> dict:
        """进程内缓存 → 索引 JSON；缺失或损坏时从官方 doc 重建、原子写回再返回。

        与 `_paths.data_dir` 同语义：索引位置在进程内首次读取时定下，改环境后需重启进程。
        """
        if self._data is None:
            with self._lock:
                if self._data is None:          # 双重检查：并发下只建一次
                    try:
                        with open(self.index_path, encoding="utf-8") as stream:
                            self._data = json.load(stream)
                    except (OSError, json.JSONDecodeError) as primary:
                        self._data = self._rebuild(primary)
        return self._data

    def build(self, doc_path: str | None = None) -> dict:
        """从来源 HTML 构建载荷；不给路径时取 VIRTUOSO_DOC_DIR 下的默认文档。"""
        if doc_path is None:
            doc_root = os.environ.get("VIRTUOSO_DOC_DIR")
            if not doc_root:
                raise FileNotFoundError(
                    "index.json 缺失，且 VIRTUOSO_DOC_DIR 未设置，无法重建。"
                    f"请设置 VIRTUOSO_DOC_DIR 或运行 knowledge-virtuoso-build {self.lib}")
            doc_path = os.path.join(doc_root, *self.doc_parts)
        if not Path(doc_path).exists():
            raise FileNotFoundError(f"文档不存在: {doc_path}，请检查 VIRTUOSO_DOC_DIR 环境变量")
        return self.payload(self.parse(doc_path))

    def _rebuild(self, primary: Exception) -> dict:
        doc_root = os.environ.get("VIRTUOSO_DOC_DIR")
        if not doc_root:
            raise RuntimeError(
                f"{self.label} 索引不可用: {self.index_path} ({primary})。"
                f"设置 VIRTUOSO_DOC_DIR 后可自动从官方 doc 重建，或运行: "
                f"knowledge-virtuoso-build {self.lib}") from primary
        print(f"{self.label} 索引缺失/损坏 ({self.index_path}): {primary}；"
              f"从 {doc_root!r} 重建", file=sys.stderr)
        data = self.build()
        atomic_write_json(self.index_path, data)
        return data


def query_rows(attrs: dict, names, keyword: str, row: Callable[[str, dict], dict]) -> list[dict]:
    """按名字集合取行：关键词过滤（子串、不区分大小写）→ 按名字排序 → 逐条交给 `row`。

    三个属性库共用这一段；`row` 决定列形状，是各库自己的表示。名字在 `attrs` 里没有记录
    时跳过（类型选择器的展开结果可能含未收录的名字）。
    """
    keyword = keyword.lower().strip()
    if keyword:
        names = {name for name in names if keyword in name.lower()}
    rows = []
    for name in sorted(names):
        info = attrs.get(name)
        if info:
            rows.append(row(name, info))
    return rows
