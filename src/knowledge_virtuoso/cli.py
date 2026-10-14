"""knowledge-virtuoso-build：从 IC618 官方 doc 显式重建各库索引。

属性库的子命令由 `database/core/registry.py` 按发现的库生成——**加一个属性库不必改这里**。
函数库的索引结构与属性库不同（信封 + 来源合并），仍单独一条路。
"""

from __future__ import annotations

import argparse
import os

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import registry as attr_registry


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="knowledge-virtuoso-build", description="从 IC618 官方 doc 重建索引"
    )
    sub = parser.add_subparsers(dest="target", required=True)
    for name in ("functions", *attr_registry.names()):
        p = sub.add_parser(name, help=f"重建 {name} 索引")
        p.add_argument(
            "--doc",
            default=None,
            help="官方 doc 路径；functions 取 doc 根，属性库取对应 html（默认取 VIRTUOSO_DOC_DIR）",
        )
        p.add_argument("--output", default=None, help="输出路径（默认写入平台索引目录）")
    if "libs" not in attr_registry.names():       # 目录名撞了就别加，免得 argparse 报重复
        sub.add_parser("libs", help="列出发现到的属性库（不看索引、不读 doc）")

    args = parser.parse_args(argv)

    if args.target == "libs":
        print(attr_registry.check())
        return

    if args.target == "functions":
        from knowledge_virtuoso.functions.index import build_index_file

        doc_root = args.doc or os.environ.get("VIRTUOSO_DOC_DIR")
        if not doc_root:
            parser.error("未指定 --doc，且未设置 VIRTUOSO_DOC_DIR")
        out = args.output or str(index_path("functions"))
        count = build_index_file(doc_root, out)
        print(f"已写入 {count} 个函数到 {out}")
        return

    lib = attr_registry.get(args.target)
    payload = lib.build(args.doc)
    out = args.output or str(index_path(args.target))
    atomic_write_json(out, payload)
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
