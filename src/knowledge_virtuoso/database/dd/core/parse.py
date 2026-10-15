#!/usr/bin/env python3
"""
knowledge_virtuoso.database.dd.core.parse — ① **如实层**：chap3.html 的文档结构。

原文（`skdfref/chap3.html` 第 19 章 *Design Management Functions* 的
"Attributes of Data Management Objects" 一节）里，这一节有四张表：一张运算符图例、
一张类型图例、一张属性表、一张关系表。**只有小节里有哪些表、每张表有哪些格子**是
这一层的事。

产出：

    {"tables": [[[格子, …], …], …]}        # 文档顺序，每张表是一个格子网格

**这一层不解释**：不判哪张是属性表哪张是关系表（② 靠**表头签名**挑）、不从格子算
对象全集、不管基数的形状。上游是原文 HTML，下游 `decorate.py`。

**这一层没有线上对照**（索引里只有 ② 归一后的形状），`fixtures/raw/` 里那份 golden 是
录下来的变更探测器。
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

_SECTION = "Attributes of Data Management Objects"


def _strip(html: str) -> str:
    """去标签、解实体、折空白——纯文本解码，不是"解释"。"""
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _rows(table_html: str) -> list[list[str]]:
    """表格 → 非空格子组成的行（格子本身是字符串）。"""
    out = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL):
        cells = [_strip(td) for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def _section_html(text: str) -> str:
    """取该 h2 小节（到下一个 h2 为止）。这一节里没有 h3/h4。"""
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', text, re.DOTALL | re.IGNORECASE):
        if _strip(m.group(1)) == _SECTION:
            nxt = re.search(r'<h2', text[m.end():], re.IGNORECASE)
            return text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    raise ValueError(f"找不到小节 {_SECTION!r}")


def parse(doc_path: str) -> dict:
    """① **如实**：把该小节解析成"有哪些表、每张表有哪些格子"。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')
    return {"tables": [_rows(t) for t in
                       re.findall(r'<table.*?</table>', _section_html(text), re.DOTALL)]}
