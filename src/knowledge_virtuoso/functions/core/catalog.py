#!/usr/bin/env python3
"""Parse the official IC618 SKILL callable-function documentation.

The committed index is deliberately limited to official SKILL *callables*.  It is
not a general symbol index: environment settings, types, aliases, C++ API pages,
and empty topic markers are excluded.  The HTML corpus has several historical
markup styles, so parsing is structural and uses only the Python standard
library.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator
from threading import RLock
from copy import deepcopy

from knowledge_virtuoso._paths import index_path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX_JSON = index_path("functions")
_SCHEMA_VERSION = 3

# These are the docsets whose entries are in scope for the callable SKILL API.
# This is an inclusion policy, not merely a preference when de-duplicating.
_SKILL_DOC_DIRS = {
    "sklangref", "sklanguser", "skdfref", "skartistref", "sklayoutref",
    "sktechfile", "skuiref", "skuirefCompat", "skcompref", "skdevref",
    "skipcref", "skoopref", "skpcellref", "sktransrefOA",
    "oceanref", "adexlSKILLref", "amsskillref", "maeSKILLref",
    "rodskillref", "caiskill", "constraintsSKILL", "vivaxlskill",
    "verifierSkillRef", "parasimSKILL", "netlistsimulateref", "ocnxl", "aelref",
}

_TOKEN_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[0-9]+")
_NAME_RE = re.compile(r"^[a-z][a-zA-Z0-9_]+$")
_PREFIX_RE = re.compile(r"^([a-z]+)[A-Z]")
_TOPIC_START_RE = re.compile(
    r"<!--\s*\[TOPIC_START_OPEN\](?P<meta>.*?)\[TOPIC_START_CLOSE\]\s*-->",
    re.DOTALL,
)
_TOPIC_ATTR_RE = re.compile(r"\[TOPIC_START_ATTR\](?P<key>[^=\s]+)=(?P<value>[^\r\n]*)")
_TOPIC_END_RE = re.compile(r"<!--\s*\[TOPIC_END\]\s*-->", re.DOTALL)

# Public module state is intentionally kept as the flat map used by the MCP
# server.  The on-disk v2 envelope is normalized when loaded.
_index: dict[str, dict] = {}
_keyword_index: dict[str, set[str]] = {}
_prefix_index: dict[str, set[str]] = {}
_index_built = False
_last_report: dict[str, object] = {}
_index_lock = RLock()
_index_source: str | None = None
_index_lengths: tuple[int, int, int] = (0, 0, 0)


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["_Node | str"] = field(default_factory=list)
    order: int = 0


class _TopicHTMLParser(HTMLParser):
    """Tolerant tiny tree builder for the old, frequently malformed HTML."""

    _AUTO_CLOSE = {
        "p": {"p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "dl"},
        "td": {"td", "th", "tr"},
        "th": {"td", "th", "tr"},
        "tr": {"tr"},
        "dd": {"dd", "dt"},
        "dt": {"dd", "dt"},
    }
    _VOID = {"br", "hr", "img", "meta", "link", "input", "area", "base", "embed", "param", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self._order = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        while len(self.stack) > 1 and tag in self._AUTO_CLOSE.get(self.stack[-1].tag, set()):
            self.stack.pop()
        self._order += 1
        node = _Node(tag, {k.lower(): v or "" for k, v in attrs}, order=self._order)
        self.stack[-1].children.append(node)
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)


def _parse_topic_html(topic: str) -> _Node:
    parser = _TopicHTMLParser()
    parser.feed(topic)
    parser.close()
    return parser.root


def _walk(node: _Node) -> Iterator[_Node]:
    yield node
    for child in node.children:
        if isinstance(child, _Node):
            yield from _walk(child)


def _node_text(node: _Node, *, line_breaks: bool = False) -> str:
    pieces: list[str] = []
    breaks = {"br", "p", "div", "li", "tr", "dd", "dt", "pre", "dl", "h1", "h2", "h3", "h4", "h5", "h6"}

    def visit(item: _Node | str) -> None:
        if isinstance(item, str):
            pieces.append(item)
            return
        if item.tag == "br":
            pieces.append("\n")
            return
        for c in item.children:
            visit(c)
        if item.tag in breaks:
            pieces.append("\n")

    visit(node)
    text = unescape("".join(pieces)).replace("\xa0", " ")
    if line_breaks:
        return "\n".join(re.sub(r"[ \t]+", " ", part).strip() for part in text.splitlines() if part.strip())
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    """Compatibility helper: return normalized visible HTML text."""
    return _node_text(_parse_topic_html(text))


def _normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(":.").casefold()


_RETURNS_LABEL_RE = re.compile(r"^(?:values? returned|return values?|returns)$")

# 允许取值表的行：单个 'symbol 字面量（如 'single）。带第二个 token 的行（如
# 'name t_name）是属性列表字段，不算取值表。
_VALUE_ROW_RE = re.compile(r"'[A-Za-z_][\w-]*")

# 官方文档里标题本身的排版异常，逐字照抄（每例 1 个函数）：
# asiMapInstanceName「value returned\」、nlGetModelName「value returne」、
# axlToolSetSetupOptions「value returnedz」、dbCellViewHasVirtHier「value returned4」、
# dbDeleteSigNetExpr「values return」、ocnxlOutputSpiceScript「.value returned」、
# vfoGRMaximizeShapes「value returnedd」。
# 只做字面量精确匹配，不做模糊容错——宽松到按“含 return”判定的规则会把
# geHiDragFig 的「Example 1 With Returned Value」这类示例标题误判为返回值小节。
_RETURNS_LABEL_TYPOS = frozenset({
    "value returned\\", "value returne", "value returnedz", "value returned4",
    "values return", ".value returned", "value returnedd",
})


# 规范节名及其在官方文档里的标题写法（实测于 7667 个函数 topic）。
# 归一原则：单复数、大小写统一到同一规范键；example 另用前缀规则覆盖编号与带描述的
# 写法（example 1、example: xxx、exampleexample、example for integrators …）。
_SECTION_LABELS = (
    ("description", ("description",)),
    ("arguments", ("argument", "arguments")),
    ("example", ("example", "examples")),
    ("reference", ("reference", "references", "related topic", "related topics", "see also")),
    ("related_functions", ("related function", "related functions")),
    ("prerequisites", ("prerequisite", "prerequisites")),
    ("additional_information", ("additional information",)),
    ("interactive_function", ("interactive function",)),
    ("associated_options", ("associated option", "associated options")),
    ("option_descriptions", ("option description", "option descriptions")),
    ("purpose", ("purpose",)),
    ("format", ("format",)),
    ("definition", ("definition",)),
    ("overview", ("overview",)),
    ("errors", ("error", "errors", "error conditions")),
)


# 索引 sections / field_status 覆盖的规范节名（顺序固定，便于对照 docs/index-v3-design.md）。
_CANONICAL_SECTIONS = (
    "description", "arguments", "returns", "example", "reference", "related_functions",
    "prerequisites", "additional_information", "interactive_function", "associated_options",
    "option_descriptions", "purpose", "format", "definition", "overview", "errors",
)

# sections 里结构化构造的节（其余节走 _section_content 的通用整理）。
_EXPLICIT_SECTIONS = ("description", "arguments", "returns", "example")


def _list_type(title: str) -> str | None:
    """从子参数列表标题里取括号内的类型名，如 ``Subrectangle Arguments (l_subrectArgs)``。"""
    match = re.search(r"\(([^)]+)\)", title)
    return match.group(1).strip() if match else None


def _arg_type(name: str) -> str:
    """取参数名的类型 token（末词，去掉列表省略号），如 ``?subrectArgs l_subrectArgs``。"""
    return name.replace("...", "").split()[-1] if name.strip() else ""


def _find_parent_arg(list_type: str | None, root_items: list[dict]) -> dict | None:
    """按类型名把子参数列表连到根参数上；匹配忽略大小写，不唯一时标 ambiguous。"""
    if not list_type:
        return None
    needle = list_type.casefold()
    hits = [a for a in root_items if needle in a["name"].casefold()]
    if len(hits) == 1:
        match = "exact" if list_type in hits[0]["name"] else "case_insensitive"
        return {"arg": hits[0]["name"], "type": _arg_type(hits[0]["name"]), "match": match}
    return {"arg": None, "type": None, "match": "ambiguous"} if hits else None


def _arg_item(row: dict) -> dict:
    return {"name": row["name"], "desc": row["desc"], "values": row.get("values")}


def _arguments_content(root_group: dict | None, root_title: str | None) -> dict:
    """把参数分组树整理为 ``{root:{title,items}, lists:[…]}``（见设计文档 2.2）。

    根参数 = 根组自身的直属参数，加上名为 root_title 的节内子范围组；
    其余子组都是"子参数列表"，按标题括号里的类型名连到根参数上。
    """
    root_items: list[dict] = []
    lists: list[dict] = []
    if root_group:
        root_items = [_arg_item(a) for a in root_group.get("arguments", [])]
        for group in root_group.get("groups", []):
            items = [_arg_item(a) for a in group.get("arguments", [])]
            if root_title is not None and group["name"] == root_title:
                root_items = root_items + items  # 节内子范围并入根参数
                continue
            lists.append({
                "title": group["name"],
                "list_type": _list_type(group["name"]),
                "parent": None,
                "items": items,
            })
    for entry in lists:
        entry["parent"] = _find_parent_arg(entry["list_type"], root_items)
    return {"root": {"title": root_title, "items": root_items}, "lists": lists}


def _section_content(section: dict[str, object] | None) -> dict:
    """把一节内容如实整理为 ``{text}`` / ``{items}``（有表格时并给结构化行）。"""
    if not section:
        return {}
    text, _ = _desc_from_section(section)
    content: dict = {}
    if text:
        content["text"] = text
    rows = [
        row
        for _, tag, node, _ in section["items"]
        if tag == "table"
        for row in _parse_table_items(node, "name")
    ]
    if rows:
        content["items"] = rows
    return content


def _section_label(text: str) -> tuple[str | None, str]:
    """Return (semantic section, heading remainder), if ``text`` is a label."""
    normalized = _normalize_label(text)
    # 返回值标题在官方文档里单复数混用（实测全库：Value Returned 7740、Returns 2817、
    # Return Values 770、Return Value 662、Values Returned 378 次）。此前只认前三种，
    # 实测导致 290 个函数的返回值小节未被识别、返回值表被并进参数小节。
    if _RETURNS_LABEL_RE.match(normalized) or normalized in _RETURNS_LABEL_TYPOS:
        return "returns", ""
    if normalized.startswith("example"):
        return "example", ""
    if normalized.startswith("additional information"):
        return "additional_information", ""
    for section, labels in _SECTION_LABELS:
        for label in labels:
            if normalized == label:
                return section, ""
            # ROD 的 "Arguments<br><br>Master Path Arguments" 这类合并标题：先归
            # arguments，remainder 交给调用方判定是节内子范围还是另一个节。
            if section == "arguments" and normalized.startswith(label + " "):
                return section, text.strip()[len(label):].strip(" :\t\r\n")
    return None, ""


def _semantic_items(root: _Node) -> list[tuple[int, str, _Node, str]]:
    """Return ordered heading/paragraph/table blocks used to delimit sections."""
    items: list[tuple[int, str, _Node, str]] = []
    def blocks(node):
        for child in node.children:
            if isinstance(child, _Node):
                yield child
                if child.tag not in {"table", "pre", "p"}:
                    yield from blocks(child)
    for node in blocks(root):
        if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "pre"}:
            items.append((node.order, node.tag, node, _node_text(node, line_breaks=True)))
    return sorted(items, key=lambda item: item[0])


def _sections(root: _Node) -> dict[str, dict[str, object]]:
    items = _semantic_items(root)
    starts: list[tuple[int, str, str]] = []
    for pos, (_, tag, _, text) in enumerate(items):
        if tag not in {"h1", "h2", "h3", "h4", "h5", "h6", "p"}:
            continue
        section, remainder = _section_label(text)
        if section:
            starts.append((pos, section, remainder))

    result: dict[str, dict[str, object]] = {}
    for start_no, (start, section, remainder) in enumerate(starts):
        end = starts[start_no + 1][0] if start_no + 1 < len(starts) else len(items)
        if section in result:
            result[section]["items"].extend(items[start + 1:end])
            continue
        result[section] = {
            "remainder": remainder,
            "items": items[start + 1:end],
            "present": True,
        }
    return result


def _desc_from_section(section: dict[str, object] | None) -> tuple[str, str]:
    if not section:
        return "", "not_documented"
    texts = [text for _, tag, _, text in section["items"] if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table"} and text]
    value = "\n".join(texts).strip()
    if not value:
        return "", "unparsed"
    if _normalize_label(value) in {"none", "n/a"}:
        return "", "documented_none"
    return value, "present"


def _descendants_directly_in(node: _Node, tag: str, container: _Node) -> list[_Node]:
    found: list[_Node] = []

    def visit(current: _Node, inside_nested_container: bool = False) -> None:
        for child in current.children:
            if not isinstance(child, _Node):
                continue
            nested = inside_nested_container or (child is not container and child.tag == container.tag)
            if child.tag == tag and not nested:
                found.append(child)
            visit(child, nested)

    visit(node)
    return found


def _table_rows(table: _Node) -> list[list[tuple[str, dict[str, str]]]]:
    rows: list[list[tuple[str, dict[str, str]]]] = []
    for tr in _descendants_directly_in(table, "tr", table):
        cells = [child for child in tr.children if isinstance(child, _Node) and child.tag in {"td", "th"}]
        if not cells:
            # Malformed HTML may wrap cells in a tbody-like node.
            cells = [n for n in _walk(tr) if n.tag in {"td", "th"}]
        row = [(_node_text(cell, line_breaks=True), cell.attrs) for cell in cells]
        if row:
            rows.append(row)
    return rows


def _is_column_header(text: str) -> bool:
    return _normalize_label(text) in {"argument", "arguments", "description", "value", "value returned", "return values"}


def _append_text(old: str, extra: str) -> str:
    return (old + "\n" + extra).strip() if old and extra else old or extra


def _parse_table_items(table: _Node, key: str) -> list[dict[str, str]]:
    """Read a two-column documentation table, including split continuation rows."""
    result: list[dict[str, str]] = []
    for row in _table_rows(table):
        texts = [text.strip() for text, _ in row]
        nonempty = [text for text in texts if text]
        if not nonempty or all(_is_column_header(text) for text in nonempty):
            continue
        first = texts[0] if texts else ""
        rest = "\n".join(text for text in texts[1:] if text).strip()
        if len(texts) == 1:
            # A full-width row is either a standalone name/value or a heading.
            if _is_column_header(first):
                continue
            item = {key: first, "desc": ""}
            result.append(item)
            continue
        # Certain older layouts place the visual two columns in a nested table.
        # In that form our structural row has exactly one visible cell, but the
        # flattened text is still an identifier followed by prose.  Do not use
        # this fallback when the row already had separate visible cells.
        if not rest and first and " " in first:
            match = re.match(r"^(\S+)\s+(.+)$", first, re.DOTALL)
            if match and not re.fullmatch(r"\?[A-Za-z_][A-Za-z0-9_]*\s+\S+", first):
                first, rest = match.group(1), match.group(2)
        if first:
            result.append({key: first, "desc": rest})
        elif result and rest:
            result[-1]["desc"] = _append_text(result[-1]["desc"], rest)
    return result


def _heading_level(tag: str) -> int:
    return int(tag[1]) if len(tag) == 2 and tag.startswith("h") and tag[1].isdigit() else 99


def _make_group(name: str, level: int) -> dict:
    return {"name": name, "arguments": [], "groups": [], "source_heading_level": level}


def _drop_rows(groups: list[dict], names: set[str]) -> None:
    """从分组树中移除指定参数名的行。"""
    for group in groups:
        group["arguments"] = [a for a in group["arguments"] if a.get("name") not in names]
        _drop_rows(group.get("groups", []), names)


def _merged_return_rows(items: list) -> list[dict[str, str]]:
    """合并标题下的返回值表：尾部那张既非参数、也非允许取值的表。"""
    tables = [node for _, tag, node, _ in items if tag == "table"]
    if not tables:
        return []
    rows = _parse_table_items(tables[-1], "value")
    values = [r["value"].strip() for r in rows]
    if not values or any(v.startswith("?") for v in values) or all(v.startswith("'") for v in values):
        return []
    return rows


def _parse_argument_section(
    section: dict[str, object] | None,
) -> tuple[list[dict[str, str]], list[dict], str, list[dict[str, str]], str | None]:
    """返回 (展开后的参数, 分组, 状态, 合并标题带来的返回值, 根范围标题)。

    标题形如 ``Arguments<br>Values Returned`` 时，后半是独立小节而非节内子范围：此时
    不建参数分组，该节尾部的非参数表按内容归入 returns。
    标题形如 ``Arguments<br><br>Master Path Arguments`` 时，后半是**节内子范围**，
    作为根参数的标题返回（root_title）。
    """
    if not section:
        return [], None, "not_documented", [], None
    items = section["items"]
    section_text = " ".join(text for _, _, _, text in items)
    if _normalize_label(section_text) in {"none", "n/a"}:
        return [], None, "documented_none", [], None

    root = _make_group("Arguments", 0)
    stack = [root]
    merged_into: str | None = None
    root_title: str | None = None
    remainder = str(section.get("remainder", "")).strip()
    if remainder:
        merged_into, _ = _section_label(remainder)
        if merged_into:
            pass  # 后半是独立小节，不建分组
        else:
            root_title = remainder
            group = _make_group(remainder, 4)
            root["groups"].append(group)
            stack.append(group)

    saw_table = False
    for _, tag, node, text in items:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and text:
            # Non-semantic headings inside the Arguments section identify groups.
            label, _ = _section_label(text)
            if label is None and "argument" in _normalize_label(text):
                level = _heading_level(tag)
                while len(stack) > 1 and stack[-1]["source_heading_level"] >= level:
                    stack.pop()
                group = _make_group(text, level)
                stack[-1]["groups"].append(group)
                stack.append(group)
        elif tag == "table":
            saw_table = True
            rows = _parse_table_items(node, "name")
            if rows and stack[-1]["arguments"] and all(
                _VALUE_ROW_RE.fullmatch(row["name"].strip()) for row in rows
            ):
                # 允许取值表：行首是 'symbol 字面量，且紧跟在一个参数之后。
                stack[-1]["arguments"][-1]["values"] = [
                    {"value": row["name"], "desc": row["desc"]} for row in rows
                ]
            else:
                stack[-1]["arguments"].extend(rows)

    def flatten(group: dict, path: tuple[str, ...]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        current_path = path + ((group["name"],) if group["name"] != "Arguments" else ())
        for item in group["arguments"]:
            copied = dict(item)
            if current_path:
                copied["group"] = " / ".join(current_path)
            result.append(copied)
        for child in group["groups"]:
            result.extend(flatten(child, current_path))
        return result

    merged_returns: list[dict[str, str]] = []
    if merged_into == "returns":
        merged_returns = _merged_return_rows(items)
        if merged_returns:
            _drop_rows([root], {r["value"] for r in merged_returns})

    flat = flatten(root, ())
    if flat:
        return flat, root, "present", merged_returns, root_title
    return [], root, "text_fallback" if section_text and not saw_table else "unparsed", merged_returns, root_title


def _parse_return_section(section: dict[str, object] | None) -> tuple[list[dict[str, str]], str]:
    if not section:
        return [], "not_documented"
    items = section["items"]
    text = " ".join(value for _, _, _, value in items)
    if _normalize_label(text) in {"none", "n/a"}:
        return [], "documented_none"
    values: list[dict[str, str]] = []
    saw_table = False
    for _, tag, node, _ in items:
        if tag != "table":
            continue
        saw_table = True
        # Return sections in ROD documents are followed by explanatory tables
        # whose first cells are numbered steps ("1.", "2.", ...).  A return
        # value must be a SKILL value token, not a numbered procedure step.
        for item in _parse_table_items(node, "value"):
            value = item["value"]
            if re.fullmatch(r"\d+\.", value):
                continue
            values.append({"value": value, "desc": item["desc"]})
    if values:
        return values, "present"
    return [], "text_fallback" if text and not saw_table else "unparsed"


def _signature_candidates(root: _Node, func_name: str) -> list[str]:
    candidates: list[str] = []
    call_re = re.compile(rf"\b{re.escape(func_name)}\s*\(")
    boundary = min((n.order for n in _walk(root) if n.tag in {"h4", "p"} and _section_label(_node_text(n))[0]), default=10**9)
    for node in _walk(root):
        if node.order >= boundary or node.tag not in {"dl", "pre", "code"}:
            continue
        text = _node_text(node, line_breaks=True)
        if call_re.search(text):
            candidates.append(text)
    return list(dict.fromkeys(candidates))


def extract_signature(topic: str, func_name: str | None = None) -> str | None:
    """Select a usable SKILL declaration from all declaration-bearing blocks."""
    root = _parse_topic_html(topic)
    if func_name is None:
        match = re.search(r"\b([a-z][a-zA-Z0-9_]+)\s*\(", _node_text(root))
        func_name = match.group(1) if match else ""
    candidates = _signature_candidates(root, func_name)
    if not candidates:
        return None
    # Prefer a compact declaration; ROD declarations are intentionally long.
    candidates.sort(key=lambda value: (0 if "=>" in value else 1, len(value)))
    return candidates[0]


def _is_callable_signature(signature: str | None, func_name: str) -> bool:
    if not signature or not re.search(rf"\b{re.escape(func_name)}\s*\(", signature):
        return False
    lower = signature.casefold()
    return not any(marker in lower for marker in ("typedef", "struct ", "enum ", "class "))


def _topic_status(topic: str) -> str:
    text = _node_text(_parse_topic_html(topic)).casefold()
    return "deprecated" if "deprecated" in text else "active"


def _extract_full_from_topic(func_name: str, topic: str) -> dict:
    """从一个 topic 提取内容：``decl`` + ``sections`` + ``field_status`` + ``status``（v3）。"""
    root = _parse_topic_html(topic)
    sections = _sections(root)
    declaration = extract_signature(topic, func_name) or ""
    arguments, argument_root, argument_status, merged_returns, root_title = (
        _parse_argument_section(sections.get("arguments")))
    returns, return_status = _parse_return_section(sections.get("returns"))
    if not returns and merged_returns:
        # 合并标题（Arguments<br>Values Returned）带来的返回值。
        returns, return_status = merged_returns, "present"
    description, description_status = _desc_from_section(sections.get("description"))
    example, example_status = _desc_from_section(sections.get("example"))

    content: dict[str, dict] = {}
    if sections.get("description"):
        content["description"] = {"text": description}
    if sections.get("arguments"):
        content["arguments"] = _arguments_content(argument_root, root_title)
        arguments_text = _desc_from_section(sections.get("arguments"))[0]
        if arguments_text:
            content["arguments"]["text"] = arguments_text
    if sections.get("returns") or merged_returns:
        content["returns"] = {"items": returns}
        returns_text = _desc_from_section(sections.get("returns"))[0]
        if returns_text:
            content["returns"]["text"] = returns_text
    if sections.get("example"):
        content["example"] = {"text": example}
    for key in _CANONICAL_SECTIONS:
        if key in _EXPLICIT_SECTIONS:
            continue
        section = sections.get(key)
        if section is None:
            continue
        content[key] = _section_content(section)
        if key == "reference":
            content[key]["links"] = [
                {"text": _node_text(node), "href": node.attrs["href"]}
                for _, _, block, _ in section["items"]
                for node in _walk(block) if "href" in node.attrs
            ]

    field_status = {key: ("present" if key in content else "not_documented")
                    for key in _CANONICAL_SECTIONS}
    field_status.update({
        "description": description_status,
        "arguments": argument_status,
        "returns": return_status,
        "example": example_status,
        "decl": "present" if declaration else "unparsed",
    })
    decl = [{"text": declaration, "shared_from": None}]
    decl += [{"text": text, "shared_from": None}
             for text in _signature_candidates(root, func_name)
             if text and text != declaration]
    return {
        "decl": decl,
        "sections": content,
        "field_status": field_status,
        "status": _topic_status(topic),
    }


def extract_description(topic: str) -> str:
    return _extract_full_from_topic("", topic)["sections"].get("description", {}).get("text", "")


def extract_arguments(topic: str) -> list[dict[str, str]]:
    arguments = _extract_full_from_topic("", topic)["sections"].get("arguments", {})
    return arguments.get("root", {}).get("items", [])


def extract_returns(topic: str) -> list[dict[str, str]]:
    return _extract_full_from_topic("", topic)["sections"].get("returns", {}).get("items", [])


def extract_example(topic: str) -> str:
    return _extract_full_from_topic("", topic)["sections"].get("example", {}).get("text", "")


def _iter_topics(html_text: str) -> Iterator[tuple[dict[str, str], str]]:
    for match in _TOPIC_START_RE.finditer(html_text):
        end = _TOPIC_END_RE.search(html_text, match.end())
        if not end:
            continue
        attrs = {m.group("key"): m.group("value").strip() for m in _TOPIC_ATTR_RE.finditer(match.group("meta"))}
        body = html_text[match.end():end.start()]
        headings = [m for m in re.finditer(r"<h3\b[^>]*>.*?</h3>", body, re.DOTALL | re.IGNORECASE)
                    if _NAME_RE.fullmatch(strip_html(m.group(0))) and _section_label(strip_html(m.group(0)))[0] is None]
        if len(headings) > 1:
            # Some official markers wrap several independent function headings.
            for i, heading in enumerate(headings):
                title = strip_html(heading.group(0))
                section = body[heading.start():headings[i + 1].start() if i + 1 < len(headings) else len(body)]
                if _NAME_RE.fullmatch(title) and extract_signature(section, title):
                    yield {**attrs, "marker_text": attrs.get("text", ""), "text": title}, section
        else:
            yield attrs, body


def extract_topic(html_text: str, func_name: str) -> str:
    """Return the exact topic body for compatibility with earlier callers."""
    for attrs, topic in _iter_topics(html_text):
        if func_name in _topic_names(attrs, topic):
            return topic
    return ""


def _docset(rel_path: str) -> str:
    return Path(rel_path).as_posix().split("/", 1)[0]


def _is_skill_doc(rel_path: str) -> bool:
    return _docset(rel_path) in _SKILL_DOC_DIRS


def _tokenize_name(name: str) -> list[str]:
    return [part.lower() for part in _TOKEN_RE.findall(name) if len(part) >= 2]


def _topic_names(attrs: dict, topic: str) -> list[str]:
    label = attrs.get("text", "")
    if label.startswith("caar, caaar,"):
        # Names occur explicitly in the official possible-combinations paragraph.
        text = strip_html(topic)
        if "up to four characters" not in text or "The possible combinations are" not in text:
            return []
        paragraph = text.split("The possible combinations are", 1)[1].split(".", 1)[0]
        return sorted(set(re.findall(r"\bc[ad]{2,4}r\b", paragraph)))
    names = [part.strip() for part in label.split(",")]
    return names if all(_NAME_RE.fullmatch(n) for n in names) else []


def _candidate_entries(doc_root: str) -> tuple[dict[str, dict], dict[str, int]]:
    entries: dict[str, dict] = {}
    report: Counter[str] = Counter()
    root = Path(doc_root)
    if not root.is_dir():
        raise ValueError(f"doc_root is not a directory: {root}")

    # Propagate directory read errors instead of silently accepting a partial scan.
    def walk_error(error: OSError) -> None:
        raise error

    html_files = []
    for directory, dirs, files in os.walk(root, onerror=walk_error):
        if Path(directory) == root:
            dirs[:] = sorted(d for d in dirs if d in _SKILL_DOC_DIRS)
            continue
        html_files.extend(Path(directory) / name for name in files if name.endswith(".html"))
    for html_file in sorted(html_files):
        rel = html_file.relative_to(root).as_posix()
        docset = _docset(rel)
        if docset not in _SKILL_DOC_DIRS:
            continue
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        for attrs, topic in _iter_topics(text):
            report["topics_considered"] += 1
            names = _topic_names(attrs, topic)
            if not names:
                report["invalid_name"] += 1
                continue
            tree = _parse_topic_html(topic)
            anchors = list(dict.fromkeys(n.attrs.get("name") or n.attrs.get("id") for n in _walk(tree) if n.attrs.get("name") or n.attrs.get("id")))
            for name in names:
                full = _extract_full_from_topic(name, topic)
                declaration = full["decl"][0]["text"]
                if not declaration and (attrs.get("text") == "assoc, assq, assv"
                                        or attrs.get("text", "").startswith("caar, caaar,")):
                    shared = next((_node_text(n, line_breaks=True) for n in _walk(tree) if n.tag == "dl"), "")
                    if not shared:
                        continue
                    # 共享声明：声明文本与归属 topic 结构化记录，不再拼一句英文说明。
                    full["decl"] = [{"text": shared, "shared_from": attrs["text"]}]
                    full["field_status"]["decl"] = "shared_declaration"
                elif not _is_callable_signature(declaration, name):
                    report["no_callable_declaration"] += 1
                    continue
                where = {"file": rel, "topic": attrs.get("text", ""),
                         "marker_text": attrs.get("marker_text", attrs.get("text", "")),
                         "anchor": name if name in anchors else (anchors[0] if anchors else "")}
                entry = {"type": "function", "decl": full["decl"], "where": where,
                         "also_at": [], "sections": full["sections"],
                         "field_status": full["field_status"], "status": full["status"]}
                existing = entries.get(name)
                if existing is None:
                    entries[name] = entry
                elif existing["status"] == "deprecated" and entry["status"] == "active":
                    entry["also_at"] = existing["also_at"] + [where]
                    entries[name] = entry
                    report["duplicate_replaced"] += 1
                else:
                    existing["also_at"].append(where)  # 同名补充来源
                    report["duplicate_ignored"] += 1
    report["accepted_functions"] = len(entries)
    report["accepted_deprecated"] = sum(e["status"] == "deprecated" for e in entries.values())
    return dict(sorted(entries.items())), dict(report)


def scan_functions(doc_root: str) -> dict[str, str]:
    """Return only official documented SKILL callable names and source paths."""
    entries, _ = _candidate_entries(doc_root)
    return {name: entry["where"]["file"] for name, entry in entries.items()}


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
        entry.setdefault("prefix", "")
        entry.setdefault("tokens", _tokenize_name(name))  # 不落盘，加载时由函数名重算
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


def _canonical_index_path(path: str | Path) -> str:
    # Lexical normalization never stats disk on healthy queries. Symlink aliases
    # intentionally remain different sources (no filesystem hot reload).
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _memory_healthy(source: str) -> bool:
    """O(1) guard, not a detector for equal-size or nested-value corruption."""
    return (_index_built and _index_source == source
            and isinstance(_index, dict) and bool(_index)
            and isinstance(_keyword_index, dict) and isinstance(_prefix_index, dict)
            and (len(_index), len(_keyword_index), len(_prefix_index)) == _index_lengths)


def _publish(runtime: tuple[dict, dict, dict], source: str, report: dict) -> None:
    """Caller holds _index_lock; published dictionaries are never mutated here."""
    global _index, _keyword_index, _prefix_index, _index_source
    global _index_lengths, _index_built, _last_report
    _index, _keyword_index, _prefix_index = runtime
    _index_source = source
    _index_lengths = tuple(len(part) for part in runtime)
    _last_report = report
    _index_built = True


def _index_envelope(entries: dict[str, dict]) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "corpus": {
            "product": "Cadence IC618",
            "scope": "official-skill-callables",
        },
        "functions": dict(sorted(entries.items())),
    }


def _write_index(json_path: str | Path, entries: dict[str, dict]) -> None:
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _index_envelope(entries)
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def build_index_file(doc_root: str, output_path: str | Path) -> int:
    """Parse, validate, atomically persist, then publish one complete generation."""
    with _index_lock:
        source = _canonical_index_path(output_path)
        entries, report = _candidate_entries(doc_root)
        runtime = _rebuild_runtime_indexes(entries)
        _write_index(source, runtime[0])
        _publish(runtime, source, report)
        return len(runtime[0])


class IndexLoadError(RuntimeError):
    """Neither JSON nor configured official docs could restore the index."""


def _build_from_json(json_path: str | Path) -> tuple[dict, dict, dict]:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("index root must be an object")
    if "schema_version" in data:
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(
                f"索引格式版本不兼容（文件为 {data['schema_version']}，当前需要 {_SCHEMA_VERSION}）；"
                "请重建索引：knowledge-virtuoso-build functions")
        entries = data.get("functions")
    else:
        entries = data  # Legacy flat records; no invented documentation fields.
    return _rebuild_runtime_indexes(entries)


def _build_index(doc_root: str | None = None, index_json: str | Path | None = None) -> None:
    global _index_built
    source = _canonical_index_path(_DEFAULT_INDEX_JSON if index_json is None else index_json)
    with _index_lock:
        if _memory_healthy(source):
            return
        # Failed recovery/source switches must never serve the previous map.
        _index_built = False
        try:
            runtime = _build_from_json(source)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            json_reason = f"{type(exc).__name__}: {exc}"
        else:
            _publish(runtime, source, {})
            return
        root = doc_root if doc_root is not None else os.environ.get("VIRTUOSO_DOC_DIR")
        print(f"SKILL index JSON unavailable ({source}): {json_reason}; recovering from doc {root!r}", file=sys.stderr)
        try:
            if not root:
                raise ValueError(
                    f"doc_root not configured; set VIRTUOSO_DOC_DIR to rebuild {source}, "
                    f"or run: knowledge-virtuoso-build functions"
                )
            build_index_file(root, source)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            raise IndexLoadError(
                f"Index recovery failed. JSON {source}: {json_reason}; "
                f"doc {root!r}: {type(exc).__name__}: {exc}"
            ) from exc


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


def coverage_report() -> dict[str, object]:
    """Return the most recent HTML build classification statistics."""
    with _index_lock:
        return dict(_last_report)


def semantic_analysis(real_funcs: dict[str, str]) -> dict:
    prefixes = Counter()
    verbs = Counter()
    connectives = Counter()
    predicates = []
    qualifier_hi = []
    for name in real_funcs:
        match = _PREFIX_RE.match(name)
        if match:
            prefixes[match.group(1)] += 1
        match = re.match(r"^[a-z]+([A-Z][a-z]+)", name)
        if match:
            verbs[match.group(1)] += 1
        if re.search(r"[a-z]p$", name):
            predicates.append(name)
        if re.search(r"Hi[A-Z]", name) and not name.startswith("hi"):
            qualifier_hi.append(name)
        for connective in ("By", "To", "From", "Per", "For", "In"):
            if re.search(rf"{connective}[A-Z]", name):
                connectives[connective] += 1
    return {
        "prefixes": dict(prefixes.most_common()),
        "verbs": dict(verbs.most_common()),
        "connectives": dict(connectives.most_common()),
        "predicate_count": len(predicates),
        "predicate_samples": predicates[:10],
        "hi_qualifier_count": len(qualifier_hi),
        "hi_qualifier_samples": qualifier_hi[:10],
    }


def print_report(real: dict[str, str], analysis: dict) -> None:
    print("=" * 60)
    print("  SKILL 函数提取报告")
    print("=" * 60)
    print(f"  真实函数:         {len(real):>6}")
    for key, value in sorted(_last_report.items()):
        print(f"  {key:24s} {value}")
    print("\n  ── 前缀 Top 30 ──")
    for prefix, count in list(Counter(analysis["prefixes"]).most_common(30)):
        print(f"    {prefix:15s} {count:4d}")


def _build_cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="从 IC618 HTML 文档提取官方 SKILL 可调用函数索引")
    parser.add_argument("--doc-root", default=os.environ.get("VIRTUOSO_DOC_DIR"))
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--export-json", metavar="FILE")
    parser.add_argument("--report", action="store_true", help="输出构建覆盖统计")
    args = parser.parse_args()
    if not args.doc_root or not os.path.isdir(args.doc_root):
        parser.error(f"文档目录无效: {args.doc_root}")
    if args.export_json:
        count = build_index_file(args.doc_root, args.export_json)
        print(f"已导出 {count} 个官方 SKILL 可调用函数到 {args.export_json}")
        if args.report:
            print(json.dumps(coverage_report(), ensure_ascii=False, indent=2))
        return
    entries, report = _candidate_entries(args.doc_root)
    if args.export:
        Path(args.export).write_text("\n".join(entries) + "\n", encoding="utf-8")
        print(f"已导出 {len(entries)} 个函数名到 {args.export}")
        return
    _last_report.update(report)
    print_report({name: entry["where"]["file"] for name, entry in entries.items()},
                 semantic_analysis(entries))


def _query_cli() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m knowledge_virtuoso.functions.core.catalog <function_name> [doc_root]", file=sys.stderr)
        raise SystemExit(1)
    info = query_function(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    if info is None:
        print(f"未找到函数: {sys.argv[1]}")
        raise SystemExit(1)
    where = info.get("where", {})
    print(f"函数: {info['name']}\n签名: {info['decl'][0]['text']}\n来源: {where.get('file', '')}")
    sections = info.get("sections", {})
    description = sections.get("description", {}).get("text", "")
    if description:
        print(f"\n描述: {description}")
    arguments = sections.get("arguments", {})
    if arguments:
        print("\n参数:")
        for item in arguments.get("root", {}).get("items", []):
            print(f"  {item['name']} — {item['desc']}")
        for group in arguments.get("lists", []):
            print(f"  [{group['title']}]")
            for item in group.get("items", []):
                print(f"    {item['name']} — {item['desc']}")
    returns = sections.get("returns", {}).get("items", [])
    if returns:
        print("\n返回:")
        for item in returns:
            print(f"  {item['value']} — {item['desc']}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1].startswith("--"):
        _build_cli()
    else:
        _query_cli()
