#!/usr/bin/env python3
"""
knowledge_virtuoso.database.index — 属性查询的**顶层联合**：一个工具，四个库。

磁盘上仍是**四份索引**（`<数据目录>/<库>/index.json`）——各自版本、各自惰性重建、
一个坏了不牵连另一个；这一层只做"按库路由 + 把结果拼成一次回答"。位置与角色对着
`functions/index.py`（那边是"把多个来源装成一张索引并查询"），区别是**这里连"装"都
不需要**：`database/core/registry.py` 的 `LIBS` 就是那张库表，各库的 `LIB.store` 各自惰性加载。

**为什么不装成一张文件**：那样会同时丢掉三件事——每个库可以有自己的载荷版本与重建
时机；某个库的原文/解析器坏了只让它自己不可查；只问一个库时不必加载全部。何况载荷顶层
就带着"我是哪个库"（`lib`，装载时还要与目录名核对），装一张反而要把这份身份抹掉。

**单库调用（给了 `lib`）的输出与各库自己的 `render()` 逐字相同**——合并工具不该改变
任何人已经看到的文本；跨库调用（`lib` 留空）才另立格式：每库一节、节首 `── <库名> ──`、
只印有结果的库。
"""

# **不要加 `from __future__ import annotations`**：`search_attr` 是直接被 `mcp.add_tool`
# 注册成工具的真函数，FastMCP 建 schema 时要做 `issubclass(param.annotation, Context)`
# ——注解一旦变成字符串，那句就 TypeError，服务起不来。（`server.py` 顶上也吃过同一记。）

from knowledge_virtuoso.database.core import registry

__all__ = ["search_attr", "libs", "doc"]

# 跨库时每节的开头。单库调用**不印**这一行，所以单库输出与各库自己的渲染逐字相同。
_SECTION = "── {name} ──"

_HEAD = """搜索 Virtuoso 对象属性。四个库各有各的对象宇宙，用 `lib` 选一个，或用 `object` 跨库搜。

参数:
  lib:     哪个库，取 {libs} 之一。**留空 = 四个都搜**（四库的对象名实测两两不重，
           所以跨库搜不会歧义）。
  object:  对象／类／数据管理对象的名字。**四个库共用这一个参数名**，但各库认的写法
           不同，见下面各段。留空 = 该库的全部对象。
  keyword: 名字关键词（子串匹配）。留空列出全部。

返回:
  lib 给了   → 就是那个库的输出（与各库自己的渲染逐字相同；命中时会先回显"问的是谁"）。
  lib 留空   → 每库一节，节首一行 `── <库名> ──`，**只印有结果的库**；都没结果才给一句提示。

各库的 `object` 认什么写法：
"""


def libs() -> tuple[str, ...]:
    """可选值（报错文案与工具描述用）。"""
    return registry.names()


def doc() -> str:
    """工具描述 = 总说明 + 各库自己的 `DOC`。

    这样**加一个属性库仍然只加一棵树**：总说明不动，新库的 `DOC` 自动进描述。
    """
    parts = [_HEAD.format(libs=" / ".join(libs()))]
    for module in registry.LIBS:
        parts.append(f"── {module.NAME}（{module.LABEL}）──\n{module.DOC.strip()}")
    return "\n".join(parts)


def _rows_and_text(module, obj: str, keyword: str) -> tuple[list, str]:
    """问一个库：行 + 文本。**只问一次**（跨库判定"有没有结果"要看行，不是看文本）。"""
    rows = module.search(obj, keyword)
    return rows, module.render(rows, obj, keyword, module.describe(obj))


def search_attr(lib: str = "", object: str = "", keyword: str = "") -> str:  # noqa: A002
    """按库 + 对象 + 关键词查属性，返回文本。**MCP 工具的唯一入口。**

    `object` 是四个库共用的选择器参数名（各库原先叫 `objType`/`className`/`object`）；
    它在各库里认的写法见工具描述里的分段说明。
    """
    if lib:
        try:
            module = registry.get(lib)
        except KeyError:
            # 库名打错**不能**静默返回空——那看起来和"查不到"一模一样。
            raise ValueError(f"没有这个属性库：{lib!r}。可选：{'、'.join(libs())}") from None
        return _rows_and_text(module, object, keyword)[1]

    sections = []
    for module in registry.LIBS:
        rows, text = _rows_and_text(module, object, keyword)
        if rows:                                   # 只印有结果的库
            sections.append(f"{_SECTION.format(name=module.NAME)}\n{text}")
    if sections:
        return "\n\n".join(sections)

    ctx = f"object={object!r}" if object else ""
    if keyword:
        ctx += (" " if ctx else "") + f"keyword={keyword!r}"
    return (f"未找到匹配 {ctx or '（给的条件）'}："
            f"已查 {'、'.join(libs())}。")
