#!/usr/bin/env python3
"""二次开发来源：外部工具产出的、与官方同构的 v3 信封。

来源接口同 `official/__init__.py`。两处不同：

* ``rebuild()`` 恒为 ``None``——信封由二次开发工具（如 skill_dev_kit）自己产出，
  本来源没有从原始材料重建的能力，坏源只能跳过。
* ``REQUIRE_ENVELOPE = True``——契约要求 custom 与官方同构，非信封形态一律拒绝。
"""

from __future__ import annotations

from knowledge_virtuoso.functions.core.envelope import _read_index_entries
from knowledge_virtuoso.functions.sources.custom import catalog as custom_catalog
from knowledge_virtuoso.functions.sources.custom.render import PROFILE

NAME = "custom"
LABEL = "自定义"
REQUIRED = False
ORDER = 20
# 不写自己的索引（信封由二次开发工具产出），所以没有语料元数据。
CORPUS = None
REQUIRE_ENVELOPE = True


def index_paths() -> tuple[str, ...]:
    """环境变量 ``VIRTUOSO_CUSTOM_INDEX`` 里的索引文件（进程内首次调用时解析）。"""
    return custom_catalog.custom_index_paths()


def read(path: str) -> dict[str, dict]:
    return _read_index_entries(path, require_envelope=REQUIRE_ENVELOPE, label=LABEL)


def rebuild(doc_root: str | None) -> None:
    return None


def owns(entry: dict) -> bool:
    return entry.get("origin") == "custom"
