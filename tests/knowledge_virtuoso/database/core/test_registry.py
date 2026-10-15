#!/usr/bin/env python3
"""属性库注册表：`database/core/registry.py`。

注册表是**接线**那一层：`server.py` 拿发现的库去装配**一个** `search_attr` 工具（按 `lib`
路由），`cli.py` 按发现的库生成构建子命令。所以文件锁住的是"库里声明的东西和它真收的
参数对得上"——**这是会静默坏掉的一道缝**：

* `NAME` 与目录名对不上 → 会把索引写到别人家去；
* **查询入口不是共用那一个**（自己写了一个 `search`）→ 同一个问题在四个库里会有四份答复；
* `render` 的前四个参数不是 `rows/object/keyword/obj` → 渲染被调用时参数错位；
* `DOC` 里把参数写成别的名字 → 工具列表看着正常，LLM 照着描述调用却次次 schema 不符。

不读索引、不需要 doc。
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
from knowledge_virtuoso.database.core import registry  # noqa: E402
from knowledge_virtuoso.database.core.assembly import Library  # noqa: E402

# 四个库名。**没有"选择器词汇"这一列了**：参数名四库共用（`object`），各库的词汇退成
# `LIB.aliases` 那张表，不是谁的接口。
_EXPECTED = ("cdfdb", "db", "dd", "techdb")

_SHARED_ENTRY = "knowledge_virtuoso.database.core.query"


def _stub() -> SimpleNamespace:
    """一棵"长对了"的树：查询入口取自共用件（`Query`），其余是必需的声明。"""
    lib = Library(name="x", version=1, doc_parts=(), parse=lambda p: {},
                  decorate=lambda r: {"objects": {}})
    entry = query.Query(lib)
    return SimpleNamespace(NAME="x", LABEL="x", DOC="参数:\n  object: …",
                           parse=lib.parse, decorate=lib.decorate, build=lib.build,
                           search=entry.search, describe=entry.describe,
                           render=lambda rows, object="", keyword="", obj=None: "")


def run(report: Report, update: bool = False) -> None:
    report.expect("发现/四个属性库都在，且顺序稳定（按 NAME）",
                  [lib.NAME for lib in registry.LIBS], list(_EXPECTED))
    report.expect("发现/库名 = 目录名 = 索引目录名 = 载荷里的 lib",
                  [lib.NAME for lib in registry.LIBS], list(registry.names()))

    for lib in registry.LIBS:
        # **声明落在库根的 `index.py`**（装配来自 `core/assembly.py`、查询入口来自
        # `core/query.py`，都不在库里）。
        # 光"接口齐全"不够——那两行搬回库里也照样齐全，看落点才知道有没有真分家。
        index_module = sys.modules.get(f"{lib.__name__}.index")
        report.truthy(f"发现/{lib.NAME} 的声明落在库根的 index.py",
                      index_module is not None and index_module.LIB is lib.LIB,
                      index_module)
        report.truthy(f"发现/{lib.NAME} 接口齐全（{len(registry.REQUIRED_ATTRS)} 项）",
                      all(hasattr(lib, name) for name in registry.REQUIRED_ATTRS),
                      [n for n in registry.REQUIRED_ATTRS if not hasattr(lib, n)])
        # DOC 是**给 LLM 看的**：参数名写错时，工具列表照样正常，调用却次次 schema 不符。
        report.truthy(f"发现/{lib.NAME} 的 DOC 讲的是共用的参数名 object",
                      "object:" in lib.DOC and lib.LABEL, lib.DOC[:40])
        # 入口就一个：来自共用件，签名也必须是那一份
        report.expect(f"接口/{lib.NAME} 的查询入口来自共用件",
                      [lib.search.__module__, lib.describe.__module__],
                      [_SHARED_ENTRY] * 2)
        # **同一个函数对象**才是"查询只有一个实现"的直接证据（绑定不同而已）
        first = registry.LIBS[0]
        report.expect(f"接口/{lib.NAME} 的入口与别家是同一个函数对象",
                      [lib.search.__func__ is first.search.__func__,
                       lib.describe.__func__ is first.describe.__func__],
                      [True, True])
        # `render` 是各库自己的声明，所以逐库钉它前四个参数：**顺序**是关键，
        # 错位了照样能调用，只是印出来的是别人的列。
        report.expect(f"接口/{lib.NAME} 的 render 前四个参数是 rows/object/keyword/obj",
                      list(inspect.signature(lib.render).parameters)[:4],
                      ["rows", "object", "keyword", "obj"])

    # ── 坏树要被认出来（真发现循环里是"警告并跳过"，这里直接钉判据本身）──
    report.expect("校验/长对了的树 → 通过", registry._entry_mismatch(_stub()), None)
    for label, patch in (
            ("自己写了一个 search（四库会有四份答复）",
             {"search": lambda object="", keyword="": []}),
            ("自己写了一个 describe",
             {"describe": lambda object: None}),
            ("render 的选择器参数还叫老名字", {"render": lambda rows, className="", keyword="": ""}),
            ("render 少了 obj", {"render": lambda rows, object="", keyword="": ""})):
        stub = _stub()
        for key, value in patch.items():
            setattr(stub, key, value)
        report.truthy(f"校验/{label} → 出声",
                      registry._entry_mismatch(stub) is not None, registry._entry_mismatch(stub))

    # ── 按名取与发现结果打印 ──
    report.expect("发现/get 按名取到同一个模块",
                  [registry.get("dd").NAME, registry.get("db") is registry.LIBS[1]], ["dd", True])
    try:
        registry.get("没有这个库")
        report.truthy("发现/取不存在的库要 KeyError", False, "没有抛错")
    except KeyError:
        report.truthy("发现/取不存在的库要 KeyError", True)
    report.truthy("发现/check() 把四个库都打出来",
                  all(lib.NAME in registry.check() for lib in registry.LIBS), registry.check()[:80])


if __name__ == "__main__":
    report = Report("database/core/test_registry")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
