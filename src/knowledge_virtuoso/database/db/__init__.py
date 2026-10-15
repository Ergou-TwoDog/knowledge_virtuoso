#!/usr/bin/env python3
"""设计库对象属性（官方 `skdfref/attrib.html`）。

**库接口**——`database/core/registry.py` 只认 `REQUIRED_ATTRS` 那几样，加一个属性库不必
改上层：

  NAME                             库名：索引目录名、`search_attr` 的 `lib` 取值、载荷里的 `lib`
  LABEL                            一句话说明（发现结果里打出来）
  DOC                              本库那段工具描述（工具描述 = 总说明 + 各库 DOC 拼成）
  parse(doc)                       ① 如实还原原文结构（不解释格子）
  decorate(raw)                    ② 归一成统一载荷（顶层 + 对象层 + 记录层三套键集）
  build(doc_path=None)             从官方 doc 重建索引载荷
  search(object, keyword)          查询 → 行（**四库共用的那一个**，来自 `core/query.py`）
  describe(object)                 选择器 → 对象记录（渲染的对象头要它；认不出给 None）
  render(rows, object, keyword, obj)   行 → 文本

选择器四库共用一个名字 `object`——**各库不再有自己的选择器词汇**；本库额外认哪些写法见
`DOC` 与 `index.py` 的 `LIB.aliases`。原文怎么读在 `core/`（`parse.py` ① + `decorate.py` ②），
本库自己的声明（库名、版本、来源文档、别名、跨对象口径）在 `index.py` 的 `LIB`。

渲染**只声明一份 `RenderSpec`**（列与提示语），表格本体在 `database/core/render.py`。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.render import Column, RenderSpec, render_attrs
# ①② 两层**在这里只是暴露给注册表**（`REQUIRED_ATTRS` 里的契约项，证明这棵树切了三层）；
# 本模块自己不用它们——用它们的是 `index.py` 的声明与 `core/assembly.py`。
from knowledge_virtuoso.database.db.core.decorate import decorate  # noqa: F401
from knowledge_virtuoso.database.db.core.parse import parse  # noqa: F401
from knowledge_virtuoso.database.db.index import LIB

NAME = LIB.name
LABEL = "设计库对象属性"
DOC = """搜索数据库对象属性。按对象 + 关键词查找属性名、类型和读写权限。

参数:
  object:  对象选择器，三种写法都认（大小写、空格不敏感）：
           ①**表标题**——IC618 文档里那张属性表的标题，如 "Cellview"/"Marker"/
             "Track Pattern"（覆盖全部 76 个对象，**推荐**）；
           ②**运行时名**——文档自报过的 `~>objType` 值，如 "cellview"/"PRBoundary"；
           ③**少量兼容别名**，如 "rect"（＝Rectangle）、"inst"（＝Instance）。
           留空搜全部对象。
  keyword: 属性名关键词（子串匹配）。留空列出该对象的全部属性。

返回的是**该对象可用属性的并集**——文档里每个对象只列自己的属性，再靠
`Note: include <父对象>` 层层继承（最深 3 层，到 Generic Object 为止）。

示例:
  object="Rectangle" keyword=""   → 矩形的全部属性（含继承自 Generic 层的）
  object="rect" keyword="bBox"    → 同上，按关键词筛
  object="" keyword="bBox"        → 所有对象中名字含 bBox 的属性
"""

build = LIB.build
# 查询入口与对象头归**查询那一层**（`core/query.py` 的 `Query`）：四库共用同一个函数对象、
# 同一个签名（`search(object, keyword)`）。换一个库若自己写了一个，`registry` 会发现并跳过。
_QUERY = query.Query(LIB)
search = _QUERY.search
describe = _QUERY.describe

# 渲染声明：列宽与描述截断（60）属于本库的表示，改它不影响别的库。
# 对象头印三项——`title` 是原文的表标题、`runtime` 只在该对象自报时才有、`section` 是它
# 在原文哪一节；原文没给的那几项渲染时自动略去。
# `selector_label` 就是工具里那个参数名（`object`）——提示语里写别的名字会让人照着填错。
_SPEC = RenderSpec(
    columns=(Column("name", "name", 25),
             Column("rw", "rw", 4),
             Column("type", "type", 15),
             Column("desc", "desc", 0, truncate=60)),
    subject="属性", selector_label="object", all_label="全部类型",
    header_fields=(("title", "title"), ("runtime", "runtime"), ("section", "section")),
)


def render(rows: list[dict], object: str = "", keyword: str = "",  # noqa: A002
           obj: dict | None = None) -> str:
    """把属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。

    `obj` 由调用方给（`describe`）：问的是别名或运行时名时，靠它回显解析到的对象。
    """
    return render_attrs(rows, _SPEC, selector=object, keyword=keyword, obj=obj)
