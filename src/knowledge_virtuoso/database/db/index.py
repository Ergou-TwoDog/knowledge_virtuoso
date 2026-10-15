#!/usr/bin/env python3
"""
knowledge_virtuoso.database.db.index — 设计库属性的**声明**（库根，不在 core/ 下）。

本库按三层切：`core/parse.py` ① 如实、`core/decorate.py` ② 归一（认父指针、把原文的
Modify 列收成两值的 `rw`）。**装配与查询入口不在这里**——它们在 `core/assembly.py` 的
`Library` 与 `core/query.py` 里（四库共用）。这里只填本库自己的事实：

    name / version    库名（= 索引目录名 = 载荷里的 `lib`）与载荷格式版本
    doc_parts         默认来源文档（`VIRTUOSO_DOC_DIR` 下）
    parse / decorate  ①② 两层
    aliases           本库的选择器词汇（原文没写过、但使用者在用的那些写法）
    cross             跨对象口径（不给选择器时怎么收）

一句话设计：文档的每张表 = **表头 → `Note: include <父表>` → 自己的属性行**，所以

    对象 = { id（表标题）, 运行时名, 父, 自身属性[] }
    attrs(x) = 自身属性(x) ∪ attrs(父(x))      # 子覆盖父；父为空即止

**继承在查询时算**（`core/query.py` 的 `merged`）；记录里除原文那几格外还落着 ② 算好的
`rw`，所以**改了推法（或改了 `ATTR_KEYS`）就要抬版本号重建**。索引在哪、怎么读、坏了怎么
从官方 doc 重建在 `core/store.py`。

用法:
  LIB.build()                                    → 从 attrib.html 显式构建索引
  python -m knowledge_virtuoso.database.db.index → 命令行版（`LIB.main()`）
  查询不在这份声明上、也不在库里——走库的公开接口（共用入口按它现绑）：
    from knowledge_virtuoso.database import db
    db.search("rect")                            → rect 的全部属性（含继承）
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.assembly import Library
from knowledge_virtuoso.database.db.core.decorate import decorate
from knowledge_virtuoso.database.db.core.parse import parse

# 载荷格式版本沿革：v1 = "每个对象 = 自身属性 + 父指针"；v2 = 并入共用对象模型；v3 = 对象字典
# 固定七键、索引只存原文事实；v4 = 记录层也定键集（`ATTR_KEYS`）、② 算出的 `rw` 入库；
# **v5 = 顶层多一个 `lib`（类型区分字段）**。更早的索引缺键、也没有 `lib`，读出来只会是个
# 形状不对的 dict——靠这个号与那个字段认出来并重建。
_VERSION = 5

# 选择器的**兼容别名**：这些名字原文里从没写过（是用户和历史工具在用的），所以
# **不进索引载荷**，只作用于查找入口。要"纯粹按文档"就把这张表清空——清空后
# `object="rect"` 之类会失效，得改用表标题（`"Rectangle"`）。
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


def _summary(objects: dict) -> list[str]:
    """`LIB.main()` 里多打的两行——本库特有的：继承的根、原文自报过运行时名的对象数。"""
    roots = [o["id"] for o in objects.values() if o["parent"] is None]
    return [f"根:           {len(roots)} 个 → {', '.join(sorted(roots))}",
            f"自报运行时名: {sum(1 for o in objects.values() if o['runtime'])} 个"]


LIB = Library(
    name="db",
    version=_VERSION,
    doc_parts=("skdfref", "attrib.html"),
    parse=parse,
    decorate=decorate,
    aliases=_ALIASES,
    # 跨对象口径：db 的属性表**没有"所属对象"列**，逐对象分行只会印出一堆看着重复、
    # 又分不出归属的行，所以**按名收一遍**（先到先占）。另一种口径 `query.EACH`（每个
    # 对象各出各的行）是 techdb/cdfdb 用的，见 `core/query.py`。
    cross=query.POOL,
    summary=_summary,
)


if __name__ == "__main__":
    LIB.main()
