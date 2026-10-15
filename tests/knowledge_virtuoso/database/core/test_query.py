#!/usr/bin/env python3
"""**查询机制**：`database/core/query.py`（四库共用）。

**与 src 一一对应**——本文件在 `database/core/` 下，对着同级的 `query.py`。

这一层是四库共用的那段：**选择器 → 记录池 → 行**。所以它要钉住的是"四家都靠它"的那几条
不变量，而不是任何一家怎么读原文：

- **给了选择器**：只查那一个对象（含它的继承链，子覆盖父）；认不出来给 `[]`
  ——"不认识"与"认识但筛完为空"分得开（渲染层据此给不同提示）；
- **不给选择器**：两种口径各钉一遍（`POOL` 按名收一遍 / `EACH` 每对象各一行），
  包括排序与"同名在不同对象下可以是不同的东西"；
- **行 = 记录 + 两个上下文字段**：记录原样（`ATTR_KEYS`）、`definedIn`（来自哪一层）、
  `classes`（这个名字被哪些对象声明过）——后两个**不进索引**，是查询算的；
- **口径写错要当场炸**，不许静默退化成某一种。

载荷是手写的（`objects.record` 建，不引厂商原文）：不读索引、不需要 doc、不碰磁盘。
"""

from __future__ import annotations

import inspect
import pathlib
import sys
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.database.core import query  # noqa: E402
from knowledge_virtuoso.database.core.objects import ATTR_KEYS, record  # noqa: E402


def _obj(oid: str, attrs: list[dict], parent: str | None = None) -> dict:
    return {"id": oid, "title": oid, "runtime": None, "section": None,
            "desc": None, "parent": parent, "attrs": attrs}


def _flat() -> dict:
    """三个平铺对象（无继承）：`shared` 在三个对象下**各有一条自己的记录**（说明不同）
    ——techdb/cdfdb 需要「每个对象各出各的行」正是为此，db/dd 则要按名收一遍。"""
    return {
        "Base": _obj("Base", [record("shared", kind="attr", desc="base 的 shared"),
                              record("baseOnly", kind="attr", desc="只在 Base")]),
        "Child": _obj("Child", [record("shared", kind="attr", desc="child 的 shared"),
                                record("childOnly", kind="attr", desc="只在 Child")]),
        "Solo": _obj("Solo", [record("shared", kind="attr", desc="solo 的 shared")]),
    }


def _inherit() -> dict:
    """一条继承链（只有 db 那种库会有）：`Child` 继承 `Base`，两边都有 `shared`。"""
    return {
        "Base": _obj("Base", [record("shared", kind="attr", desc="base 的 shared"),
                              record("baseOnly", kind="attr", desc="只在 Base")]),
        "Child": _obj("Child", [record("shared", kind="attr", desc="child 的 shared"),
                                record("childOnly", kind="attr", desc="只在 Child")],
                      parent="Base"),
    }


def run(report: Report, update: bool = False) -> None:
    objs = _flat()

    # ── 行 = 记录（ATTR_KEYS）+ definedIn + classes ──
    rows = query.search(objs, "Child")
    report.expect("行/记录原样交出（`ATTR_KEYS` 那九个键都在），只多两个上下文字段",
                  sorted(rows[0]), sorted([*ATTR_KEYS, "definedIn", "classes"]))
    report.expect("行/按名字排序（query_rows 管），每条带着它来自哪个对象",
                  [(r["name"], r["definedIn"]) for r in rows],
                  [("childOnly", "Child"), ("shared", "Child")])
    report.expect("行/classes 是**这个名字被哪些对象声明过**（文档顺序），不是某一条的归属",
                  next(r for r in rows if r["name"] == "shared")["classes"],
                  ["Base", "Child", "Solo"])

    # ── 给了选择器：一个对象；认不出来给 [] ──
    # 别名是各库自己的词汇，由调用方给进来（`aliases=`）
    report.expect("选择器/别名表由调用方给（四库的选择器词汇各是各的）",
                  [r["name"] for r in query.search(objs, "kid", aliases={"kid": "Child"})],
                  [r["name"] for r in rows])
    report.expect("选择器/认不出来给空表——与「认识但筛完为空」分开（渲染靠 describe 分辨）",
                  (query.search(objs, "没有这个"), query.search(objs, "Solo", "没有这个关键词")),
                  ([], []))

    # ── 不给选择器：POOL 按名收一遍（先到先占）──
    pooled = query.search(objs, "", "", cross=query.POOL)
    report.expect("口径 POOL/一个名字一行，先到先占（shared 归文档里第一个声明的 Base）",
                  [(r["name"], r["definedIn"]) for r in pooled],
                  [("baseOnly", "Base"), ("childOnly", "Child"), ("shared", "Base")])
    report.expect("口径 POOL/关键词照筛",
                  [r["name"] for r in query.search(objs, "", "only", cross=query.POOL)],
                  ["baseOnly", "childOnly"])

    # ── 不给选择器：EACH 每个对象各出各的行 ──
    each = query.search(objs, "", "", cross=query.EACH)
    report.expect("口径 EACH/同名在不同对象下各占一行（这就是 techdb/cdfdb 要的）",
                  [(r["name"], r["definedIn"]) for r in each],
                  [("baseOnly", "Base"), ("childOnly", "Child"),
                   ("shared", "Base"), ("shared", "Child"), ("shared", "Solo")])
    report.expect("口径 EACH/先按名字、再按所属对象排（同名那三行按文档顺序稳定）",
                  [(r["name"], r["classes"]) for r in each if r["name"] == "shared"],
                  [("shared", ["Base", "Child", "Solo"])] * 3)

    # ── 口径写错要当场炸 ──
    try:
        query.search(objs, "", "", cross="按名字")
        report.truthy("口径/不认识的 cross → 抛错", False, "没有抛错")
    except ValueError as exc:
        report.truthy("口径/不认识的 cross → 抛错（不许静默退化成某一种）",
                      "按名字" in str(exc), str(exc))

    # ── 入口：`Query` 把"载荷从哪儿来 + 本库的别名与口径"绑成两个入口 ──
    # 只给三样就够（各库 `index.py` 那份 `Library` 正好都有）——这就是"装配与查询分家"的接口。
    source = SimpleNamespace(store=SimpleNamespace(load=lambda: {"objects": _flat()}),
                             aliases={"kid": "Base"}, cross=query.EACH)
    entry = query.Query(source)
    report.expect("入口/search 与 describe 来自共用件（注册表据此认这棵树）",
                  [entry.search.__module__, entry.describe.__module__],
                  ["knowledge_virtuoso.database.core.query"] * 2)
    report.expect("入口/签名就是工具那两个参数（四库一致）",
                  (list(inspect.signature(entry.search).parameters),
                   list(inspect.signature(entry.describe).parameters)),
                  (["object", "keyword"], ["object"]))
    report.expect("入口/别名与跨对象口径取 source 的那两份（别名认了、EACH 生效）",
                  [(r["name"], r["definedIn"]) for r in entry.search("kid")],
                  [("baseOnly", "Base"), ("shared", "Base")])
    report.expect("入口/describe 走同一份别名",
                  entry.describe("kid")["id"], "Base")
    report.expect("入口/载荷只取里面的 `objects`（顶层那两键它不关心）",
                  len(entry.search("")), 5)

    # ── 继承：给了选择器时按链合并，子覆盖父（`merged`，无父的库退化成取自身）──
    chain = _inherit()
    report.expect("继承/子覆盖父，且逐条记得来自哪一层",
                  [(r["name"], r["definedIn"]) for r in query.search(chain, "Child")],
                  [("baseOnly", "Base"), ("childOnly", "Child"), ("shared", "Child")])
    report.expect("继承/没有继承的库（parent 全 None）合并退化成取自身",
                  [(r["name"], r["definedIn"]) for r in query.search(objs, "Solo")],
                  [("shared", "Solo")])

    # ── describe：选择器 → 对象记录（渲染的对象头要它）──
    report.expect("describe/解析到的对象原样给出来",
                  query.describe(objs, "Child")["id"], "Child")
    report.expect("describe/别名也认（走同一套 resolve）",
                  query.describe(objs, "kid", {"kid": "Child"})["id"], "Child")
    report.expect("describe/没给选择器或认不出 → None（渲染据此不加对象头）",
                  [query.describe(objs, ""), query.describe(objs, "没有这个")], [None, None])


if __name__ == "__main__":
    report = Report("database/core/test_query")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
