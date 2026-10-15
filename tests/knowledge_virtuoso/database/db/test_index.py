#!/usr/bin/env python3
"""③ **声明**：`database/db/index.py`（库根那一份 `LIB`）。

**与 src 一一对应**——本文件在 `db/` 下，对着同级的 `db/index.py`。那份文件只填**声明**：
库名、载荷版本、来源文档、①② 两层、别名表、跨对象口径。而**装配与查询入口来自共用件**
（`database/core/assembly.py` 的 `Library`、`core/query.py`），那两处由
`database/core/test_assembly.py` 与 `test_query.py` 管。

    test_index.py      ↔ db/index.py            fixtures/search.json
    test_render.py     ↔ db/__init__.py         cases/（那是 `RenderSpec` 的渲染 golden）

这一层测的是"**本库的声明对不对**"：

- **检索**：走库的公开接口（共用入口按 `LIB` 现绑），跑在 `fixtures/search.json` 的手写载荷上
  （**手写**，不引厂商原文——不读真索引、不需要 doc）；
- **选择器词汇**：`LIB.aliases` 那几条兼容写法（本库独有的）；
- **继承合并**：db 是四库里唯一有 `parent` 的，这里验它在**本库这份载荷**上的行为；
- **跨对象口径**：`LIB.cross == POOL`（表里没有"所属对象"列，分行分不出归属）。

**行形状不在这**：`rw` 由原文的 `modify` 推、② 就算好落盘了（见 `core/test_decorate.py`）；
行 = 记录 + `definedIn`/`classes` 两个查询上下文字段，那是 `core/query.py` 的事。

索引装配与版本号（`LIB.payload`/`build`/`store`）**没有**断言，只有手工的重建逐字节比对，
见 `tests/README.md`。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.core import query  # noqa: E402
from knowledge_virtuoso.database import db  # noqa: E402


def _objects() -> dict:
    """`fixtures/search.json` 里的手写对象表（供纯函数断言用，不碰磁盘索引）。

    那张表里有四条链，够覆盖本层的几种情形：`Generic Object → Generic Figure →
    Generic Shape → Rectangle`（`Rectangle` 自身 0 条，纯转发）、`Cellview → Generic
    Object`（**重名**：`objType` 两边都有，子更具体）、`Label → Generic Shape`。
    """
    return read_json(HERE / "fixtures" / "search.json")["payload"]["objects"]


def run(report: Report, update: bool = False) -> None:
    # ── 检索：手写载荷 → 选择器与合并 ──
    run_attr_search_cases(HERE, db, report)

    objs = _objects()

    # ── 选择器：表标题 / 运行时名 / 忽略大小写与空格 / 兼容别名 / 不认识 ──
    report.expect("检索/选择器解析的几条路径",
                  [objects_mod.resolve(objs, "Cellview"), objects_mod.resolve(objs, "cellview"),
                   objects_mod.resolve(objs, "CELLVIEW"),
                   objects_mod.resolve(objs, "rect", db.LIB.aliases),
                   objects_mod.resolve(objs, "Rectangle"), objects_mod.resolve(objs, "没有这个")],
                  ["Cellview", "Cellview", "Cellview", "Rectangle", "Rectangle", None])

    # ── 继承合并（查询时算）：子覆盖父、definedIn 记归属、纯转发全靠继承 ──
    merged = objects_mod.merged(objs, "Rectangle")
    report.expect("检索/合并后拿到整条链上的属性（Object←Figure←Shape）",
                  sorted(merged),
                  ["bBox", "cellView", "layerName", "layerNum", "objType", "prop", "purpose"])
    report.expect("检索/纯转发对象自身 0 条，合并后 7 条",
                  (len(objs["Rectangle"]["attrs"]), len(merged)), (0, 7))
    report.expect("检索/子覆盖父：Cellview 的 objType 取代 Generic Object 的",
                  (objects_mod.merged(objs, "Cellview")["objType"]["definedIn"],
                   objects_mod.merged(objs, "Cellview")["cellView"]["definedIn"]),
                  ("Cellview", "Generic Object"))

    # ── 本库自己那几句：别名表不空、跨对象按名收一遍 ──
    report.expect("声明/本库的选择器词汇非空（`rect`/`inst` 那几张表）",
                  sorted(db.LIB.aliases)[:2], ["customVia", "inst"])
    report.expect("声明/本库的跨对象口径：按名去重", db.LIB.cross, query.POOL)


if __name__ == "__main__":
    report = Report("database/db/test_index")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
