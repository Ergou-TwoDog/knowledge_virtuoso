#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.index — 技术库属性的**声明**。

本库按三层切：`core/parse.py` ① 如实、`core/decorate.py` ② 归一（只留 `techID~>` 类，并把
`type` 从该类自己的说明里推出来落盘）。**装配与查询入口在 `core/assembly.py` 与
`core/query.py`**（四库共用）；这里只填本库自己的事实——库名、版本、来源文档、①② 两层、
别名表、跨对象口径、本库自己的构建期校验。

载荷 = **每个类各存自己那份**（对象层七键 + 记录层 `ATTR_KEYS`）：

    {"version": 5, "lib": "techdb", "objects": {cid: {id, title, runtime, section, desc, parent, attrs}}}

**为什么不能"全局按属性名去重"**（本库 0.3.0 之前就是这么存的）：实测有 **24 个属性名
挂在多个类下**，而同一个名字在不同类里说明与类型可以不同（`name` 在 9 个类里各有一句
自己的说明）。按名去重只会静默留下第一个类的——`snapPatternDefs~>layer` 因此被显示成
`l_objId`，而该类原文 "A list of layers on which…" 推出来是 `l_string`。

用法:
  python -m knowledge_virtuoso.database.techdb.index   → 命令行版（`LIB.main()`）
  查询走库的公开接口（共用入口按这份声明现绑）：
    from knowledge_virtuoso.database import techdb
    techdb.search("viaDefs")                           → 列出 viaDefs 全部属性
    techdb.search("lps", "valid")
    techdb.search(keyword="objType")                   → 全部类中搜
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.assembly import Library
from knowledge_virtuoso.database.techdb.core.decorate import decorate
from knowledge_virtuoso.database.techdb.core.parse import parse

# 载荷格式版本沿革：v1 = "每个类各存自己的属性"（此前是全局按名去重）；v2 = 并入共用对象
# 模型（`classes` → `objects`）；v3 = 对象字典固定七键、索引只存原文事实；v4 = 记录层也定
# 键集（`ATTR_KEYS`）、② 算出的 `type` 入库；**v5 = 顶层多一个 `lib`（类型区分字段）**。
_VERSION = 5

# 选择器的**兼容别名**：这些取值（如 `stdViaDef`）在原文里只出现在正文与输出例子里
# （`tfid~>viaDefs~>objType => ("stdViaDef" …)`），抽不成表，所以**不进索引载荷**——索引
# 只放解析器读出来的事实——只作用于查找入口。要"纯粹按文档"就清空这张表。
_ALIASES = {
    "stdViaDef": "viaDefs",
    "customViaDef": "viaDefs",
    "stdViaVariant": "viaVariants",
    "customViaVariant": "viaVariants",
    # 原文两处写法不一致：siteDefs 表里写的是复数的 scalarSiteDefs / arraySiteDefs，
    # 而 elsewhere 用单数。两种都收。
    "scalarSiteDef": "siteDefs",
    "arraySiteDef": "siteDefs",
    "scalarSiteDefs": "siteDefs",
    "arraySiteDefs": "siteDefs",
}


LIB = Library(
    name="techdb",
    version=_VERSION,
    doc_parts=("sktechfile", "appA.html"),
    parse=parse,
    decorate=decorate,
    aliases=_ALIASES,
    # 跨对象口径：不给类时**每个类各出各的行**——名字相同而归属不同（24 个名字跨类，且说明
    # 与类型可以不同），合并成一行只会静默挑一个。见 `core/query.py` 的 `EACH`。
    cross=query.EACH,
    # 本库自己的构建期校验：对象 id 是标识符（不是 db 那种带空格的表标题）、每个类都有属性
    # ——这两条 cdfdb 逐字相同，所以收在 `core/objects.py`（dd 有自己的一套，在它那儿）。
    check=objects_mod.validate_identifier_objects,
)


if __name__ == "__main__":
    LIB.main()
