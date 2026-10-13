#!/usr/bin/env python3
"""重新采集 fixture（被测层的输入）。golden 用 `run_tests.py --update` 重录。

用法（在仓库根执行）:

  uv run python -B tests/capture_fixtures.py                  # 全部
  uv run python -B tests/capture_fixtures.py functions        # 只采函数库
  uv run python -B tests/capture_fixtures.py db techdb        # 只采属性库

函数库的记录取自**本机索引**（平台数据目录，`VIRTUOSO_DATA_DIR` 可覆盖），所以只在
"记录契约变了"或"要新增用例"时跑；跑完记得 `run_tests.py --update` 重录 golden 并核对差异。

手写的那几份**不在这里重录**（它们不是从索引来的，改了要自己动手）：
`functions/sources/custom/fixtures/synthetic.json`（手写信封）与
`database/techdb/fixtures/rw_shown.json`（手写行，文件里标了 `"synthetic": true`）。
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import MIRROR, read_json, write_text  # noqa: E402

from knowledge_virtuoso.functions import index as skill_language  # noqa: E402
from knowledge_virtuoso.database.db.core import catalog as db_cat  # noqa: E402
from knowledge_virtuoso.database.techdb.core import catalog as tech_cat  # noqa: E402
from knowledge_virtuoso.database.cdfdb.core import catalog as cdf_cat  # noqa: E402

ATTR_LIBS = {
    "db": (db_cat, "search_attr"),
    "techdb": (tech_cat, "search_tech_attr"),
    "cdfdb": (cdf_cat, "search_cdf_attr"),
}


def write_json(path, obj) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def capture_functions() -> None:
    fixtures = MIRROR / "functions" / "sources" / "official" / "fixtures"
    for fixture in sorted(fixtures.glob("*.json")):
        record = skill_language.query_function(fixture.stem)
        if record is None:
            print(f"跳过：索引里没有 {fixture.stem}")
            continue
        write_json(fixture, record)
    print(f"functions/sources/official: {len(list(fixtures.glob('*.json')))} 条记录")


def capture_attrs(library: str) -> None:
    module, func_name = ATTR_LIBS[library]
    fixtures = MIRROR / "database" / library / "fixtures"
    count = 0
    for fixture in sorted(fixtures.glob("*.json")):
        case = read_json(fixture)
        if case.get("synthetic"):
            continue                      # 手写行：官方索引里没有这种数据
        case["rows"] = getattr(module, func_name)(**case["params"])
        write_json(fixture, case)
        count += 1
    print(f"database/{library}: {count} 个用例")


def main() -> None:
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")] or ["functions", *ATTR_LIBS]
    if "functions" in wanted:
        capture_functions()
    for library in ATTR_LIBS:
        if library in wanted:
            capture_attrs(library)


if __name__ == "__main__":
    main()
