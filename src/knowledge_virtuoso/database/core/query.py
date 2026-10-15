#!/usr/bin/env python3
"""属性库共用的**查询**：机制（选择器 + 关键词 → 行）+ 入口（`Query`）。

分两半是为了归属清楚：**装配**（声明 → 能用的库）在 `core/assembly.py`，**查询**在这里
——库包只要 `search, describe = Query(LIB).search, Query(LIB).describe`（实际写法见 `Query`）。

**为什么这一段能收在 core**：四个库的载荷在 ② 之后是同一套形状（对象层七键 + 记录层
`ATTR_KEYS`，见 `objects.py`），所以"怎么筛、怎么排序"对四家是同一件事。查询**只碰
记录的名字**（`store.query_rows` 按 `name` 筛、排序，其余字段原样转手），其余一概不看
——这正是四家能共用一份查询的根据。

各库仍然各留三样，都在它自己的 `index.py` 里：

    aliases     本库的选择器词汇（原文里没写过、但使用者会用的那些写法）
    cross       跨对象口径（见下）
    载荷来源     _load()，本库自己的索引文件

**跨对象口径为什么要声明，而不是在这里推**：不给选择器时，四家的表形状决定了它们该
怎么印——techdb/cdfdb 的表有"所属类"列，同一个名字在不同类里可以是不同的东西，所以
**逐对象分行**；db 的表没有归属列、dd 的同一条记录本来就摊在多个对象下，分行只会印出
一堆看着重复又分不出归属的行，所以**按名收一遍**。这不是谁更对，是各自的原文长得不一样，
所以它是库的一句声明（`_CROSS`）而不是这里的推断。

返回的**行 = 记录 + 查询上下文**：

    * 记录本身（`ATTR_KEYS` 九个键，原样）；
    * `definedIn`——这条来自哪一层/哪个对象（继承链上先声明它的那个；无继承的库就是
      它自己）。单对象查询与逐对象查询由 `merged()` 顺手带上，按名收一遍时由这里补；
    * `classes`——名字 → 声明它的那些对象的列表（`declared_in`，文档顺序）。

`definedIn`/`classes` **不进索引**：它们取决于"这次问了谁"，是查询算出来的，不是原文。
渲染层要印哪几列由各库的 `RenderSpec` 决定，多出来的键它不看。
"""

from __future__ import annotations

from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import store

__all__ = ["search", "describe", "Query", "POOL", "EACH"]

# `_CROSS` 的两种取值。字面量写错会在 `search` 里当场炸，不静默退化成某一种。
POOL = "pool"      # 跨对象：按名收一遍（同名先到先占），一行一个名字
EACH = "each"      # 跨对象：每个对象各出各的行，按 (名字, 所属对象) 排序


def _row_of(declared: dict[str, list[str]]):
    """行工厂：记录原样 + `classes`（谁声明过这个名字）。"""

    def row(name: str, info: dict) -> dict:
        return {**info, "classes": list(declared.get(name, []))}

    return row


def search(objects: dict, selector: str = "", keyword: str = "",
           *, aliases: dict | None = None, cross: str = POOL) -> list[dict]:
    """查一个库：选择器（可空）+ 关键词 → 行。

    * 给了选择器 → **一个对象**（含它的继承链，子覆盖父）：认不出来返回 `[]`
      ——"不认识的选择器"与"认识但筛完没匹配"因此分得开，渲染层靠 `describe()`
      是不是 `None` 给出不同的提示；
    * 没给 → **跨全部对象**，口径由 `cross` 定（`POOL`/`EACH`，见模块说明）。
    """
    declared = objects_mod.declared_in(objects)
    row = _row_of(declared)

    if selector:
        oid = objects_mod.resolve(objects, selector, aliases)
        if oid is None:
            return []                              # 不认识的写法：不猜
        # db 的继承在这里生效；techdb/cdfdb/dd 的 `parent` 全是 None，
        # `merged()` 走一遍就返回自身——退化情形本身就是如实的表示，不必特判。
        pool = objects_mod.merged(objects, oid)
        return store.query_rows(pool, set(pool), keyword, row)

    if cross == POOL:
        # 同名先到先占（文档顺序）。`definedIn` 记着它属于谁——表里没有归属列时，
        # 这一列是唯一能说明归属的地方。
        pooled: dict[str, dict] = {}
        for oid, obj in objects.items():
            for attr in obj["attrs"]:
                pooled.setdefault(attr["name"], {**attr, "definedIn": oid})
        return store.query_rows(pooled, set(pooled), keyword, row)

    if cross == EACH:
        rows: list[dict] = []
        for oid in objects:
            pool = objects_mod.merged(objects, oid)
            rows += store.query_rows(pool, set(pool), keyword, row)
        # 先按名字、再按"被哪些对象声明"排：同一个名字在多个对象下各占一行时，
        # 名字相同而归属不同，只看名字排不出稳定次序。
        rows.sort(key=lambda r: (r["name"], r["classes"]))
        return rows

    raise ValueError(f"不认识的跨对象口径：{cross!r}（应为 {POOL!r} 或 {EACH!r}）")


def describe(objects: dict, selector: str, aliases: dict | None = None) -> dict | None:
    """选择器 → 对象记录；认不出来（或压根没给选择器）返回 `None`。

    渲染的**对象头**靠它回显"这次问的是谁"——问的是别名（`rect`）或运行时名
    （`cellview`）时这一步尤其要紧，否则调用方只看得到"匹配 25 个属性"，不知道说的是
    `Rectangle`。认不出给 `None` 还有一层用处：它与"认出来了但筛完为空"要给出不同的
    提示（`render_attrs` 分得开）。
    """
    if not selector:
        return None
    oid = objects_mod.resolve(objects, selector, aliases)
    return objects.get(oid) if oid else None


class Query:
    """一个库的**查询入口**：把"载荷从哪儿来 + 本库的别名与口径"绑在一起。

    库包（`__init__.py`）里就这么两行：

        _QUERY = Query(LIB)
        search, describe = _QUERY.search, _QUERY.describe

    **入口与装配分家**：装配（声明 → 能用的库）在 `core/assembly.py`，查询（含入口）在这里。
    做成类的方法、而不是每次调用现造的闭包，是为了**四个库共用同一个函数对象**
    （`search.__func__` 全等）——那正是"查询只有一个实现"的直接体现，注册表与测试都钉着它。

    `source` 只要有三样：`store`（`.load()` 给载荷）、`aliases`、`cross`——各库 `index.py`
    里那份 `Library` 正好都有。
    """

    def __init__(self, source) -> None:
        self.source = source

    def search(self, object: str = "", keyword: str = "") -> list[dict]:  # noqa: A002
        """选择器 + 关键词 → 行。别名与跨对象口径取本库声明的那两份（见模块说明）。"""
        # `load()` 给的是**整份载荷**（顶层还有 `version`/`lib`），机制只要里面的对象表。
        return search(self.source.store.load()["objects"], object, keyword,
                      aliases=self.source.aliases, cross=self.source.cross)

    def describe(self, object: str) -> dict | None:
        """选择器 → 对象记录；认不出来给 `None`（渲染的对象头要它）。"""
        return describe(self.source.store.load()["objects"], object, self.source.aliases)
