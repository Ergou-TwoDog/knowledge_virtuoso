#!/usr/bin/env python3
"""knowledge_virtuoso.functions.core.envelope — 索引文件（v3 信封）的读写。

**与来源无关**：各来源落盘/读入的是同一种信封。差异由调用方传进来：`require_envelope`
（契约是否强制信封形态）与 `label`（报错文案里的来源称呼）、`corpus`（信封里的语料
元数据）——core 不知道"官方"或"custom"是谁。
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from knowledge_virtuoso.functions.core.contract import _DERIVED_KEYS, _SCHEMA_VERSION

def _canonical_index_path(path: str | Path) -> str:
    # Lexical normalization never stats disk on healthy queries. Symlink aliases
    # intentionally remain different sources (no filesystem hot reload).
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _index_envelope(entries: dict[str, dict], corpus: dict) -> dict:
    """信封骨架；``corpus``（语料是谁）由写索引的那个来源提供。"""
    return {
        "schema_version": _SCHEMA_VERSION,
        "corpus": dict(corpus),
        # 派生字段不落盘：加载时按函数名重算。
        "functions": {
            name: {k: v for k, v in entry.items() if k not in _DERIVED_KEYS}
            for name, entry in sorted(entries.items())
        },
    }


def _write_index(json_path: str | Path, entries: dict[str, dict], corpus: dict) -> None:
    """原子写入索引：紧凑分隔符 + LF 换行 + gzip。

    索引体积的绝大部分是表示开销而非不可约信息：紧凑化去掉约 28% 的缩进空白，
    gzip 再去掉键名与短语重复。代价是文件不能再直接 grep，排障需解压查看。
    """
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        _index_envelope(entries, corpus), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            # mtime=0 让同样的内容产出同样的字节，便于比较与复现。
            stream.write(gzip.compress(payload, 9, mtime=0))
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()



def _read_index_entries(json_path: str | Path, *, require_envelope: bool = False,
                        label: str = "") -> dict:
    """读取一份索引（gzip 或明文）→ ``functions`` 记录字典。

    ``require_envelope`` 为真时只接受 v3 envelope（含 ``schema_version``）——按各来源自己
    的契约要求而定：非 envelope 形态（如按文件分组的 list）一律拒绝。``label`` 是报错文案
    里对来源的称呼，由调用方给。
    """
    raw = Path(json_path).read_bytes()
    if raw[:2] == b"\x1f\x8b":  # v3 起索引 gzip 落盘；仍兼容未压缩的 JSON
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("index root must be an object")
    if "schema_version" in data:
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(
                f"索引格式版本不兼容（文件为 {data['schema_version']}，当前需要 {_SCHEMA_VERSION}）")
        entries = data.get("functions")
    elif require_envelope:
        raise ValueError(f"{label}索引必须是 v3 envelope（含 schema_version=3）")
    else:
        entries = data  # Legacy flat records; no invented documentation fields.
    return entries


