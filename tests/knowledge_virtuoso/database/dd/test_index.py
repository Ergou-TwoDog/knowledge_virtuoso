#!/usr/bin/env python3
"""③ **声明**：`database/dd/index.py`（库根那一份 `LIB`）。

**与 src 一一对应**——本文件在 `dd/` 下，对着同级的 `index.py`。那份文件只填**声明**：
库名、载荷版本、来源文档、①② 两层、别名表（本库没有）、跨对象口径、**本库自己的构建期
校验**。装配与查询入口来自共用件（`core/assembly.py` / `query.py`）。

这一层测的是"**本库的声明对不对**"：

- **检索**：走库的公开接口（共用入口按 `LIB` 现绑），跑在 `fixtures/search.json` 的手写载荷上（**手写**，不读真索引）；
- **跨对象口径**：`LIB.cross == POOL`（同一条记录本来就摊在多个对象下，分行只会重复）；
- **本库自己的校验**（`_check`）：一个对象都没有 / 某对象一条记录都没有 / 关系基数不像
  `1:n` / 同名既当属性又当关系；顶层键集、`lib` 与库名、两层键集由共用的那道门管。
  **"适用对象在不在全集里"不在这儿**——那要在摊平之前才看得全，归 ②。

**选择器解析不在这**：四库共用 `objects.resolve`（本库原先有一份简化版 `_resolve`，现在
没了），所以那条断言在 `core/test_objects.py`。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.core import query  # noqa: E402
from knowledge_virtuoso.database import dd  # noqa: E402


def _obj(oid: str, attrs: list[dict]) -> dict:
    """七键对象（本库除 `id` 外全是空的——原文只给了这六个名字）。"""
    return {"id": oid, "title": None, "runtime": None, "section": None,
            "desc": None, "parent": None, "attrs": attrs}


def _rec(name: str, kind: str = "attr", card: str | None = None, objects=("lib",)) -> dict:
    """一条记录——用 ② 那个同一个构造器，测试就不必自己抄一份键表。"""
    return objects_mod.record(name, kind=kind, cardinality=card, objectTypes=list(objects))


def _payload(objects: dict, **top) -> dict:
    """手写载荷的**顶层三键**——构建期校验只认这个形状（`lib` 必须对得上本库）。"""
    return {"version": dd.LIB.version, "lib": dd.LIB.name, "objects": objects, **top}


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, dd, report)

    # ── 本库自己的那几条校验 ──
    def _bad(objects: dict, **top) -> bool:
        try:
            dd.LIB.validate(_payload(objects, **top))
            return False
        except ValueError:
            return True

    report.expect("校验/干净的一份通过",
                  _bad({"lib": _obj("lib", [_rec("a")])}), False)
    report.expect("校验/一个对象都没有要抛错",
                  _bad({}), True)
    report.expect("校验/某个对象一条记录都没有要抛错",
                  _bad({"lib": _obj("lib", [])}), True)
    report.expect("校验/关系基数不像 `1:n` 要抛错",
                  _bad({"lib": _obj("lib", [_rec("r", "relation", "很多")])}), True)
    report.expect("校验/同一个名字既当属性又当关系要抛错（摊平后未必落在同一个对象里）",
                  _bad({"lib": _obj("lib", [_rec("a")]),
                        "cell": _obj("cell", [_rec("a", "relation", "1:1", ("cell",))])}), True)
    report.expect("校验/同一对象下记录重名要抛错（共用件管）",
                  _bad({"lib": _obj("lib", [_rec("a"), _rec("a")])}), True)
    report.expect("校验/记录键集不全要抛错（ATTR_KEYS）",
                  _bad({"lib": _obj("lib", [{k: v for k, v in _rec("a").items()
                                             if k != "kind"}])}), True)
    report.expect("校验/载荷里的 lib 与库名不符要抛错",
                  _bad({"lib": _obj("lib", [_rec("a")])}, lib="db"), True)

    # ── 本库自己那两句：没有别名表、跨对象按名收一遍 ──
    report.expect("声明/本库没有别名表（对象名就是选择器）", dd.LIB.aliases, {})
    report.expect("声明/本库的跨对象口径：按名去重", dd.LIB.cross, query.POOL)


if __name__ == "__main__":
    report = Report("database/dd/test_index")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
