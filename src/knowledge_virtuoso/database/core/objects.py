#!/usr/bin/env python3
"""属性库共用的**对象模型**：校验、选择器解析、继承合并。

db / techdb / cdfdb 的载荷形状是同一套（见 `database/dd/core/README.md` 之外的
`database/<库>/core/README.md`）：

    {"version": N,
     "objects": {<id>: {"id", "title", "section"|null, "desc"|null,
                        "parent": <id>|null, "attrs": [<该库自己的记录>]}}}

**"有没有继承"不用旗子标**：没有继承的库，`parent` 全是 `None`，`merged()` 的循环
走一遍就返回自身——退化情形本身就是如实的表示（"该库全是根节点"）。校验同理：
没有父就没有环可查。

各库真正不同的只有三样，且都在库自己那边：

* **解析器**——原文怎么读成对象与属性（四份文档的记法各不相同）；
* **属性记录的字段**——db 存原文的 `modify` 列、techdb 只有 `name/type/desc`、
  cdfdb 的 `rw` 来自散文且多一个 `source` 标出处；
* **行工厂与渲染**——列布局是各库自己的表示。

跨对象（不给选择器）时的口径也各库不同：db 按名去重，techdb/cdfdb 每个对象各一行
——因为 db 的表**没有"所属对象"列**，分对象分行只会印出一堆看着重复、又分不出归属的行；
另两库的表有"所属类"列，分行才读得出归属。**口径跟着各自的表走。**
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import store

# 对象 id 与属性名的合法形状：**允许大写开头**（`DBUPerUU`、`IOBox` 是原文里的合法名字）。
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_objects(objects: dict) -> None:
    """三家共有的构建期不变量：属性名形状、对象内无重名、父可解析、继承链不成环。

    校验放在**构建**而不是**解析**：解析要能吃半份文档（测试里的 HTML 片段就是一节），
    而一旦要落成索引，这些就得站得住。

    两条**不在这里**，因为它们是库自己的事实：

    * **对象 id 的形状**——db 的 id 是**带空格的表标题**（`Generic Object`、
      `Layer-Purpose Pair`），techdb/cdfdb 的才是标识符（`layers`、`cdfDataId`）；
    * **"每个对象至少一条属性"**——那对 techdb/cdfdb 成立，对 db 不成立
      （Rectangle 之类的"纯转发"对象自身就是 0 条）。
    """
    for oid, obj in objects.items():
        names = [a["name"] for a in obj["attrs"]]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"{oid}: 对象内属性名重复 {dup}")
        bad = [n for n in names if not _NAME_RE.match(n)]
        if bad:
            raise ValueError(f"{oid}: 属性名形状不对 {bad[:5]}")

    for oid, obj in objects.items():
        p = obj.get("parent")
        if p is not None and p not in objects:
            # 文档里每个非 root 的对象都有可解析的父；解析不到只可能是**漏收了那张表**，
            # 所以必须炸掉——静默当空会产出"看起来正常的错答案"。
            raise ValueError(f"{oid}: 父对象 {p!r} 不在索引里（原文有表、本解析没收到？）")

    for oid in objects:
        seen, cur = set(), oid
        while cur:
            if cur in seen:
                raise ValueError(f"{oid}: 继承链成环（{cur} 重复出现）")
            seen.add(cur)
            cur = objects[cur].get("parent")


def resolve(objects: dict, selector: str, aliases: dict | None = None) -> str | None:
    """选择器 → 对象 id。顺序：**精确 id → 原文自报的运行时名 → 忽略大小写与空格 → 兼容别名**。

    别名表由各库自己给（是它自己的选择器词汇，不进索引载荷）。运行时名只有 db 的载荷
    带（原文有 16 张表自报了 `~>objType` 的取值），别的库没有这个字段，
    `runtime_matches` 恒返回 None，等于跳过。
    """
    if not selector:
        return None
    if selector in objects:
        return selector
    hit = runtime_matches(objects, selector)
    if hit:
        return hit
    flat = re.sub(r"[\s_]+", "", selector).lower()
    for oid in objects:
        if re.sub(r"[\s_]+", "", oid).lower() == flat:
            return oid
    return (aliases or {}).get(selector)


def runtime_matches(objects: dict, selector: str) -> str | None:
    """按**原文自报的运行时名**找对象（`obj~>objType` 的取值）。"""
    for oid, obj in objects.items():
        if obj.get("runtime") == selector:
            return oid
    return None


def merged(objects: dict, oid: str) -> dict[str, dict]:
    """`自身属性 ∪ attrs(父)`：子先到先占（**子覆盖父**），并记下每条来自哪一层。

    没有继承的库（`parent` 全为 None）走一遍就返回自身——不需要特判。
    """
    out: dict[str, dict] = {}
    cur, guard = oid, 0
    while cur and guard < 64:
        for attr in objects[cur]["attrs"]:
            if attr["name"] not in out:
                out[attr["name"]] = {**attr, "definedIn": cur}
        cur, guard = objects[cur].get("parent"), guard + 1
    return out


def declared_in(objects: dict) -> dict[str, list[str]]:
    """名字 → 声明它的对象（文档顺序）。供那些表里有"所属对象"列的行用。"""
    out: dict[str, list[str]] = {}
    for oid, obj in objects.items():
        for attr in obj["attrs"]:
            out.setdefault(attr["name"], []).append(oid)
    return out


def query(objects: dict, oid: str, keyword: str, row) -> list[dict]:
    """查**一个对象**的行：合并该对象的属性（无父即自身）→ 关键词过滤 → 组行。"""
    attrs = merged(objects, oid)
    return store.query_rows(attrs, set(attrs), keyword, row)
