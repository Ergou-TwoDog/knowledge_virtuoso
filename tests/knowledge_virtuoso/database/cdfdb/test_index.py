#!/usr/bin/env python3
"""③ **声明**：`database/cdfdb/index.py`（库根那一份 `LIB`）。

**与 src 一一对应**——本文件在 `cdfdb/` 下，对着同级的 `index.py`。那份文件只填**声明**：
库名、载荷版本、来源文档、①② 两层、别名表（本库没有）、跨对象口径、本库自己的构建期校验。
装配与查询入口来自共用件（`core/assembly.py` / `query.py`）。

这一层测的是"**本库的声明对不对**"：

- **检索**：走库的公开接口（共用入口按 `LIB` 现绑），跑在 `fixtures/search.json` 的手写载荷上（**手写**，不读真索引）；
- **跨类口径**：`LIB.cross == EACH`（与 techdb 同一口径）；
- **构建期校验**：`LIB.validate` 那道门（顶层键集 / `lib` 与库名 / 两层键集 / 本库的形状）。

**`rw`/`type` 的推法不在这**：那两样在 ② 就算好了（`core/decorate.py`），所以那些断言在
`core/test_decorate.py`。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.core import query  # noqa: E402
from knowledge_virtuoso.database import cdfdb  # noqa: E402


def _obj(cid: str, attrs: list[dict]) -> dict:
    """七键对象——`validate_objects` 就认这个键集（缺一个键构建期就该炸）。"""
    return {"id": cid, "title": cid, "runtime": None, "section": None,
            "desc": None, "parent": None, "attrs": attrs}


def _rec(name: str) -> dict:
    """一条记录——用 ② 那个同一个构造器，测试就不必自己抄一份键表。"""
    return objects_mod.record(name, kind="attr", source="field")


def _payload(objects: dict, **top) -> dict:
    """手写载荷的**顶层三键**——构建期校验只认这个形状（`lib` 必须对得上本库）。"""
    return {"version": cdfdb.LIB.version, "lib": cdfdb.LIB.name, "objects": objects, **top}


def run(report: Report, update: bool = False) -> None:
    # ── 检索：手写载荷 → 选择器 / 跨类各出一行 ──
    run_attr_search_cases(HERE, cdfdb, report)

    # ── 构建期校验 + 顶层三键 ──
    def _bad(payload: dict) -> bool:
        try:
            cdfdb.LIB.validate(payload)
            return False
        except ValueError:
            return True

    report.expect("校验/干净的一份通过",
                  _bad(_payload({"x": _obj("x", [_rec("a")])})), False)
    report.expect("校验/一个属性都没有的类要抛错",
                  _bad(_payload({"x": _obj("x", [])})), True)
    report.expect("校验/类内属性名重复要抛错",
                  _bad(_payload({"x": _obj("x", [_rec("a"), _rec("a")])})), True)
    report.expect("校验/类名形状不对要抛错（本库的 id 是标识符）",
                  _bad(_payload({"cdf DataId": _obj("cdf DataId", [_rec("a")])})), True)
    report.expect("校验/对象键集不全要抛错（七键）",
                  _bad(_payload({"x": {"id": "x", "attrs": []}})), True)
    report.expect("校验/记录键集不全要抛错（ATTR_KEYS）",
                  _bad(_payload({"x": _obj("x", [{k: v for k, v in _rec("a").items()
                                                  if k != "rw"}])})), True)
    report.expect("校验/载荷里的 lib 与库名不符要抛错",
                  _bad(_payload({"x": _obj("x", [_rec("a")])}, lib="techdb")), True)

    # ── 本库自己那两句：没有别名表、跨类各出各的行 ──
    report.expect("声明/本库没有别名表（类名就是选择器）", cdfdb.LIB.aliases, {})
    report.expect("声明/本库的跨对象口径：每个类各出各的行", cdfdb.LIB.cross, query.EACH)


if __name__ == "__main__":
    report = Report("database/cdfdb/test_index")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
