#!/usr/bin/env python3
"""属性库注册表：`database/core/registry.py`。

注册表是**接线**那一层：`server.py` 按发现的库生成 MCP 工具（工具名 = `<NAME>_search_attr`，
第一个参数名 = 该库自己的 `SELECTOR`），`cli.py` 按发现的库生成构建子命令。
所以文件锁住的是"库里声明的东西和它真收的参数对得上"——**这是会静默坏掉的一道缝**：
`SELECTOR` 写错时工具照样注册得出来（名字对），但每次调用都会因 schema 不符而失败。

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

from knowledge_virtuoso.database.core import registry  # noqa: E402

_EXPECTED = {
    "cdfdb": ("cdfdb_search_attr", "className"),
    "db": ("db_search_attr", "objType"),
    "dd": ("dd_search_attr", "object"),
    "techdb": ("techdb_search_attr", "className"),
}


def run(report: Report, update: bool = False) -> None:
    report.expect("发现/四个属性库都在，且顺序稳定（按 NAME）",
                  [lib.NAME for lib in registry.LIBS], sorted(_EXPECTED))
    report.expect("发现/库名 = 目录名 = 索引目录名",
                  [lib.NAME for lib in registry.LIBS], list(registry.names()))

    for lib in registry.LIBS:
        tool, selector = _EXPECTED[lib.NAME]
        report.expect(f"发现/{lib.NAME} 的工具名与选择器",
                      (registry.tool_name(lib), lib.SELECTOR), (tool, selector))
        report.truthy(f"发现/{lib.NAME} 接口齐全（{len(registry.REQUIRED_ATTRS)} 项）",
                      all(hasattr(lib, name) for name in registry.REQUIRED_ATTRS),
                      [n for n in registry.REQUIRED_ATTRS if not hasattr(lib, n)])
        report.truthy(f"发现/{lib.NAME} 的 DOC 里有它自己的选择器名",
                      lib.SELECTOR in lib.DOC and lib.LABEL, lib.DOC[:40])

    # ── 选择器名必须真的出现在 search / render 的签名里（工具就是按它造参数名的）──
    for lib in registry.LIBS:
        report.truthy(f"接口/{lib.NAME} 的 search 收 {lib.SELECTOR!r} 与 keyword",
                      set(inspect.signature(lib.search).parameters) == {lib.SELECTOR, "keyword"},
                      list(inspect.signature(lib.search).parameters))
        report.truthy(f"接口/{lib.NAME} 的 render 收 rows + {lib.SELECTOR!r} + keyword",
                      list(inspect.signature(lib.render).parameters)
                      == ["rows", lib.SELECTOR, "keyword"],
                      list(inspect.signature(lib.render).parameters))

    # ── 坏树要被认出来（真发现循环里是"警告并跳过"，这里直接钉判据本身）──
    good = SimpleNamespace(SELECTOR="object",
                           search=lambda object="", keyword="": [],
                           render=lambda rows, object="", keyword="": "")
    report.expect("校验/接口对得上 → 通过", registry._selector_mismatch(good), None)
    report.expect("校验/SELECTOR 不在 search 签名里 → 出声",
                  registry._selector_mismatch(
                      SimpleNamespace(SELECTOR="object",
                                      search=lambda className="", keyword="": [],
                                      render=lambda rows, object="", keyword="": ""))
                  is not None, True)
    report.expect("校验/search 没有 keyword → 出声",
                  registry._selector_mismatch(
                      SimpleNamespace(SELECTOR="object",
                                      search=lambda object="": [],
                                      render=lambda rows, object="", keyword="": ""))
                  is not None, True)

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
