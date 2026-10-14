#!/usr/bin/env python3
"""官方来源（Cadence IC618 文档里可调用的 SKILL 函数）。

**来源接口**——`registry` 只认这几样，加一个来源不必改 `core/`：

  NAME / LABEL        来源名与警告文案里的称呼
  REQUIRED            索引不可用时是"报错"（基准来源）还是"跳过并警告"
  index_paths()       该来源的索引文件（可多个；顺序即合并优先级）
  read(path)          读一份索引 → 记录字典
  rebuild(doc_root)   从原始材料重建 → (记录, 报告)；没有这种能力的来源返回 None
  owns(entry)         这条记录是否属于本来源
  PROFILE             渲染差异（见 render.py）

可选（不在上面那 10 项里，缺了照常工作）：`print_report(entries, report)` —— 构建报表的
口径（前缀/动词分布是官方解析自己的知识）。开发入口的 `--report` 有就调，没有就原样打
报告字典。这里显式 re-export：开发入口只认 `registry.BASE` 这一个名字，不认 `catalog`。
"""

from __future__ import annotations

from knowledge_virtuoso.functions.core.envelope import _read_index_entries
from knowledge_virtuoso.functions.sources.official import catalog
from knowledge_virtuoso.functions.sources.official.catalog import print_report  # noqa: F401
from knowledge_virtuoso.functions.sources.official.render import PROFILE  # noqa: F401

NAME = "official"
LABEL = "官方"
REQUIRED = True
ORDER = 10
# 写自己索引时的信封元数据（语料是谁）。
CORPUS = {"product": "Cadence IC618", "scope": "official-skill-callables"}
# 官方索引兼容更早的扁平记录；契约只对 custom 源强制要求信封形态。
REQUIRE_ENVELOPE = False


def index_paths() -> tuple[str, ...]:
    """官方索引文件（只有一个）。统一成字符串：来源之间用路径元组比较是否换过源。"""
    return (str(catalog.INDEX_PATH),)


def read(path: str) -> dict[str, dict]:
    return _read_index_entries(path, require_envelope=REQUIRE_ENVELOPE, label=LABEL)


def rebuild(doc_root: str | None) -> tuple[dict[str, dict], dict]:
    """从 IC618 doc 重建官方索引（解析 + 校验前的记录，原 _candidate_entries）。"""
    return catalog.build_entries(doc_root)


def owns(entry: dict) -> bool:
    """官方条目没有 ``origin`` 键（约定见 functions/README.md §2）。

    作为**兜底**：没有被别的来源认领的记录都算官方的。
    """
    return True
