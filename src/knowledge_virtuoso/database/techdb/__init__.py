#!/usr/bin/env python3
"""技术库对象类及其 `~>` 属性（官方 `sktechfile/appA.html`）。

**库接口**见 `database/core/registry.py`（NAME / LABEL / SELECTOR / DOC / build /
search / render 七项）。这里的选择器叫 `className`——技术库的"对象"是 `techID~>` 的成员。
"""

from __future__ import annotations

from knowledge_virtuoso.database.techdb.core.catalog import build_from_html, search_tech_attr
from knowledge_virtuoso.database.techdb.render import render_techdb_attrs

NAME = "techdb"
LABEL = "技术库对象属性"
SELECTOR = "className"
DOC = """搜索 tech 数据库对象属性。按类 + 关键词查找属性名、类型和所属类。

参数:
  className: tech 对象类名，如 "techID"/"layers"/"lps"/"viaDefs"/"siteDefs"。
             留空搜全部类。
  keyword:   属性名关键词（子串匹配）。留空列出该类全部属性。

示例:
  className="viaDefs" keyword=""            → 列出 viaDefs 全部属性
  className="lps" keyword="valid"           → lps 属性中带 "valid" 的
  className="" keyword="objType"            → 所有类中名为 objType 的属性
"""

build = build_from_html
# 直接别名，不包一层：签名里就是本库自己的选择器名（注册表据此校验 SELECTOR）。
search = search_tech_attr          # (className="", keyword="")
render = render_techdb_attrs       # (rows, className="", keyword="")
