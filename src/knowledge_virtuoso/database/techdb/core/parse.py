#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.core.parse — ① **如实层**：appA.html 的文档结构。

原文（`sktechfile/appA.html` 附录 A）的形状：**每个 `<h3>` 小节 = 一块**，小节里有
`Description` 与 `Attributes` 两个 h4；`Attributes` 表两列（属性名 | 说明），说明折行会
变成独立的续行。**没有继承、没有父指针**。

这一层只回答"原文里有什么"，产出：

    {"sections": [{"heading": h3 的文字, "description": Description 小节正文,
                   "rows": Attributes 表的格子}]}

**这一层不解释格子**：不判哪一格是属性名（那是 `_is_name_token` 的词表规则）、不合并续行、
不推类型、不认 `techID~>` 这个类名前缀——全在 `decorate.py`。**所有小节都收**（是不是类由
② 决定），文字也不截断（要不要截是 ② 的事）。

与 db 那边一样，这一层的输出**没有线上对照**，`tests/.../techdb/core/fixtures/raw/` 里
那几份 golden 是录下来的变更探测器。上游是原文 HTML，下游 `decorate.py`。
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


def _h4_body(section: str, name: str) -> str:
    """某个 `<h4><a>name</a></h4>` 小节的正文（到下一个 h4/h3 为止）。"""
    m = re.search(r'<h4[^>]*>\s*<a[^>]*>' + name + r'</a>\s*</h4>(.*?)(?=<h4|</body>|<h3)',
                  section, re.DOTALL)
    return m.group(1) if m else ""


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
    """① **如实**：把 doc 解析成"文档结构"——每个 h3 小节的标题、Description 正文、Attributes 表的格子。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')
    h3s = list(re.finditer(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', text, re.DOTALL))

    sections = []
    for i, m in enumerate(h3s):
        end = h3s[i + 1].start() if i + 1 < len(h3s) else len(text)
        body = text[m.end():end]
        sections.append({"heading": _strip(m.group(1)),
                         "description": _strip(_h4_body(body, "Description")),
                         "rows": _table_rows(_h4_body(body, "Attributes"))})
    return {"sections": sections}
