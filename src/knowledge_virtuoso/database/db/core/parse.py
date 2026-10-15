#!/usr/bin/env python3
"""
knowledge_virtuoso.database.db.core.parse — ① **如实层**：attrib.html 的文档结构。

这一层只回答"原文里有什么"：**哪些标题、某标题后是哪张表、表里有哪些格子**。
`<br>` 分出的段落原样留着（那是原文的排版事实，`decorate.py` 要靠它分「折行」与
「一行两名」）。

格子里是**原文的文本节点**，包括排版用的换行与缩进（真实片段里一格长这样：
`"\n            objType\n          "`）——**折空白是 ② 的事**（`_row_cells`/`_text`）。
`fixtures/raw/` 的 golden 钉着这一点：让 ① 顺手折掉空白，它会红。

**这一层不解释格子**：不认哪一格是属性名、不认 `Note: include` 是父指针、不把
"Type of the object: …" 读成运行时名——那些都在 `decorate.py`。产出：

    {"sections": [{"title": 表标题, "section": 所属 h3, "preamble": 表前正文,
                   "table": [[格子段, …], …]}]}

* `section` 是这张表在**原文自己的归类**里的位置（h3 小节名）；
* `preamble` 是标题与表之间的正文——少数表把父指针写在那儿（见 `decorate.py`）。

**这一层的输出没有线上对照**（索引里只有 ② 归一后的形状），所以它是三库里唯一
"golden 只能当变更探测器"的一层：`tests/.../db/core/fixtures/raw/` 那几份 `.json`
是录下来的，改这里就得连它们一起走。

上游是原文 HTML，下游是 `decorate.py`；装配在 `../index.py`（查询机制四库共用，在
`database/core/query.py`）。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

# 「对象」的识别口径：h4 级、标题以它结尾的小节。**① ② 都得用**——这里用它决定
# "哪张表归本库管"（`_DocParser` 只收这些标题后面的第一张表），`decorate.py` 用它
# 决定"哪一节是一个对象"。
_SUFFIX = " Attributes"


def _text(buf) -> str:
    """把一段文本节点拼成一个规范化字符串（折空白、`&nbsp;` 也算空白）。"""
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
                    # 少数表把父指针写在**表前的一段正文**里（见 `decorate.py`），
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


def parse(doc_path: str) -> dict:
    """① **如实**：把 doc 解析成"文档结构"——有哪些标题、某标题后是哪张表、表里有哪些格子。

    格子保留 `<br>` 分段的原样（分不分段是**原文的排版事实**，`_names_in_cell` 要靠它
    分辨"折行"与"一行两名"）。
    """
    parser = _DocParser()
    parser.feed(Path(doc_path).read_text(encoding="utf-8", errors="ignore"))
    parser.close()

    # 每个标题记下它所在的 h3 节（文档自己的归类，供上层决定归属，不在这里预判）
    section_of: dict[str, str] = {}
    current = ""
    for level, text in parser.headings:
        if level == "h3":
            current = text
        elif level == "h4":
            section_of.setdefault(text, current)

    return {"sections": [{"title": title, "section": section_of.get(title, ""),
                          "preamble": parser.preamble.get(title, ""), "table": rows}
                         for title, rows in parser.by_heading.items()]}
