#!/usr/bin/env python3
"""
knowledge_virtuoso.database.cdfdb.core.parse — ① **如实层**：chap21.html 的文档结构。

原文（`skartistref/chap21.html` 第 21 章 "CDF Functions"）里，字段是按 **h4 小节**平铺的：
每个字段一个 `<h4>`，正文是一段散文；`cdfDataId` 另有张 `Displaying Parameters` 表。

这一层只回答"原文里有什么"，产出：

    {"fields": {<h4 文本>: {"name", "text": 整段正文, "section": 所属 h3, "rows": 该 h4 的表}}}

**这一层不解释**：不判哪个 h4 是哪个类的字段（那是 ② 的手写白名单）、不从散文推可编辑性、
不给记录打来源标签、也**不掺任何手写数据**（那两条补录是 ② 自己的事，见 `decorate.py`）。
正文也不截断（截断是渲染列的事）。

一个坑写在这里：h4 要**按文本认**而不是按 `<h4><a>名字</a></h4>` 这个形状认——原文里
`parseAsNumber` 的小节写作 `<h4><a name="parseAsNumber"></a><a name="303193">
parseAsNumber</a></h4>`，**首个锚点是空的**。

与另外两库一样，这一层的输出**没有线上对照**，`fixtures/raw/` 里那份 golden 是录下来的
变更探测器。上游是原文 HTML，下游 `decorate.py`。
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path


def _strip(html: str) -> str:
    """去标签、解实体、折空白——纯文本解码，不是"解释"。"""
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _h4_index(text: str) -> dict[str, tuple[int, int, str]]:
    """`h4 文本 → (开始, 结束, 所属 h3 小节)`，同名取第一次。

    按**文本**认而不是按 `<h4><a>名字</a></h4>` 这个形状认：原文里
    `parseAsNumber` 的小节写作 `<h4><a name="parseAsNumber"></a><a name="303193">
    parseAsNumber</a></h4>`——**首个锚点是空的**，按形状匹配会整个漏掉它，
    于是它一度只能靠"手写补录"混进来。
    """
    marks = [(m.start(), m.end(), "h3", _strip(m.group(1))) for m in
             re.finditer(r'<h3[^>]*>(.*?)</h3>', text, re.DOTALL | re.IGNORECASE)]
    marks += [(m.start(), m.end(), "h4", _strip(m.group(1))) for m in
              re.finditer(r'<h4[^>]*>(.*?)</h4>', text, re.DOTALL | re.IGNORECASE)]
    marks.sort()
    out: dict[str, tuple[int, int, str]] = {}
    section = ""
    for start, end, kind, name in marks:
        if kind == "h3":
            section = name                     # 字段正文到下一个 h3/h4 为止，够用
        elif name and name not in out:
            out[name] = (start, end, section)
    return out


def _body_after(text: str, end: int) -> str:
    """从 h4 结束位置取到下一个 h4/h3 或 TOPIC_END 的正文。"""
    nxt = len(text)
    for tag in ('<h4', '<h3', '<!-- [TOPIC_END]'):
        pos = text.find(tag, end)
        if pos != -1:
            nxt = min(nxt, pos)
    return text[end:nxt]


def _table_rows(html: str) -> list[list[str]]:
    """表 → 非空格子的行（格子已去标签、折叠空白）。"""
    rows = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL):
        tds = [_strip(td) for td in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
        tds = [t for t in tds if t]
        if tds:
            rows.append(tds)
    return rows


def parse(doc_path: str) -> dict:
    """① **如实**：把 doc 解析成"文档结构"——每个 h4 小节的正文与表格。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')
    h4s = _h4_index(text)

    fields: dict[str, dict] = {}
    for name, (_start, end, section) in h4s.items():
        body = _body_after(text, end)
        fields[name] = {"name": name, "text": _strip(body),
                        "section": section, "rows": _table_rows(body)}
    return {"fields": fields}
