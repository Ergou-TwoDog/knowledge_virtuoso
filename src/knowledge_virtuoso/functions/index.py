#!/usr/bin/env python3
"""knowledge_virtuoso.functions.index — 装配编排、内存索引与查询。

这一层是**跨来源**的：它遍历 `registry` 发现到的来源合成一张内存索引，并在这张索引
上做查询/搜索/建议。哪个来源怎么读、怎么重建、坏了怎么办，都写在各自的
`functions/sources/<来源>/` 包里；**加来源不用动这个文件**。索引缺失时按"基准来源可
重建、可选来源只跳过"来恢复。
"""

from __future__ import annotations

import difflib
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from threading import RLock

from knowledge_virtuoso.functions import registry
from knowledge_virtuoso.functions.core.contract import _rebuild_runtime_indexes, _tokenize_name
from knowledge_virtuoso.functions.core.envelope import _canonical_index_path, _write_index


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# Public module state is intentionally kept as the flat map used by the MCP
# server.  The on-disk v2 envelope is normalized when loaded.
_index: dict[str, dict] = {}
_keyword_index: dict[str, set[str]] = {}
_prefix_index: dict[str, set[str]] = {}
_index_built = False
_last_report: dict[str, object] = {}
_index_lock = RLock()
# 当前内存索引由哪些源合成：第一个恒为官方索引，其后为零个或多个 custom 源。
_index_sources: tuple[str, ...] = ()
_index_lengths: tuple[int, int, int] = (0, 0, 0)


def _memory_healthy(sources: tuple[str, ...]) -> bool:
    """O(1) guard, not a detector for equal-size or nested-value corruption."""
    return (_index_built and _index_sources == sources
            and isinstance(_index, dict) and bool(_index)
            and isinstance(_keyword_index, dict) and isinstance(_prefix_index, dict)
            and (len(_index), len(_keyword_index), len(_prefix_index)) == _index_lengths)


def _publish(runtime: tuple[dict, dict, dict], sources: tuple[str, ...], report: dict) -> None:
    """Caller holds _index_lock; published dictionaries are never mutated here."""
    global _index, _keyword_index, _prefix_index, _index_sources
    global _index_lengths, _index_built, _last_report
    _index, _keyword_index, _prefix_index = runtime
    _index_sources = tuple(sources)
    _index_lengths = tuple(len(part) for part in runtime)
    _last_report = report
    _index_built = True



def last_report() -> dict[str, object]:
    """最近一次官方构建的分类统计（供 --report 与排查用）。"""
    with _index_lock:
        return dict(_last_report)


def set_last_report(report: dict) -> None:
    """记录一次构建统计（构建入口在发布之外单独跑的路径用）。"""
    global _last_report
    with _index_lock:
        _last_report = dict(report)


def build_index_file(doc_root: str, output_path: str | Path) -> int:
    """Parse, validate, atomically persist, then publish one complete generation."""
    with _index_lock:
        source = _canonical_index_path(output_path)
        entries, report = registry.BASE.rebuild(doc_root)
        runtime = _rebuild_runtime_indexes(entries)
        _write_index(source, runtime[0], registry.BASE.CORPUS)
        _publish(runtime, (source,), report)
        return len(runtime[0])


class IndexLoadError(RuntimeError):
    """Neither JSON nor configured official docs could restore the index."""


def _build_index(doc_root: str | None = None, index_json: str | Path | None = None) -> None:
    """枚举来源装配内存索引。调用方不持锁。

    基准来源（官方）的索引坏了要报错，但先**尝试从原始 doc 重建**再写回；可选来源
    （custom 等）坏了只警告并跳过——它们不该拖垮服务。显式指定 `index_json` 时只读
    这一份：调用方说的是"就读这个文件"，不该再掺入环境里登记的来源。
    """
    global _index_built
    if index_json is not None:
        sources = (_canonical_index_path(index_json),)
        optional: tuple[tuple[object, str], ...] = ()
    else:
        sources = tuple(_canonical_index_path(path) for path in registry.BASE.index_paths())
        optional = _optional_plan(sources)
        sources += tuple(path for _source, path in optional)
    with _index_lock:
        if _memory_healthy(sources):
            return
        # Failed recovery/source switches must never serve the previous map.
        _index_built = False
        base_path = _canonical_index_path(sources[0])
        try:
            entries = registry.BASE.read(base_path)
            _rebuild_runtime_indexes(entries)  # 基准来源记录校验，失败同样走 doc 恢复
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            json_reason = f"{type(exc).__name__}: {exc}"
        else:
            _publish_merged(entries, sources, optional)
            return
        root = doc_root if doc_root is not None else os.environ.get("VIRTUOSO_DOC_DIR")
        print(f"SKILL index JSON unavailable ({base_path}): {json_reason}; "
              f"recovering from doc {root!r}; "
              "或运行 knowledge-virtuoso-build functions", file=sys.stderr)
        try:
            if not root:
                raise ValueError(
                    f"doc_root not configured; set VIRTUOSO_DOC_DIR to rebuild {base_path}, "
                    f"or run: knowledge-virtuoso-build functions"
                )
            entries, _report = registry.BASE.rebuild(root)
            _write_index(base_path, entries, registry.BASE.CORPUS)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            raise IndexLoadError(
                f"Index recovery failed. JSON {base_path}: {json_reason}; "
                f"doc {root!r}: {type(exc).__name__}: {exc}; "
                "请重建索引：knowledge-virtuoso-build functions"
            ) from exc
        _publish_merged(entries, sources, optional)


def _optional_plan(base_paths: tuple[str, ...]) -> tuple[tuple[object, str], ...]:
    """可选来源的装配计划：逐个来源、逐个索引文件。

    "同一份文件不当两个来源"是**跨来源**的判断（比如环境变量把官方索引也写进来了），
    所以放在装配这层，而不是塞进某一棵来源树——来源树之间不互相认识。
    """
    # 基准路径也要先规范化再比：否则 `_optional_plan(("index.json",))` 与候选的绝对路径
    # 永远不相等，去重会静默失灵（`_build_index` 恰好传的是规范形式，才没暴露）。
    used = {_canonical_index_path(path) for path in base_paths}
    plan: list[tuple[object, str]] = []
    for source in registry.OPTIONAL:
        for path in source.index_paths():
            path = _canonical_index_path(path)
            if path in used:
                continue
            used.add(path)
            plan.append((source, path))
    return tuple(plan)


def _publish_merged(entries: dict, sources: tuple[str, ...], optional) -> None:
    """把基准记录与各可选来源合并、校验后发布（caller 持有 _index_lock）。

    可选来源逐源读取；坏源（缺失/损坏/非 envelope）跳过并警告，不拖垮服务。同名时
    可选来源覆盖基准（二次开发的定位即扩展/打补丁），遮蔽写 stderr 警告，避免官方
    文档被静默隐藏。
    """
    merged = dict(entries)
    for source, extra in optional:
        try:
            extra_entries = source.read(extra)
            if not extra_entries:
                print(f"{source.LABEL}索引为空，忽略: {extra}", file=sys.stderr)
                continue
            _rebuild_runtime_indexes(extra_entries)  # 先独立校验，坏源不进合并
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            print(f"{source.LABEL}索引跳过（{type(exc).__name__}: {exc}）: {extra}",
                  file=sys.stderr)
            continue
        for name, record in extra_entries.items():
            if name in merged:
                print(f"{source.LABEL}索引覆盖同名函数 {name}: {extra}", file=sys.stderr)
            merged[name] = record
    runtime = _rebuild_runtime_indexes(merged)
    _publish(runtime, sources, {})


def _search_by_tokens(words: list[str], prefix_filter: str | None = None) -> list[str]:
    candidates: set[str] | None = None
    if prefix_filter:
        candidates = set(_prefix_index.get(prefix_filter, set()))
        if not candidates:
            return []
    for word in words:
        matches = set(_keyword_index.get(word, set()))
        for token, names in _keyword_index.items():
            if word in token:
                matches.update(names)
        candidates = matches if candidates is None else candidates & matches
        if not candidates:
            return []
    return sorted(_index.keys() if candidates is None else candidates)


def _query_tokens(raw: str) -> list[str]:
    """把查询串按驼峰/空白拆成检索词,使查词与索引的拆词一致。

    'createRect' 与 'create rect' 等价;纯单字符等拆不出词的输入退回原始词,
    以保留既有的子串匹配行为(不因拆词把查询变空而放大召回)。
    """
    tokens = _tokenize_name(raw)
    if tokens:
        return tokens
    return [word.casefold() for word in raw.split() if word]


def _flatten_search(raw_query: str, prefix_filter: str | None = None) -> list[str]:
    """压平兜底:去掉大小写边界与空白后做子串匹配。

    仅当精确匹配与拆词匹配都落空时使用,用于接住 'createrect' 这类无大小写边界、
    拆不出词的输入。
    """
    flattened = re.sub(r"[\s_]+", "", raw_query.casefold())
    if not flattened:
        return []
    return sorted(
        name for name, entry in _index.items()
        if (not prefix_filter or entry.get("prefix") == prefix_filter)
        and flattened in name.casefold()
    )


def search_page(prefix: str = "", keywords: str = "", offset: int = 0, limit: int = 30) -> dict:
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 500:
        raise ValueError("offset must be a nonnegative integer; limit must be 1..500")
    with _index_lock:
        _build_index()
        prefix = prefix.strip()
        raw_query = keywords.strip()
        query = raw_query.casefold()
        exact = [n for n in _index if n.casefold() == query and (not prefix or _index[n]["prefix"] == prefix)]
        matches = exact or _search_by_tokens(_query_tokens(raw_query), prefix or None)
        if not matches:
            matches = _flatten_search(raw_query, prefix or None)
        names = matches[offset:offset + limit]
        return {"names": names, "total": len(matches), "offset": offset, "limit": limit,
                "next_offset": offset + len(names) if offset + len(names) < len(matches) else None}


def search_by_components(prefix: str = "", keywords: str = "", offset: int = 0, limit: int = 30) -> list[str]:
    """Backward compatible list API; search_page additionally reports totals."""
    return search_page(prefix, keywords, offset, limit)["names"]


def _extract_full(func_name: str, html_text: str) -> dict | None:
    topic = extract_topic(html_text, func_name)
    if not topic:
        return None
    return _extract_full_from_topic(func_name, topic)


def query_function(func_name: str, doc_root: str | None = None) -> dict | None:
    """Return normalized function details without requiring the HTML corpus."""
    with _index_lock:
        _build_index(doc_root)
        entry = _index.get(func_name)
        if entry is None:
            return None
        # Do not expose nested mutable runtime data to callers.
        entry = deepcopy(entry)
    decl = entry.get("decl") or []
    if not decl or not decl[0].get("text"):
        return None
    return {**entry, "name": func_name}


def entries(names: list[str]) -> list[dict]:
    """按名字取记录的深拷贝，顺序与 ``names`` 一致（未知名字给 ``{}``）。

    搜索页渲染需要记录本体。走这里而不是让调用方去读 ``_index``：既守住"不把可变
    运行时数据交出去"，也让渲染层与索引实现解耦（渲染层只认记录，不认索引）。
    """
    with _index_lock:
        _build_index()
        return [deepcopy(_index.get(name, {})) for name in names]


def suggest_names(func_name: str, limit: int = 5, prefix: str = "") -> list[str]:
    """给出与 func_name 相近的官方函数名,供“未找到”时提示。

    先用名称编辑距离(处理拼写,如 dbCreateRct → dbCreateRect),再用拆词重叠兜底
    (处理片段、词序)。拼写优先是刻意的:公共 token(如 db/create)会让一大族函数平票,
    仅靠拆词重叠无法把真正接近的那个排上来。prefix 非空时只在同前缀内给建议。
    """
    query = func_name.strip()
    if not query:
        return []
    prefix = prefix.strip()
    with _index_lock:
        _build_index()
        names = [n for n in _index if not prefix or _index[n].get("prefix") == prefix]
        tokens = {name: set(_index[name].get("tokens", [])) for name in names}

    suggestions: list[str] = []
    seen: set[str] = set()

    folded = {name.casefold(): name for name in names}
    for close in difflib.get_close_matches(query.casefold(), list(folded), n=limit, cutoff=0.6):
        name = folded[close]
        if name not in seen:
            seen.add(name)
            suggestions.append(name)
    if len(suggestions) >= limit:
        return suggestions

    q_tokens = set(_tokenize_name(query))
    if q_tokens:
        ranked = sorted(
            ((-len(q_tokens & tokens[name]), len(name), name)
             for name in names if q_tokens & tokens[name])
        )
        for _, _, name in ranked:
            if name not in seen:
                seen.add(name)
                suggestions.append(name)
            if len(suggestions) >= limit:
                break
    return suggestions


