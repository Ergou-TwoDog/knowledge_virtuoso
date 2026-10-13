#!/usr/bin/env python3
"""官方来源的渲染差异。

官方条目**没有**额外标记，头部也不需要状态行——所以这里只是显式声明"本来源不额外
加东西"，好让 `registry` 按同一个接缝取配置：渲染主干不认识"官方"这个词。
"""

from __future__ import annotations

from knowledge_virtuoso.functions.core.render import DEFAULT_PROFILE

PROFILE = DEFAULT_PROFILE
