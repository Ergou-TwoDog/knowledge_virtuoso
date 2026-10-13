#!/usr/bin/env python3
"""二次开发来源的渲染差异：digest 的 `（自定义）` 标记 + 头部的 `load()` 前提行。

这两处是"只因为来源不同"而不同的全部渲染内容（主干里其余 660 行两边完全一样）。
"""

from __future__ import annotations

from knowledge_virtuoso.functions.core.render import Profile


def _load_line(entry: dict) -> str | None:
    """二次开发函数的调用前提行。

    必须先 ``load()`` 才能调用——这个前提官方文档没有，只能从记录的
    ``origin_meta.custom.load`` 取；不给出来，LLM 就会写出对不上真实环境的调用。
    """
    if entry.get("origin") != "custom":
        return None
    meta = (entry.get("origin_meta") or {}).get("custom") or {}
    load = (meta.get("load") or "").strip()
    return ("状态: 自定义函数（二次开发）" + (f"，需先 {load} 才能调用" if load else ""))


PROFILE = Profile(digest_marks=("自定义",), status_line=_load_line)
