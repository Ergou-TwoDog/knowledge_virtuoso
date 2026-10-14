#!/usr/bin/env python3
"""CDF 对象属性（官方 `skartistref/chap21.html`）。

**库接口**见 `database/core/registry.py`（NAME / LABEL / SELECTOR / DOC / build /
search / render 七项）。这里的选择器叫 `className`——CDF 的"对象"是两个 SKILL 类
（`g_cdfDataId` / `g_cdfParamId`）。
"""

from __future__ import annotations

from knowledge_virtuoso.database.cdfdb.core.catalog import build_from_html, search_cdf_attr
from knowledge_virtuoso.database.cdfdb.render import render_cdfdb_attrs

NAME = "cdfdb"
LABEL = "CDF 对象属性"
SELECTOR = "className"
DOC = """搜索 CDF 对象属性。按类 + 关键词查找属性名、描述和所属类。

参数:
  className: CDF 对象类名，如 "cdfDataId"/"cdfParamId"。留空搜全部类。
  keyword:   属性名关键词（子串匹配）。留空列出该类全部属性。

示例:
  className="cdfParamId" keyword=""        → 列出 cdfParamId 全部属性
  className="cdfDataId" keyword="param"    → cdfDataId 属性中带 "param" 的
  className="" keyword="value"             → 所有类中名为 value 的属性
"""

build = build_from_html
# 直接别名，不包一层：签名里就是本库自己的选择器名（注册表据此校验 SELECTOR）。
search = search_cdf_attr           # (className="", keyword="")
render = render_cdfdb_attrs        # (rows, className="", keyword="")
