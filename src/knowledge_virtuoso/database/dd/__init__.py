#!/usr/bin/env python3
"""数据管理对象属性与关系（官方 `skdfref/chap3.html`）。

**库接口**见 `database/core/registry.py`（NAME / LABEL / SELECTOR / DOC / build /
search / render 七项）。这里的选择器叫 `object`——本库的"对象"是数据管理对象
（lib / cell / view / libFile / cellFile / viewFile），原文的记法是**转置**的：
一行一个属性/关系，后面每个适用对象各占一格。
"""

from __future__ import annotations

from knowledge_virtuoso.database.dd.core.catalog import build_from_html, search_dd_attr
from knowledge_virtuoso.database.dd.render import render_dd_attrs

NAME = "dd"
LABEL = "数据管理对象属性"
SELECTOR = "object"
DOC = """搜索数据管理对象的属性与关系。按对象 + 关键词查找。

参数:
  object:  数据管理对象，取 "lib"/"cell"/"view"/"libFile"/"cellFile"/"viewFile"
           之一（大小写不敏感）。留空搜全部对象。
  keyword: 名字关键词（子串匹配）。留空列出该对象的全部属性与关系。

返回两类条目，用 kind 列区分：`attr`（属性）与 `relation`（关系，带基数 `1:1`/`1:n`）。
注意**原文没给类型也没给说明**——属性表只有"名字 | 适用对象"，逐条类型只出现在没进
HTML 的图里，所以这里没有 type/desc 列，不是解析漏了。

示例:
  object="cellFile" keyword=""     → cellFile 的全部属性与关系
  object="lib" keyword="cells"     → lib 上的 cells 关系
  object="" keyword="group"        → 所有对象中名字含 group 的
"""

build = build_from_html
# 直接别名，不包一层：签名里就是本库自己的选择器名（注册表据此校验 SELECTOR）。
search = search_dd_attr            # (object="", keyword="")
render = render_dd_attrs           # (rows, object="", keyword="")
