#!/usr/bin/env python3
"""设计库对象属性（官方 `skdfref/attrib.html`）。

**库接口**——`database/core/registry.py` 只认这几样，加一个属性库不必改上层：

  NAME                             库名：索引目录名、工具名前缀（工具名 = `<NAME>_search_attr`）
  LABEL                            一句话说明（发现结果里打出来）
  SELECTOR                         工具第一个参数名（**各库不同**，这里是 objType）
  DOC                              工具 docstring 全文
  build(doc_path=None)             从官方 doc 重建索引载荷
  search(selector, keyword)        查询 → 行
  render(rows, selector, keyword)  行 → 文本

解析器与渲染器各自独立（`core/catalog.py` 按对象+父指针建索引、查询时合并；
`render.py` 只做行 → 文本）。这里只做接线。
"""

from __future__ import annotations

from knowledge_virtuoso.database.db.core.catalog import build_from_html, search_attr
from knowledge_virtuoso.database.db.render import render_db_attrs

NAME = "db"
LABEL = "设计库对象属性"
SELECTOR = "objType"
DOC = """搜索数据库对象属性。按对象 + 关键词查找属性名、类型和读写权限。

参数:
  objType: 对象选择器，三种写法都认（大小写、空格不敏感）：
           ①**表标题**——IC618 文档里那张属性表的标题，如 "Cellview"/"Marker"/
             "Track Pattern"（覆盖全部 76 个对象，**推荐**）；
           ②**运行时名**——文档自报过的 `~>objType` 值，如 "cellview"/"PRBoundary"；
           ③**少量兼容别名**，如 "rect"（＝Rectangle）、"inst"（＝Instance）。
           留空搜全部对象。
  keyword: 属性名关键词（子串匹配）。留空列出该对象的全部属性。

返回的是**该对象可用属性的并集**——文档里每个对象只列自己的属性，再靠
`Note: include <父对象>` 层层继承（最深 3 层，到 Generic Object 为止）。

示例:
  objType="Rectangle" keyword=""   → 矩形的全部属性（含继承自 Generic 层的）
  objType="rect" keyword="bBox"    → 同上，按关键词筛
  objType="" keyword="bBox"        → 所有对象中名字含 bBox 的属性
"""

build = build_from_html
# 直接别名，不包一层：`search` 的签名里就是本库自己的选择器名（注册表据此校验
# `SELECTOR` 与它对得上），`render` 的第二个参数同理。
search = search_attr          # (objType="", keyword="")
render = render_db_attrs      # (rows, objType="", keyword="")
