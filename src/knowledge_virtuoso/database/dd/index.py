#!/usr/bin/env python3
"""
knowledge_virtuoso.database.dd.index — 数据管理对象的属性与关系：**声明**。

本库按三层切：`core/parse.py` ① 如实、`core/decorate.py` ② 归一（按表头签名挑表、读出
记录，再摊到每个适用对象下）。**装配与查询入口在 `core/assembly.py` 与 `core/query.py`**
（四库共用）；这里只填本库自己的事实——库名、版本、来源文档、①② 两层、别名表（本库没有：
对象名就是选择器）、跨对象口径、本库自己的构建期校验。

原文（`skdfref/chap3.html` 第 19 章 *Design Management Functions* 的
"Attributes of Data Management Objects" 一节）的记法与另外三个库**都不同**：它是
**转置**的——一张表一行一个属性，后面每个适用对象各占一格：

    Attribute Names | Object Types Attribute is Valid For
    group           | libFile | cellFile | viewFile
    name            | lib | cell | view | libFile | cellFile | viewFile

再加一张关系表：`关系名 | 基数 | 适用对象…`（`cells | 1:n | lib`）。

**但载荷走的是和另三库一样的容器**（② 把它摊平了）：

    {"version": 5, "lib": "dd", "objects": {"lib": {id, title, runtime, section, desc, parent, attrs}, …}}

代价是副本（22 条 → 6 个对象共 74 条，3.36×），换来的是**上层一视同仁**：联合查询、
渲染的对象头、三层键集的校验都不必为本库开特例。原文那个转置的记法由 `core/decorate.py`
与 `core/README.md` 如实记着。

**本库拿不到类型也拿不到说明**：原文的属性表只有"名字 | 适用对象"两列；类型图例虽然
在 HTML 里（一张 9 行表：b/d/f/g/l/n/s/t/x），但正文指向的那张图**在这套 doc 里不存在**
（dd 节 `<img>` 为 0、印刷版承载这两张表的正文 1728/1729 页里绘图指令也为 0）。所以记录里
没有 `type`、也没有 `desc`——是**原文没有**，不是"有图没解析"。

用法:
  python -m knowledge_virtuoso.database.dd.index        → 命令行版（`LIB.main()`）
  查询走库的公开接口（共用入口按这份声明现绑）：
    from knowledge_virtuoso.database import dd
    dd.search("cellFile")                               → cellFile 的全部属性与关系
    dd.search("lib", "cells")
    dd.search(keyword="group")                          → 所有对象中名字含 group 的
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import query
from knowledge_virtuoso.database.core.assembly import Library
from knowledge_virtuoso.database.dd.core.decorate import decorate
from knowledge_virtuoso.database.dd.core.parse import parse

# 载荷格式版本沿革：v1 = 建库；v2 = `objects` → `objectTypes` 改名（那时本库站在统一容器
# 之外）；v3 = 摊进七键容器（`objectTypes` 退回记录里的一个字段）；v4 = 记录层也定键集
# （`ATTR_KEYS`，缺的补 `null`）；**v5 = 顶层多一个 `lib`（类型区分字段）**。
_VERSION = 5

_CARD_RE = re.compile(r"^\d+:(?:\d+|n)$")     # 原文只有 `1:1` 与 `1:n` 两种


def _check(objects: dict) -> None:
    """本库自己的构建期校验（顶层的键集/`lib`、两层键集由 `Library.validate` 那套管）。

    **"适用对象在不在全集里"不在这儿**——那要在摊平之前才看得全，已由 `decorate()` 快速
    失败（摊平之后只看得到挂上去的那些，一条"只挂在全集之外"的记录会连影子都没有）。
    """
    if not objects:
        raise ValueError("一个对象都没有（表头签名变了？）")
    kinds: dict[str, str] = {}
    for oid, obj in objects.items():
        if not obj["attrs"]:
            raise ValueError(f"{oid}: 一条记录都没有（属性表或关系表没读到？）")
        for rec in obj["attrs"]:
            if rec["kind"] == "relation" and not _CARD_RE.match(rec.get("cardinality") or ""):
                raise ValueError(f"{oid}/{rec['name']}: 关系基数不像 `1:n`："
                                 f"{rec.get('cardinality')!r}")
            # 同一个名字在所有对象下必须是同一种东西（摊平后"属性名与关系名撞车"
            # 未必落在同一个对象里，所以在这儿按名收一遍）
            if kinds.setdefault(rec["name"], rec["kind"]) != rec["kind"]:
                raise ValueError(f"{rec['name']!r} 既是属性又是关系")


def _summary(objects: dict) -> list[str]:
    """`LIB.main()` 里多打一行——本库特有的：六个对象的名字。"""
    return [f"对象:        {', '.join(objects)}"]


LIB = Library(
    name="dd",
    version=_VERSION,
    doc_parts=("skdfref", "chap3.html"),
    parse=parse,
    decorate=decorate,
    # 本库**没有别名表**：对象名就是选择器（`lib`/`cell`/…），`resolve` 还兜大小写。
    aliases=None,
    # 跨对象口径：不给对象时**按名收一遍**（先到先占）。同一条记录本来就摊在多个对象下
    # （3.36× 的副本），逐对象分行只会印出 N 行一模一样的；而「适用对象」那列本来就把归属
    # 说全了。口径与 db 一致，理由不同——见 `core/query.py` 的 `POOL`。
    cross=query.POOL,
    check=_check,
    summary=_summary,
)


if __name__ == "__main__":
    LIB.main()
