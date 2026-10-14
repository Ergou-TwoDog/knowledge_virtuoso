#!/usr/bin/env python3
"""属性库发现：扫描 `database/` 下的库，不再手工登记。

**加一个属性库 = 在 `database/` 下加一棵树**——实现 `database/<库>/__init__.py` 里那套
接口（`NAME` / `LABEL` / `SELECTOR` / `DOC` / `build` / `search` / `render`），
`server.py`、`cli.py` 与本文件都不用改：

* `server.py` 按发现的库逐个生成 MCP 工具（工具名 = `<NAME>_search_attr`，第一个参数名
  用该库自己的 `SELECTOR`），所以四个库各有各的调用契约；
* `cli.py` 按发现的库生成 `knowledge-virtuoso-build <库>` 子命令。

**这不是"来源抽象"**：各库的解析器、渲染器、索引仍然各自独立（`database/core/store.py`
只是把"读 JSON / 坏了重建 / 缓存 / 锁"这一件事收敛成一份）。这里发现的只是**接线**——
免得加一个库要改一圈 import 与工具定义。

发现失败（导入出错、接口不全、目录名与 `NAME` 对不上）的库**警告并跳过**：一棵坏树不该
拖垮服务。`knowledge-virtuoso-build libs` 可以把发现结果打出来看。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys

from knowledge_virtuoso import database as DATABASE_PACKAGE

# 库接口：缺一项就不认这棵树。宁可不加载，也不要半残的库在跑。
REQUIRED_ATTRS = ("NAME", "LABEL", "SELECTOR", "DOC", "build", "search", "render")

# `database/` 下不是属性库的包：`core` 是三库共用的索引存取（见 store.py）。
_SHARED = {"core"}


def _discover() -> tuple:
    found = []
    for info in pkgutil.iter_modules(DATABASE_PACKAGE.__path__):
        if not info.ispkg or info.name in _SHARED:
            continue
        try:
            module = importlib.import_module(f"{DATABASE_PACKAGE.__name__}.{info.name}")
        except Exception as exc:  # 一棵树写坏了，别的库照常工作
            print(f"属性库 {info.name} 跳过（导入失败 {type(exc).__name__}: {exc}）",
                  file=sys.stderr)
            continue
        missing = [name for name in REQUIRED_ATTRS if not hasattr(module, name)]
        if missing:
            print(f"属性库 {info.name} 跳过（接口不全，缺 {', '.join(missing)}）", file=sys.stderr)
            continue
        if module.NAME != info.name:
            # 目录名即索引目录名（`index_path(NAME)`）也即工具名前缀。对不上说明这棵树
            # 放错了地方或 `NAME` 写错了，加载起来会把索引写到别人家去。
            print(f"属性库 {info.name} 跳过（NAME={module.NAME!r} 与目录名不符）", file=sys.stderr)
            continue
        bad = _selector_mismatch(module)
        if bad:
            # 最阴的一类坏法：`server.py` 按 SELECTOR 造工具的参数名，而库里 search 收的
            # 是别的名字 → 工具列表看着正常（参数名对），一调用就全错。宁可不认这棵树。
            print(f"属性库 {info.name} 跳过（{bad}）", file=sys.stderr)
            continue
        found.append(module)
    # 按 NAME 排序只为让工具/子命令的顺序稳定可预期；**属性库之间没有"谁覆盖谁"**，
    # 所以不像 `functions/sources` 那样需要 ORDER。
    return tuple(sorted(found, key=lambda module: module.NAME))


def _selector_mismatch(module) -> str | None:
    """`SELECTOR` 必须真的出现在 `search` / `render` 的签名里。对不上返回说明，对上了返回 None。"""
    for fn_name in ("search", "render"):
        params = inspect.signature(getattr(module, fn_name)).parameters
        if module.SELECTOR not in params:
            return f"{fn_name} 的签名里没有 SELECTOR={module.SELECTOR!r}（实际有 {list(params)}）"
    if "keyword" not in inspect.signature(module.search).parameters:
        return "search 的签名里没有 keyword"
    return None


LIBS = _discover()

_seen = {lib.NAME for lib in LIBS}
if len(_seen) != len(LIBS):  # 目录名唯一 + NAME==目录名，理论上到不了这里
    raise RuntimeError(f"属性库 NAME 重复：{[lib.NAME for lib in LIBS]}")


def names() -> tuple[str, ...]:
    """发现到的库名（`cli.py` 的子命令、索引目录名）。"""
    return tuple(lib.NAME for lib in LIBS)


def get(name: str):
    """按库名取库模块；没有就 KeyError。"""
    for lib in LIBS:
        if lib.NAME == name:
            return lib
    raise KeyError(name)


def tool_name(lib) -> str:
    """该库的 MCP 工具名。默认 `<NAME>_search_attr`，库里可以定义 `TOOL` 覆盖。"""
    return getattr(lib, "TOOL", f"{lib.NAME}_search_attr")


def check() -> str:
    """发现结果（`knowledge-virtuoso-build libs` 打印这个）。"""
    if not LIBS:
        return "没发现任何属性库（database/ 下应有实现接口的包）"
    lines = [f"发现 {len(LIBS)} 个属性库："]
    width = max(len(lib.NAME) for lib in LIBS)
    for lib in LIBS:
        lines.append(f"  {lib.NAME:<{width}}  {tool_name(lib):<24} "
                     f"选择器={lib.SELECTOR:<12} {lib.LABEL}")
    return "\n".join(lines)
