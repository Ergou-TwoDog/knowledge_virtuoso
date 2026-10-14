#!/usr/bin/env python3
"""
knowledge_virtuoso.database.db.core.catalog — 解析 attrib.html，按**对象**查询设计库属性。

设计见同目录 README.md。一句话：文档的每张表 = **表头 → `Note: include <父表>` → 自己的属性行**，
所以

    对象 = { id（表标题）, 运行时名, 父, 自身属性[] }
    attrs(x) = 自身属性(x) ∪ attrs(父(x))      # 子覆盖父；父为空即止

**索引只存每个对象自己的行**（含与祖先同名的那些，被覆盖的不删——那是事实），
**继承在查询时算**。索引在哪、怎么读、坏了怎么从官方 doc 重建在 `database/core/store.py`。

解析只依赖原文的**结构**，不认词表：
* 对象 = 文档里 h4 级、标题以 ` Attributes` 结尾的小节
* 属性表 = 该标题后**第一张**表；表头行丢掉，含 `include` 的那行当父指针，其余当属性
* 名字用**原文**（`DBUPerUU` 这种大写开头也要留），`<br>` 折行与"一行两名"按大小写交界分辨

用法:
  search_attr(objType="rect")              → rect 的全部属性（含继承）
  search_attr(objType="rect", keyword="box")
  build_from_html()                        → 从 attrib.html 显式构建索引
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import store

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("db")

# 载荷格式版本。v1 = "每个对象 = 自身属性 + 父指针"；v2 = 并入 `database/core/objects.py`
# 的共用对象模型（形状不变，语义由共用件承担）。更早那套"全局按名去重 + `expanded`"
# 的索引读出来只会是个形状不对的 dict——靠这个号认出来并重建。
_PAYLOAD_VERSION = 2

# 「对象」的识别口径：h4 级、标题以它结尾的小节。
_SUFFIX = " Attributes"
# 父指针那行。原文有三种写法（`include` 64 · `Includes` 4 · `includes` 1），
# 还有一处笔误 `include s Generic Object Attributes`，所以大小写不敏感 + 容忍多余的 `s`。
_INCLUDE_RE = re.compile(r"Note:\s*includes?\s+(?:s\s+)?(.+?)\s+Attributes\b", re.I)
# 运行时名只在对象的 `objType` 行里自报（"Type of the object: \"layer\""）。
_OBJTYPE_HINT_RE = re.compile(r"type of (?:the )?object", re.I)
_QUOTED_RE = re.compile(r'"\s*([^"\s]+)\s*"')
# 属性名的合法形状：**允许大写开头**（`DBUPerUU`、`IOBox` 是原文里的合法属性名）。
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 选择器的**兼容别名**：这些名字原文里从没写过（是用户和历史工具在用的），所以
# **不进索引载荷**，只作用于查找入口。要"纯粹按文档"就把这张表清空——清空后
# `objType="rect"` 之类会失效，得改用表标题（`"Rectangle"`）。
# 只收**指向唯一对象**的别名：`busDef`（对应 Bus Net/Terminal/Vector 三张表）、
# `viaHeader`（Standard/Custom 两张）都不收——那种"猜一个"正是静默错答案。
_ALIASES = {
    "rect": "Rectangle",
    "inst": "Instance",
    "instTerm": "Instance Terminal",
    "stdVia": "Standard Via",
    "customVia": "Custom Via",
    "instHeader": "Instance Header",
    "lp": "Layer-Purpose Pair",
    "layerHeader": "Layer Header",
    "prop": "Property",
}


def _text(buf) -> str:
    """把一段文本节点拼成一个规范化字符串。"""
    return re.sub(r"\s+", " ", "".join(buf).replace("\xa0", " ")).strip()


class _DocParser(HTMLParser):
    """只服务 attrib.html 的两个形状：**标题顺序** 与 **某标题后第一张表的行**。

    老排版 HTML 不能当良构 XML 读，这里只做必要的事：一个打开的标题 / 一行 / 一个单元格，
    遇到同类新标签就自动收口；`<br>` 是空标签（正是靠它把「折行」和「一行两名」分开）。
    嵌套表格用深度计数挡掉——只取最外层那张。
    """

    _HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _VOID = {"br", "hr", "img", "meta", "link", "input", "area", "base", "embed", "param", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[str, str]] = []      # 文档顺序的 (级别, 文本)
        self.by_heading: dict[str, list] = {}          # 表标题 → 该表的最外层行
        self.preamble: dict[str, str] = {}             # 表标题 → 标题与表之间的正文
        self._head = None                              # 正在收集的标题级别
        self._buf: list[str] = []
        self._pending = None                           # 标题收口后，等第一张表的对象标题
        self._pre = None                               # 同一标题与表之间的正文
        self._depth = 0
        self._rows = None
        self._row = None
        self._cell = None

    # ── 标签 ────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._HEADINGS:
            self._head, self._buf = tag, []
        elif tag == "table":
            self._depth += 1
            if self._depth == 1:
                if self._pending is not None:
                    self._rows = []
                    # 少数表把父指针写在**表前的一段正文**里（见 extract_all 里的说明），
                    # 这里趁 `_pre` 还在先收下来，再封口。
                    self.preamble[self._pending] = _text(self._pre or [])
                self._pre = None                   # 前导正文到此为止
        elif tag == "tr" and self._depth == 1 and self._rows is not None:
            self._row = []
        elif tag in ("td", "th"):
            if self._depth == 1 and self._row is not None:
                self._cell = [""]
        elif tag == "br" and self._cell is not None:
            self._cell.append("")              # 段与段的交界

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == self._head:
            self._close_heading()
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth = max(0, self._depth - 1)
            if self._depth == 0 and self._pending is not None:
                title = self._pending
                if title not in self.by_heading:              # 只要第一张
                    self.by_heading[title] = self._rows or []
                self._rows, self._pending = None, None
                self._pre = None

    def handle_data(self, data):
        if self._head is not None:
            self._buf.append(data)
        elif self._cell is not None:
            self._cell[-1] += data
        elif self._pre is not None:
            self._pre.append(data)

    # ── 收口 ────────────────────────────────────────────────
    def _close_heading(self):
        level, text = self._head, _text(self._buf)
        self._head, self._buf = None, []
        if not text:
            return
        self.headings.append((level, text))
        if text.endswith(_SUFFIX):
            self._pending, self._pre = text, []
        else:
            self._pending, self._pre = None, None


def _object_id(title: str) -> str:
    """表标题 → 对象 id（去掉 ` Attributes` 后缀；原文有一处 `Standard viaVariant .` 的尾巴也去掉）。"""
    oid = title[: -len(_SUFFIX)] if title.endswith(_SUFFIX) else title
    return re.sub(r"\s*\.\s*$", "", oid).strip()


def _names_in_cell(segments) -> list[str]:
    """名字格里 `<br>` 的两种含义（见 README §五 规则 8），只能靠大小写交界分辨：

    * `modifiedButNot<br>Saved`  —— 长名字被排版断开 → **一个**名字
    * `startConn<br>endConn`     —— 一行列了两个名字 → **两个**名字（共享同一条描述）

    交界处是「小写→大写」的算折行（长标识符断在驼峰处），其余算两名。
    """
    parts = [_text([s]) for s in segments if _text([s])]
    if len(parts) <= 1:
        return parts
    if all(p[-1].islower() and q[0].isupper() for p, q in zip(parts, parts[1:])):
        return ["".join(parts)]
    return parts


def _row_cells(row) -> list[list[str]]:
    """一行的非空格子；每个格子保留 `<br>` 分出的段落。"""
    return [[_text([seg]) for seg in cell] if cell else [] for cell in row]


def _parent_from(text: str) -> str | None:
    """从一段文本里认父指针（`Note: include[s] X Attributes`），认不出返回 None。

    父指针有**两种位置**：多数表在表里的第二行；`Generic widthSpacingPattern` 等 4 张表
    写在表**前**的正文段落里（`<p><strong>Note: </strong>Includes <a>Generic Object
    Attributes</a>.</p>`）。两处都用同一个正则，只是喂进来的文本不同。
    """
    m = _INCLUDE_RE.search(text or "")
    return _object_id(m.group(1).strip()) if m else None


def extract_all(doc_path: str) -> dict:
    """从 attrib.html 提取**每个对象自己的**属性表与父指针，返回索引载荷。"""
    parser = _DocParser()
    parser.feed(Path(doc_path).read_text(encoding="utf-8", errors="ignore"))
    parser.close()

    # 每个对象记下它所在的 h3 节（文档自己的归类，供上层决定归属，不在这里预判）
    section_of: dict[str, str] = {}
    current = ""
    for level, text in parser.headings:
        if level == "h3":
            current = text
        elif level == "h4" and text.endswith(_SUFFIX):
            section_of.setdefault(text, current)

    objects: dict[str, dict] = {}
    for title, rows in parser.by_heading.items():
        if title not in section_of or not rows:
            continue
        oid = _object_id(title)
        attrs, parent, runtime = [], _parent_from(parser.preamble.get(title, "")), None
        for row in rows[1:]:                       # 第 0 行是表头
            cells = [c for c in _row_cells(row) if any(c)]
            if not cells:
                continue
            head = _text(cells[0])
            if len(cells) == 1 and head.lower().startswith("note:"):
                # 绝大多数表的父指针是表里的第二行（`Note: include X Attributes`）
                parent = _parent_from(head) or parent
                continue
            if len(cells) < 3:
                continue                           # 枚举值的续行等，不是属性
            names = _names_in_cell(cells[0])
            if not names or not all(_NAME_RE.match(n) for n in names):
                continue
            modify = _text(cells[1])
            typ = _text(cells[2])
            desc = _text([" ".join(c) for c in cells[3:]]) if len(cells) > 3 else ""
            for name in names:
                attrs.append({"name": name, "modify": modify, "type": typ, "desc": desc})
            if runtime is None and names[0] == "objType" and _OBJTYPE_HINT_RE.search(desc):
                q = _QUOTED_RE.search(desc)        # 只在对象自报时才取（"in this case \"cellview\""）
                runtime = q.group(1) if q else None
        objects[oid] = {"id": oid, "title": title, "section": section_of[title],
                        "runtime": runtime, "parent": parent, "attrs": attrs}

    return {"objects": objects}


def _validated(payload: dict) -> dict:
    """构建期的载荷包装：交给共用对象模型校验，再打上格式版本。

    校验放在**构建**而不是**解析**：解析要能吃半份文档（测试里的 HTML 片段就是一节），
    而一旦要落成索引，父指针就必须条条有着落。见 `database/core/objects.py`。
    """
    objects_mod.validate_objects(payload["objects"])
    return {"version": _PAYLOAD_VERSION, **payload}


def _row(name: str, info: dict) -> dict:
    """本库的行形状：db 没有 `classes` 列（那是 techdb/cdfdb 的）。

    `rw` 是 `modify` 的**呈现形式**（原文的 Modify 列有 `no`/`yes`/`no/yes`），
    索引里存的是原文，这里才收成两值。
    """
    modify = info.get("modify", "")
    return {"name": name, "rw": "rw" if "yes" in modify.lower() else "ro",
            "type": info.get("type", "?"), "desc": info.get("desc", ""),
            "definedIn": info.get("definedIn", "")}


def search_attr(objType: str = "", keyword: str = "") -> list[dict]:
    """按对象和关键词搜索属性。属性表**在查询时**按继承合并。"""
    objects = _load()["objects"]
    if objType:
        oid = objects_mod.resolve(objects, objType, _ALIASES)
        if oid is None:
            return []                              # 不认识的选择器：区别于"认识但筛完没属性"
        merged = objects_mod.merged(objects, oid)
    else:
        # 不给对象时跨全部对象搜。同名属性在别的对象里可以是别的类型（实测 39 个），
        # 这里按**文档顺序先到先占**，`definedIn` 记着它属于谁。
        merged = {}
        for oid, obj in objects.items():
            for attr in obj["attrs"]:
                merged.setdefault(attr["name"], {**attr, "definedIn": oid})
    return store.query_rows(merged, set(merged), keyword, _row)


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、构建期的校验。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="db_attr",
    lib="db",
    doc_parts=("skdfref", "attrib.html"),
    parse=extract_all,
    payload=_validated,
    version=_PAYLOAD_VERSION,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 attrib.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def main() -> None:
    """CLI：从 attrib.html 提取 dbObject 属性定义，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 attrib.html 提取 dbObject 属性定义")
    parser.add_argument("--doc", default=None,
                        help="attrib.html 路径 (默认取 VIRTUOSO_DOC_DIR/skdfref/attrib.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    output = build_from_html(args.doc)
    objects = output["objects"]
    atomic_write_json(Path(args.output), output)

    roots = [o["id"] for o in objects.values() if o["parent"] is None]
    print(f"\n已导出到 {args.output}")
    print(f"  objects:    {len(objects)} 个对象")
    print(f"  自身属性:   {sum(len(o['attrs']) for o in objects.values())} 条")
    print(f"  根:         {len(roots)} 个 → {', '.join(sorted(roots))}")
    print(f"  自报运行时名: {sum(1 for o in objects.values() if o['runtime'])} 个")


if __name__ == "__main__":
    main()
