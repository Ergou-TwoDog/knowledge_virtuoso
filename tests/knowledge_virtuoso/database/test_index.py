#!/usr/bin/env python3
"""**顶层联合**：`database/index.py`（一个工具，四个库）。

**与 src 一一对应**——本文件在 `database/` 下，对着同级的 `index.py`。

这一层测的是"**按库路由 + 把结果拼成一次回答**"，不测任何一个库怎么读原文（那是
`<库>/core/` 的事）：

* **单库**：给了 `lib` 就该**逐字**等于那个库自己的 `render(...)`——合并工具不该改变
  任何人已经看到的文本；
* **跨库**：`lib` 留空 → 每库一节、节首 `── <库名> ──`、**只印有结果的库**；
* **库名打错**要明确报错并列出可选值（静默返回空会与"查不到"混成一回事）。

载荷是**手写注入**的（`lib.LIB.store._data = payload`，与 `tests/common.py` 的
`run_attr_search_cases` 同一手法）：不读真索引、不需要 doc、不碰磁盘。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, store_of  # noqa: E402

from knowledge_virtuoso.database import index as attr_index  # noqa: E402
from knowledge_virtuoso.database.core import objects  # noqa: E402
from knowledge_virtuoso.database.core import registry  # noqa: E402


def _obj(oid: str, attrs, parent=None, **kw) -> dict:
    """七键对象（db/techdb/cdfdb 共用那套容器）。"""
    return {"id": oid, "title": oid, "runtime": None, "section": None, "desc": None,
            "parent": parent, "attrs": attrs, **kw}


def _rec(name: str, **kw) -> dict:
    """一条记录（`ATTR_KEYS` 全给）——手写载荷用，键集只有一处定义。"""
    return objects.record(name, **kw)


def _payloads() -> dict:
    """四个库各一份最小载荷（顶层三键齐全）。对象名**故意两两不重**（真实索引里也是）。"""
    return {
        "db": {"version": 5, "lib": "db", "objects": {
            "Rectangle": _obj("Rectangle", [
                _rec("bBox", kind="attr", type="bBox", rw="ro", modify="no",
                     desc="The bounding box."),
                _rec("layerName", kind="attr", type="string", rw="rw", modify="yes",
                     desc="Layer name."),
            ]),
            "Marker": _obj("Marker", [
                _rec("markerType", kind="attr", type="string", rw="ro", modify="no",
                     desc="Kind."),
            ]),
        }},
        "techdb": {"version": 5, "lib": "techdb", "objects": {
            "viaDefs": _obj("viaDefs", [
                _rec("bBoxLayer", kind="attr", type="l_string", desc="A list of layers."),
            ]),
        }},
        "cdfdb": {"version": 5, "lib": "cdfdb", "objects": {
            "cdfParamId": _obj("cdfParamId", [
                _rec("defValue", kind="attr", rw="rw", desc="Default value.", source="field"),
            ]),
        }},
        "dd": {"version": 5, "lib": "dd", "objects": {
            "lib": _obj("lib", [
                _rec("name", kind="attr", objectTypes=["lib", "cell"]),
                _rec("cells", kind="relation", cardinality="1:n", objectTypes=["lib"]),
            ]),
            "cell": _obj("cell", [
                _rec("name", kind="attr", objectTypes=["lib", "cell"]),
            ]),
        }},
    }


def _inject(payloads: dict) -> dict:
    """把四份手写载荷塞进各库的进程内缓存，返回原值以便还原。"""
    saved = {}
    for name, payload in payloads.items():
        store = store_of(registry.get(name))           # noqa: SLF001  那个库的 Store
        saved[name] = store._data                      # noqa: SLF001
        store._data = payload                          # noqa: SLF001
    return saved


def _restore(saved: dict) -> None:
    for name, value in saved.items():
        store_of(registry.get(name))._data = value     # noqa: SLF001


def run(report: Report, update: bool = False) -> None:
    saved = _inject(_payloads())
    try:
        # ── 单库：逐字等于该库自己的渲染 ──
        for name in registry.names():
            module = registry.get(name)
            if name == "dd":
                obj, keyword = "lib", ""
            elif name == "db":
                obj, keyword = "Rectangle", "bBox"
            elif name == "techdb":
                obj, keyword = "viaDefs", ""
            else:
                obj, keyword = "cdfParamId", "defValue"
            mine = module.render(module.search(obj, keyword), obj, keyword,
                                 module.describe(obj))
            report.expect(f"联合/单库 lib={name} 的输出与它自己的 render 逐字相同",
                          attr_index.search_attr(name, obj, keyword), mine)

        # ── 跨库：只印有结果的库，节首是 `── <库名> ──` ──
        text = attr_index.search_attr("", "Rectangle", "bBox")
        report.expect("联合/跨库只印有结果的库（Rectangle 只有 db 认）",
                      [ln for ln in text.splitlines() if ln.startswith("──")],
                      ["── db ──"])
        report.expect("联合/跨库那一节的内容就是该库自己的输出",
                      text, "── db ──\n" + registry.get("db").render(
                          registry.get("db").search("Rectangle", "bBox"), "Rectangle", "bBox",
                          registry.get("db").describe("Rectangle")))

        # keyword="b"：db 的 bBox、techdb 的 bBoxLayer 命中；cdfdb 的 defValue 与 dd 的不含 b
        wide = attr_index.search_attr("", "", "b")
        report.expect("联合/跨库关键词命中多个库时每库一节（没命中的库不出现）",
                      [ln for ln in wide.splitlines() if ln.startswith("──")],
                      ["── db ──", "── techdb ──"])

        # ── 都没结果：合并成一句，并点名查过哪几个库 ──
        none = attr_index.search_attr("", "没有这个对象", "")
        report.truthy("联合/跨库全无结果时给一条合并提示（点名查过的库）",
                      none.startswith("未找到匹配") and all(n in none for n in registry.names()),
                      none)

        # ── 库名打错：明确报错，并列出可选值 ──
        try:
            attr_index.search_attr("没有这个库", "Rectangle")
            report.truthy("联合/库名不认识 → 抛错", False, "没有抛错")
        except ValueError as exc:
            report.truthy("联合/库名不认识 → 抛错且列出可选值",
                          all(name in str(exc) for name in registry.names()), str(exc))

        # ── 工具描述：总说明 + 各库自己的 DOC 都在里面 ──
        description = attr_index.doc()
        report.truthy("描述/四个库的 DOC 都拼进去了",
                      all(lib.DOC.strip() in description for lib in registry.LIBS),
                      [lib.NAME for lib in registry.LIBS if lib.DOC.strip() not in description])
        report.truthy("描述/点名了 lib 的可选值",
                      all(name in description for name in registry.names()))
    finally:
        _restore(saved)


if __name__ == "__main__":
    report = Report("database/test_index")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
