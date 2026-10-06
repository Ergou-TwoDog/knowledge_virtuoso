"""knowledge-virtuoso-build：从 IC618 官方 doc 显式重建各库索引。"""

from __future__ import annotations

import argparse
import importlib
import os

from knowledge_virtuoso._paths import atomic_write_json, index_path

_ATTR_MODULES = {
    "db": "knowledge_virtuoso.database.db.core.catalog",
    "techdb": "knowledge_virtuoso.database.techdb.core.catalog",
    "cdfdb": "knowledge_virtuoso.database.cdfdb.core.catalog",
}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="knowledge-virtuoso-build", description="从 IC618 官方 doc 重建索引"
    )
    sub = parser.add_subparsers(dest="target", required=True)
    for name in ("functions", "db", "techdb", "cdfdb"):
        p = sub.add_parser(name, help=f"重建 {name} 索引")
        p.add_argument(
            "--doc",
            default=None,
            help="官方 doc 路径；functions 取 doc 根，属性库取对应 html（默认取 VIRTUOSO_DOC_DIR）",
        )
        p.add_argument("--output", default=None, help="输出路径（默认写入平台索引目录）")
    args = parser.parse_args(argv)

    if args.target == "functions":
        from knowledge_virtuoso.functions.core.catalog import build_index_file

        doc_root = args.doc or os.environ.get("VIRTUOSO_DOC_DIR")
        if not doc_root:
            parser.error("未指定 --doc，且未设置 VIRTUOSO_DOC_DIR")
        out = args.output or str(index_path("functions"))
        count = build_index_file(doc_root, out)
        print(f"已写入 {count} 个函数到 {out}")
        return

    catalog = importlib.import_module(_ATTR_MODULES[args.target])
    payload = catalog.build_from_html(args.doc)
    out = args.output or str(index_path(args.target))
    atomic_write_json(out, payload)
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
