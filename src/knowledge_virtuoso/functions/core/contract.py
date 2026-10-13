#!/usr/bin/env python3
"""knowledge_virtuoso.functions.core.contract — 函数记录的契约与校验。

**与来源无关**：官方索引和 custom 索引是同一个记录契约（v3 envelope），谁写进来的
记录都要过这里。派生字段（prefix/tokens）不落盘，加载时按函数名无条件重算。
"""

from __future__ import annotations

import re
from copy import deepcopy

_SCHEMA_VERSION = 3
_TOKEN_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[0-9]+")
_NAME_RE = re.compile(r"^[a-z][a-zA-Z0-9_]+$")
_PREFIX_RE = re.compile(r"^([a-z]+)[A-Z]")
# 加载时由函数名重算的派生字段，不写进索引文件。
_DERIVED_KEYS = ("prefix", "tokens")


def _tokenize_name(name: str) -> list[str]:
    return [part.lower() for part in _TOKEN_RE.findall(name) if len(part) >= 2]


def _rebuild_runtime_indexes(entries: dict[str, dict]) -> tuple[dict, dict, dict]:
    """Validate query-consumed types and build private indexes without publishing."""
    if not isinstance(entries, dict) or not entries:
        raise ValueError("function records must be a nonempty object")
    index, keywords, prefixes = {}, {}, {}

    def require(value, expected, label):
        if not isinstance(value, expected):
            raise ValueError(f"{label} must be {expected.__name__}")

    def arg_items(value, label):
        require(value, list, label)
        for row in value:
            require(row, dict, label)
            require(row.get("name"), str, f"{label}.name")
            require(row.get("desc"), str, f"{label}.desc")
            if row.get("values") is not None:
                require(row["values"], list, f"{label}.values")
                for item in row["values"]:
                    require(item, dict, f"{label}.values item")
                    require(item.get("value"), str, f"{label}.values.value")

    def arguments_block(value, label):
        require(value, dict, label)
        require(value.get("root"), dict, f"{label}.root")
        arg_items(value["root"].get("items", []), f"{label}.root.items")
        require(value.get("lists", []), list, f"{label}.lists")
        for item in value["lists"]:
            require(item, dict, f"{label}.lists item")
            require(item.get("title"), str, f"{label}.lists.title")
            if item.get("parent") is not None:
                require(item["parent"], dict, f"{label}.lists.parent")
            arg_items(item.get("items", []), f"{label}.lists.items")

    for name, raw in entries.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("function name must be a nonempty string")
        require(raw, dict, name)
        entry = deepcopy(raw)
        # prefix / tokens 不落盘、加载时无条件由函数名重算（不信任文件里的旧值）。
        prefix_match = _PREFIX_RE.match(name)
        entry["prefix"] = prefix_match.group(1) if prefix_match else ""
        entry["tokens"] = _tokenize_name(name)
        require(entry.get("where", {}), dict, f"{name}.where")
        require(entry["where"].get("file", ""), str, f"{name}.where.file")
        require(entry.get("decl", []), list, f"{name}.decl")
        for item in entry["decl"]:
            require(item, dict, f"{name}.decl item")
            require(item.get("text"), str, f"{name}.decl item text")
        require(entry.get("sections", {}), dict, f"{name}.sections")
        for key, section in entry["sections"].items():
            require(section, dict, f"{name}.sections.{key}")
            if key == "arguments":
                arguments_block(section, f"{name}.sections.arguments")
            elif key == "returns":
                require(section.get("items", []), list, f"{name}.sections.returns.items")
                for row in section["items"]:
                    require(row, dict, f"{name}.sections.returns.items item")
                    require(row.get("value"), str, f"{name}.sections.returns.items.value")
                    # desc 是渲染直接取的键（`item['desc']`），漏检会让"能加载"的记录在查询时崩。
                    require(row.get("desc"), str, f"{name}.sections.returns.items.desc")
            elif "text" in section:
                require(section["text"], str, f"{name}.sections.{key}.text")
            if "links" in section:
                require(section["links"], list, f"{name}.sections.{key}.links")
        require(entry.get("field_status", {}), dict, f"{name}.field_status")
        for key, value in entry["field_status"].items():
            require(value, str, f"{name}.field_status.{key}")
        require(entry.get("status", "active"), str, f"{name}.status")
        index[name] = entry
        for token in entry["tokens"]:
            keywords.setdefault(token, set()).add(name)
        if entry["prefix"]:
            prefixes.setdefault(entry["prefix"], set()).add(name)
    return index, keywords, prefixes
