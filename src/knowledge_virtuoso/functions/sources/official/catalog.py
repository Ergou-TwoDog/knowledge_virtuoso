#!/usr/bin/env python3
"""knowledge_virtuoso.official.catalog — 官方来源：解析 IC618 SKILL 文档。

收录范围只限官方 SKILL *可调用函数*：环境设置、类型、别名、C++ API 页、空 topic
标记都不收。HTML 语料有多种历史排版，所以解析是结构化的，只用标准库。
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator

from knowledge_virtuoso._paths import index_path
# 这两个正则在搬移时随契约一起去了 core/contract.py（"函数名的合法形状"与"前缀口径"两处
# 唯一的定义）。这里**必须**从契约取，不能自己再写一份：重建（`build_entries`）与报告统计
# 都按它们判名，两边漂移会让"能收进来的名字"和"索引里的 prefix"对不上。
from knowledge_virtuoso.functions.core.contract import _NAME_RE, _PREFIX_RE


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# 官方索引的落盘位置；来源接口 official/__init__.py 从这里取。
INDEX_PATH = index_path("functions")
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
_TOPIC_START_RE = re.compile(
    r"<!--\s*\[TOPIC_START_OPEN\](?P<meta>.*?)\[TOPIC_START_CLOSE\]\s*-->",
    re.DOTALL,
)
_TOPIC_ATTR_RE = re.compile(r"\[TOPIC_START_ATTR\](?P<key>[^=\s]+)=(?P<value>[^\r\n]*)")
_TOPIC_END_RE = re.compile(r"<!--\s*\[TOPIC_END\]\s*-->", re.DOTALL)


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


def _row_cell_count(tr: _Node) -> int:
    return sum(1 for child in tr.children if isinstance(child, _Node) and child.tag in {"td", "th"})


def _wrap_orphan_rows(root: _Node) -> None:
    """把裸 ``<tr>`` 收进合成表格。

    老式排版里 ``</table>`` 之后会继续出现属于同一张表的 ``<tr>``（实测 hiSetCursor 的
    光标常量表：前 37 行在 ``<table>`` 内，其后 165 个单元格以裸 ``<tr><td><p>`` 续排）。
    不处理时，这些单元格的 ``<p>`` 会被当成独立段落，整表内容只剩纯文本、没有条目。
    这里把同一父节点下连续出现（≥3 行）、且每行至少两个单元格的 ``<tr>`` 段包成
    ``<table>``，交由常规表格解析按行读取；少于 3 行不动，避免把版式行当表格。
    """
    def visit(node: _Node) -> None:
        if node.tag == "table":
            return
        rebuilt: list[_Node | str] = []
        run: list[_Node] = []

        def flush() -> None:
            if len(run) >= 3:
                rebuilt.append(_Node("table", {}, list(run), order=run[0].order))
            else:
                rebuilt.extend(run)
            run.clear()

        for child in node.children:
            if isinstance(child, _Node) and child.tag == "tr" and _row_cell_count(child) >= 2:
                run.append(child)
                continue
            # 行与行之间的空白文本节点（HTML 缩进）不能断开连续行，随行一起收进合成表。
            if isinstance(child, str) and not child.strip() and run:
                run.append(child)
                continue
            flush()
            rebuilt.append(child)
            if isinstance(child, _Node):
                visit(child)
        flush()
        node.children = rebuilt

    visit(root)


def _parse_topic_html(topic: str) -> _Node:
    parser = _TopicHTMLParser()
    parser.feed(topic)
    parser.close()
    _wrap_orphan_rows(parser.root)
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


# 索引 sections / field_status 覆盖的规范节名（顺序固定，便于对照 functions/README.md）。
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


_NAME_TOKEN_RE = re.compile(r"^(?:[?@])?[A-Za-z_][\w.>\-]*\(?\)?:?$")
_NAME_COLON_RE = re.compile(r"^([A-Za-z_][\w.]*):\s*\S")
_ENGLISH_WORD_RE = re.compile(r"[A-Z][a-z]+$")
_CONSTANT_SLASH_RE = re.compile(r"[A-Za-z_][\w.]*\s*/\s*\S+")


def _name_head(text: str) -> bool:
    """这一行是"名称行"还是"说明/散文行"（只用于首列被占位的行，见 _parse_table_items）。

    实测四种名称形状，其余一律按说明处理——判宽了会把 ``Valid Values: …``、
    ``For Sampling:``、``Note: …``、``Equivalent to setting …`` 这类散文切成假条目：

    1. 单个标识符——``hicArrow``；
    2. 名称与说明挤在同一格、冒号紧跟首个标识符——``gdmStateCI: File is managed…``；
    3. 恰好两个词、第二词不以小写开头——``t_viewName Symbol``；
    4. 常量与其值同格——``PCRE_CASELESS / 0x00000001``。

    首词是普通英文单词（``For``/``When``/``The``/``Note``/``See``）的一律不算名称。
    """
    tokens = text.split()
    if not tokens or _ENGLISH_WORD_RE.fullmatch(tokens[0]):
        return False
    match = _NAME_COLON_RE.match(text)
    if match and not _ENGLISH_WORD_RE.fullmatch(match.group(1)):
        return True
    if len(tokens) == 1:
        return bool(_NAME_TOKEN_RE.match(tokens[0]))
    if len(tokens) == 2 and _NAME_TOKEN_RE.match(tokens[0]) and not tokens[1][:1].islower():
        return True
    return bool(_CONSTANT_SLASH_RE.fullmatch(text))


def _parse_table_items(table: _Node, key: str) -> list[dict[str, str]]:
    """Read a documentation table, including split continuation rows.

    实测老式排版会把内容整体右移一格（项目符号图片或 ``&nbsp;`` 占住首列），
    例如 ``['', 'gdmStateCI: File is managed…']``；旧实现直接丢弃这类行，
    整表只剩纯文本。这里按行的**内容**判定：名称行照常建条目，散文行并入上一条目
    的说明（pcreCompile 的名字一行、说明下一行即属此类），两者都不是则不动。
    """
    result: list[dict[str, str]] = []
    for row in _table_rows(table):
        texts = [text.strip() for text, _ in row]
        nonempty = [text for text in texts if text]
        if not nonempty or all(_is_column_header(text) for text in nonempty):
            continue
        lead = next(index for index, text in enumerate(texts) if text)
        if lead:
            # 首列被占位：内容单元格看形状决定是名称还是上一行的说明。
            if not _name_head(texts[lead]):
                if result:
                    result[-1]["desc"] = _append_text(
                        result[-1]["desc"], "\n".join(text for text in texts[lead:] if text))
                continue
            first = texts[lead]
            rest = "\n".join(text for text in texts[lead + 1:] if text).strip()
        else:
            first = texts[0]
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


def build_entries(doc_root: str) -> tuple[dict[str, dict], dict[str, int]]:
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
    entries, _ = build_entries(doc_root)
    return {name: entry["where"]["file"] for name, entry in entries.items()}




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



def print_report(entries: dict[str, dict], report: dict) -> None:
    """打印一次构建的报告；``report`` 由调用方给（分类统计属构建产物，不是索引状态）。

    收**记录**、不收算好的统计：口径（前缀/动词分布）是官方解析自己的知识，让调用方去算
    它等于让开发入口认识一个具体来源——`semantic_analysis` 因此留在这里。
    """
    real = {name: entry["where"]["file"] for name, entry in entries.items()}
    analysis = semantic_analysis(entries)
    print("=" * 60)
    print("  SKILL 函数提取报告")
    print("=" * 60)
    print(f"  真实函数:         {len(real):>6}")
    for key, value in sorted(report.items()):
        print(f"  {key:24s} {value}")
    print("\n  ── 前缀 Top 30 ──")
    for prefix, count in list(Counter(analysis["prefixes"]).most_common(30)):
        print(f"    {prefix:15s} {count:4d}")
