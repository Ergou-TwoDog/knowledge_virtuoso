#!/usr/bin/env python3
"""函数库的开发入口：不经 MCP 查一个函数，或从官方 doc 生成索引。

  uv run python -m knowledge_virtuoso.functions dbCreateRect
  uv run python -m knowledge_virtuoso.functions --sources      # 看发现到哪些来源
  uv run python -m knowledge_virtuoso.functions --doc-root <doc> --report
  uv run python -m knowledge_virtuoso.functions --doc-root <doc> --export-json <file>

正式重建请用 `knowledge-virtuoso-build`（见 README「显式重建」）；这里只是本地排障
用的小工具，所以放在 `functions/` 这一层：它同时要用到官方来源的解析与索引层的查询。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from knowledge_virtuoso.functions import index
from knowledge_virtuoso.functions.sources.official import catalog as official

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _sources_cli() -> None:
    """把自动发现的结果打出来：自动发现把"一眼看得见"换成了"遍历目录"，这里补回来。"""
    from knowledge_virtuoso.functions import registry

    print(f"发现 {len(registry.SOURCES)} 个来源（ORDER 大者覆盖小者）：")
    for source in registry.SOURCES:
        role = "基准" if source.REQUIRED else "可选"
        paths = source.index_paths()
        corpus = (source.CORPUS or {}).get("product", "—")
        print(f"  [{source.ORDER:>3}] {source.NAME:<9} {source.LABEL:<4} {role}"
              f"  语料: {corpus}")
        print(f"        索引: {' | '.join(paths) if paths else '（无）'}")


def _build_cli() -> None:
    parser = argparse.ArgumentParser(description="从 IC618 HTML 文档提取官方 SKILL 可调用函数索引")
    parser.add_argument("--doc-root", default=os.environ.get("VIRTUOSO_DOC_DIR"))
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--export-json", metavar="FILE")
    parser.add_argument("--report", action="store_true", help="输出构建覆盖统计")
    args = parser.parse_args()
    if not args.doc_root or not os.path.isdir(args.doc_root):
        parser.error(f"文档目录无效: {args.doc_root}")
    if args.export_json:
        count = index.build_index_file(args.doc_root, args.export_json)
        print(f"已导出 {count} 个官方 SKILL 可调用函数到 {args.export_json}")
        if args.report:
            print(json.dumps(index.last_report(), ensure_ascii=False, indent=2))
        return
    entries, report = official.build_entries(args.doc_root)
    if args.export:
        Path(args.export).write_text("\n".join(entries) + "\n", encoding="utf-8")
        print(f"已导出 {len(entries)} 个函数名到 {args.export}")
        return
    index.set_last_report(report)
    official.print_report({name: entry["where"]["file"] for name, entry in entries.items()},
                          official.semantic_analysis(entries), index.last_report())


def _query_cli() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m knowledge_virtuoso.functions <function_name> [doc_root]",
              file=sys.stderr)
        raise SystemExit(1)
    info = index.query_function(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    if info is None:
        print(f"未找到函数: {sys.argv[1]}")
        raise SystemExit(1)
    where = info.get("where", {})
    print(f"函数: {info['name']}\n签名: {info['decl'][0]['text']}\n来源: {where.get('file', '')}")
    sections = info.get("sections", {})
    description = sections.get("description", {}).get("text", "")
    if description:
        print(f"\n描述: {description}")
    arguments = sections.get("arguments", {})
    if arguments:
        print("\n参数:")
        for item in arguments.get("root", {}).get("items", []):
            print(f"  {item['name']} — {item['desc']}")
        for group in arguments.get("lists", []):
            print(f"  [{group['title']}]")
            for item in group.get("items", []):
                print(f"    {item['name']} — {item['desc']}")
    returns = sections.get("returns", {}).get("items", [])
    if returns:
        print("\n返回:")
        for item in returns:
            print(f"  {item['value']} — {item['desc']}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--sources":
        _sources_cli()
    elif len(sys.argv) >= 2 and sys.argv[1].startswith("--"):
        _build_cli()
    else:
        _query_cli()
