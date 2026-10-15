#!/usr/bin/env python3
"""
knowledge_virtuoso.database.cdfdb.index — CDF 对象属性的**声明**。

本库按三层切：`core/parse.py` ① 如实、`core/decorate.py` ② 归一（按手写白名单归到两个类
下，并把 `type`/`rw` 推出来落盘）。**装配与查询入口在 `core/assembly.py` 与
`core/query.py`**（四库共用）；这里只填本库自己的事实——库名、版本、来源文档、①② 两层、
别名表（本库没有：类名即选择器）、跨对象口径、本库自己的构建期校验。

原文（`skartistref/chap21.html` 第 21 章 "CDF Functions"）里，CDF 的数据模型是**两个
SKILL 对象类**：`g_cdfDataId`（描述对象）与 `g_cdfParamId`（参数对象）。**没有继承、
没有父指针**，两类的属性清单各自平铺。

载荷 = **每个类各存自己那份**：

    {"version": 5, "lib": "cdfdb", "objects": {cid: {id, title, runtime, section, desc, parent, attrs}}}

两个类**零重名**，所以"逐类存储"在这里只统一形状、不改结果（`techdb` 那边就不同了：
它 24 个名字跨类，全局去重会丢东西）。

用法:
  python -m knowledge_virtuoso.database.cdfdb.index       → 命令行版（`LIB.main()`）
  查询走库的公开接口（共用入口按这份声明现绑）：
    from knowledge_virtuoso.database import cdfdb
    cdfdb.search("cdfParamId")                            → 列出该类全部属性
    cdfdb.search("cdfParamId", "param")
    cdfdb.search(keyword="value")                         → 全部类中搜
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.assembly import Library
from knowledge_virtuoso.database.cdfdb.core.decorate import decorate
from knowledge_virtuoso.database.cdfdb.core.parse import parse

# 载荷格式版本沿革：v1 = "每个类各存自己的属性"；v2 = 并入共用对象模型（`classes` →
# `objects`）；v3 = 对象字典固定七键、索引只存原文事实；v4 = 记录层也定键集（`ATTR_KEYS`）、
# ② 算出的 `type`/`rw` 入库；**v5 = 顶层多一个 `lib`（类型区分字段）**。
_VERSION = 5


LIB = Library(
    name="cdfdb",
    version=_VERSION,
    doc_parts=("skartistref", "chap21.html"),
    parse=parse,
    decorate=decorate,
    # 本库**没有别名表**：类名就是选择器，原文的写法与使用者写的写法一致（`resolve` 还兜
    # 大小写与空格）。别的库有别名表，是因为它们的原文里有一批"原文没写过、但使用者在用"
    # 的写法（如 db 的 `rect`）。
    aliases=None,
    # 跨对象口径：不给类时**每个类各出各的行**——与 techdb 同一口径（同名属性在不同类里可以
    # 是不同字段），理由也一样。见 `core/query.py` 的 `EACH`。
    cross=query.EACH,
    # 与 techdb 逐字相同的两条（id 是标识符、每个类都有属性），所以收在共用件里。
    check=objects_mod.validate_identifier_objects,
)


if __name__ == "__main__":
    LIB.main()
