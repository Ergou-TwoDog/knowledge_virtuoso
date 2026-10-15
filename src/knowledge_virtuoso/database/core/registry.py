#!/usr/bin/env python3
"""属性库发现：扫描 `database/` 下的库，不再手工登记。

**加一个属性库 = 在 `database/` 下加一棵树**——实现 `database/<库>/__init__.py` 里那套
接口（`REQUIRED_ATTRS`），`server.py`、`cli.py` 与本文件都不用改：

* `server.py` 把发现的库交给 `database/index.py` 装配成**一个** `search_attr` 工具
  （按 `lib` 路由）；
* `cli.py` 按发现的库生成 `knowledge-virtuoso-build <库>` 子命令。

**这不是"来源抽象"**：各库的解析器、归一器与索引仍然各自独立（`database/core/` 那些共用件
只收敛"与是哪个库无关"的部分：载荷模型、装配与查询、渲染机制、索引存取）。这里发现的只是
**接线**——免得加一个库要改一圈 import 与工具定义。

发现失败（导入出错、接口不全、目录名与 `NAME` 对不上、**查询入口不是共用那一个**）的库
**警告并跳过**：一棵坏树不该拖垮服务。`knowledge-virtuoso-build libs` 可以把发现结果打出来看。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys

from knowledge_virtuoso import database as DATABASE_PACKAGE

# 库接口：缺一项就不认这棵树。宁可不加载，也不要半残的库在跑。
#
# `parse`/`decorate` **不是给别的模块调的**（上层只用 build/search/describe/render），而是把
# "每个库必须切成三层"变成**可校验的契约**：忘了切（或者把三层又揉回一个文件）的树会被发现
# 时警告并跳过，而不是悄悄地少一层。`describe(选择器) → 对象记录 | None` 则是渲染的对象头
# 要用的（渲染层自己不读索引，对象由调用方给）——dd 的对象记录里除 `id` 全是空的，所以它的
# 对象头只印 `对象 <id>`。
#
# **没有 `SELECTOR`**：四库共用一个参数名 `object`（工具也是），各库的"选择器词汇"退成了
# `LIB.aliases` 那张表——不再是谁的接口。
REQUIRED_ATTRS = ("NAME", "LABEL", "DOC", "parse", "decorate",
                  "build", "search", "describe", "render")

# 共用入口所在的模块：`search`/`describe` 必须来自它（见 `_entry_mismatch`）。
# 是 `core.query` 而不是 `core.assembly`——**查询的入口归查询那一层**（`Query`）。
_SHARED_ENTRY = "knowledge_virtuoso.database.core.query"

# `database/` 下不是属性库的包：`core` 是四库共用的那层（载荷模型、装配与查询、渲染机制、
# 索引存取、发现），见 core/README.md。
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
            # 目录名即索引目录名（`index_path(NAME)`）、即载荷里的 `lib`。对不上说明这棵树
            # 放错了地方或 `NAME` 写错了，加载起来会把索引写到别人家去。
            print(f"属性库 {info.name} 跳过（NAME={module.NAME!r} 与目录名不符）", file=sys.stderr)
            continue
        bad = _entry_mismatch(module)
        if bad:
            # 最阴的一类坏法：查询入口看着有、签名也对，但它不是共用那一个——同一个问题在
            # 四个库里会有四份答复。宁可不认这棵树。
            print(f"属性库 {info.name} 跳过（{bad}）", file=sys.stderr)
            continue
        found.append(module)
    # 按 NAME 排序只为让工具/子命令的顺序稳定可预期；**属性库之间没有"谁覆盖谁"**，
    # 所以不像 `functions/sources` 那样需要 ORDER。
    return tuple(sorted(found, key=lambda module: module.NAME))


def _entry_mismatch(module) -> str | None:
    """**查询入口必须是共用那一个**（`core/query.py` 的 `Query` 提供），签名也必须是那一份。

    以前查的是"各库声明的选择器名真的出现在它 `search` 的签名里"——那是"每库一套参数名"
    时代的守卫（工具就是按那个名字造参数的）。现在参数统一叫 `object`、入口由共用件出，
    所以查得更死：**自己写一个 `search` 就不认这棵树**，免得四库各答各的。
    """
    for fn in ("search", "describe"):
        where = getattr(getattr(module, fn), "__module__", "?")
        if where != _SHARED_ENTRY:
            return f"{fn} 不是共用入口（定义在 {where}）"
    for fn, want in (("search", ["object", "keyword"]), ("describe", ["object"]),
                     ("render", ["rows", "object", "keyword", "obj"])):
        params = list(inspect.signature(getattr(module, fn)).parameters)
        if fn == "render":
            params = params[:4]        # 之后允许各库再加可有可无的
        if params != want:
            return f"{fn} 的参数不是 {want}：{params}"
    return None


LIBS = _discover()

_seen = {lib.NAME for lib in LIBS}
if len(_seen) != len(LIBS):  # 目录名唯一 + NAME==目录名，理论上到不了这里
    raise RuntimeError(f"属性库 NAME 重复：{[lib.NAME for lib in LIBS]}")


def names() -> tuple[str, ...]:
    """发现到的库名（`cli.py` 的子命令、索引目录名、载荷里的 `lib`）。"""
    return tuple(lib.NAME for lib in LIBS)


def get(name: str):
    """按库名取库模块；没有就 KeyError。"""
    for lib in LIBS:
        if lib.NAME == name:
            return lib
    raise KeyError(name)


def check() -> str:
    """发现结果（`knowledge-virtuoso-build libs` 打印这个）。

    只报"这一个库自己长什么样"：查询工具只有一个、参数名四库共用，所以这里不再有
    "每库一个工具/一个参数名"那种列。
    """
    if not LIBS:
        return "没发现任何属性库（database/ 下应有实现接口的包）"
    lines = [f"发现 {len(LIBS)} 个属性库："]
    width = max(len(lib.NAME) for lib in LIBS)
    for lib in LIBS:
        lines.append(f"  {lib.NAME:<{width}}  {lib.LABEL}")
    return "\n".join(lines)
