#!/usr/bin/env python3
"""函数库的开发入口：不经 MCP 查一个函数，或从 doc 生成索引。

  uv run python -m knowledge_virtuoso.functions dbCreateRect
  uv run python -m knowledge_virtuoso.functions ergUtilGetListMax -d skel   # 五档同 MCP
  uv run python -m knowledge_virtuoso.functions --sources      # 看发现到哪些来源
  uv run python -m knowledge_virtuoso.functions --doc-root <doc> --report
  uv run python -m knowledge_virtuoso.functions --doc-root <doc> --export <names.txt>
  uv run python -m knowledge_virtuoso.functions --doc-root <doc> --export-json <file>

正式重建请用 `knowledge-virtuoso-build`（见 README「显式重建」）；这里只是本地排障
用的小工具，所以放在 `functions/` 这一层：它同时要用到来源接口与索引层的查询。

**查询走与 MCP 同一个渲染入口**（`core/render.render_entry`）：排障时看到的形状就是 LLM
看到的形状——含来源标记与 `load()` 前提行。另写一套简化输出会失去"用 CLI 复现 LLM 所见"
这唯一的价值，所以哪怕多几行参数也不自己拼字符串。

**重建只走来源接口**：谁是基准来源、怎么解析，都由来源自己答（`registry.BASE`）；本文件
不认识"官方"这个名字——加一棵带解析能力的来源树，构建与查询两个入口跟着就能用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from knowledge_virtuoso.functions import index, registry
from knowledge_virtuoso.functions.core import render

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 构建用法的旗标。**只看第一个参数**判断走哪条路：比 `startswith("--")` 稳——查询侧
# 也有自己的旗标（-d/--detail、-s/--sections），前缀判断会把它们误当成构建参数。
_BUILD_FLAGS = ("--doc-root", "--export", "--export-json", "--report")


def _sources_cli() -> None:
    """把自动发现的结果打出来：自动发现把"一眼看得见"换成了"遍历目录"，这里补回来。"""
    print(f"发现 {len(registry.SOURCES)} 个来源（ORDER 大者覆盖小者）：")
    for source in registry.SOURCES:
        role = "基准" if source.REQUIRED else "可选"
        paths = source.index_paths()
        corpus = (source.CORPUS or {}).get("product", "—")
        print(f"  [{source.ORDER:>3}] {source.NAME:<9} {source.LABEL:<4} {role}"
              f"  语料: {corpus}")
        print(f"        索引: {' | '.join(paths) if paths else '（无）'}")


def _query_cli(argv: list[str]) -> None:
    """查一个函数；输出与 MCP 的 `skill_language_search_doc` 逐字一致。"""
    parser = argparse.ArgumentParser(
        prog="python -m knowledge_virtuoso.functions",
        description="不经 MCP 查一个函数（输出与 MCP 的 search_doc 逐字一致）")
    parser.add_argument("func_name", help="完整函数名；未命中会给出相近名")
    parser.add_argument("doc_root", nargs="?", default=None,
                        help="官方 doc 根；只在索引不可用、需要现场重建时用到")
    parser.add_argument("-d", "--detail", default="brief", choices=render.DETAILS,
                        help="返回粒度，同 MCP（默认 brief）")
    parser.add_argument("-s", "--sections", nargs="*", default=None, metavar="SECTION",
                        help="额外索取的节名，同 MCP 的 sections 参数")
    args = parser.parse_args(argv)

    info = index.query_function(args.func_name, args.doc_root)
    if info is None:
        print(render.render_not_found(args.func_name, index.suggest_names(args.func_name)))
        raise SystemExit(1)
    print(render.render_entry(info, args.detail, args.sections,
                              profile=registry.profile_for(info)))


def _build_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="从 IC618 HTML 文档提取 SKILL 可调用函数索引")
    parser.add_argument("--doc-root", default=os.environ.get("VIRTUOSO_DOC_DIR"))
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--export-json", metavar="FILE")
    parser.add_argument("--report", action="store_true", help="输出构建覆盖统计")
    args = parser.parse_args(argv)
    if not args.doc_root or not os.path.isdir(args.doc_root):
        parser.error(f"文档目录无效: {args.doc_root}")
    if args.export_json:
        count = index.build_index_file(args.doc_root, args.export_json)
        print(f"已导出 {count} 个官方 SKILL 可调用函数到 {args.export_json}")
        if args.report:
            print(json.dumps(index.last_report(), ensure_ascii=False, indent=2))
        return
    entries, report = registry.BASE.rebuild(args.doc_root)
    index.set_last_report(report)
    if args.export:
        Path(args.export).write_text("\n".join(entries) + "\n", encoding="utf-8")
        print(f"已导出 {len(entries)} 个函数名到 {args.export}")
        if args.report:            # 与 --export-json 一致：--report 说了就打，不再静默忽略
            _print_report(entries)
        return
    _print_report(entries)


def _print_report(entries: dict) -> None:
    """构建覆盖统计：来源提供了 `print_report` 就用它，没有就原样打报告字典。

    这是**可选**扩展点（不在来源接口的 10 项里）：报表口径（前缀/动词分布）是各来源自己
    的解析知识，装配与开发入口都不该知道，所以只"有就调"。
    """
    printer = getattr(registry.BASE, "print_report", None)
    if printer is None:
        print(json.dumps(index.last_report(), ensure_ascii=False, indent=2))
        return
    printer(entries, index.last_report())


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--sources"]:
        _sources_cli()
    elif argv[:1] and argv[0] in _BUILD_FLAGS:
        _build_cli(argv)
    else:
        _query_cli(argv)


if __name__ == "__main__":
    main()
