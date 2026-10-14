#!/usr/bin/env python3
"""采集官方 doc 的 **HTML 片段**当解析器夹具（手动跑，需要本机 doc）。

```bash
VIRTUOSO_DOC_DIR=<IC618 doc 根> uv run python -B tests/capture_official_html.py
```

切两种颗粒度，都只留"判别特征 + 够解析的上下文"：

  fixtures/html/topic/<函数>.html   一个 topic 的**正文**（两个标记之间）
                                     → 喂 `_extract_full_from_topic(name, body)`
  fixtures/html/page/<函数>.html    覆盖该函数的**整个标记区间**（含
                                     `[TOPIC_START_OPEN]…[TOPIC_END]`）
                                     → 喂 `_iter_topics()` / `build_entries()`

选哪些函数、为什么选它，写在 `TEST_TARGETS` 里（一族一份）；每次跑都会重写
`fixtures/html/README.md` 的清单，出处与切法因此不会和文件对不上。

跑完请用 `git diff --stat tests/knowledge_virtuoso/functions/sources/official/fixtures/html/`
看一眼体积有没有异常膨胀。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent      # tests/tools
TESTS = HERE.parent                                  # tests/
REPO = TESTS.parent                                  # 仓库根
sys.path.insert(0, str(TESTS))

from common import write_text  # noqa: E402

from knowledge_virtuoso.functions import index  # noqa: E402
from knowledge_virtuoso.functions.sources.official import catalog as official  # noqa: E402

FIXTURES = TESTS / "knowledge_virtuoso" / "functions" / "sources" / "official" / "fixtures" / "html"

# (颗粒度, 函数名, 覆盖的格式族)。族的名目与实测数量见 tests/README.md。
TEST_TARGETS = (
    ("topic", "hiSetCursor", "C7 裸 <tr> 续排的大表（全库独一份）"),
    ("topic", "rodCreatePath", "B3 节内子范围标题 + C2 超长声明 + C10 子参数列表 + D2 编号步骤表"),
    ("topic", "error", "B3 合并标题（Arguments<br>Values Returned）+ D3 返回节只有散文"),
    ("topic", "evalstring", "C9 允许取值表（'symbol 行）"),
    ("topic", "pcreCompile", "C4 首列被占位的续排行（名称一行、说明下一行）"),
    ("topic", "gdmstatus", "C4/C5 首列被占位 + 名称与说明同格"),
    ("topic", "absAbstract", "B4 documented_none + E4 option_descriptions 大字典"),
    ("topic", "awvCreateBus", "E3 description 缺失、只有 definition"),
    ("topic", "asiMapInstanceName", "B2 官方笔误标题 value returned\\"),
    ("page", "ccpGetAutoRename", "A1 标记协议 + A2 一个标记含多个函数标题"),
    ("page", "caaar", "A3 名字在散文里列出 + F5 共享声明（取同 topic 的 <dl>）"),
)


def _topic_body(text: str, name: str) -> tuple[str, str]:
    """返回 (topic 正文, 覆盖该函数的标记区间原文)。

    一个标记可能含多个函数（A2）：这时标记区间是整块，正文也是整块——由测试决定用
    `_iter_topics` 还是直接喂正文。
    """
    for start in official._TOPIC_START_RE.finditer(text):
        end = official._TOPIC_END_RE.search(text, start.end())
        if not end:
            continue
        region = text[start.start():end.end()]
        names: list[str] = []
        for attrs, topic in official._iter_topics(region):
            names += official._topic_names(attrs, topic)
        if name in names:
            return text[start.end():end.start()], region
    raise SystemExit(f"{name}: 在源文件里找不到对应的 topic 标记")


def main() -> None:
    parser = argparse.ArgumentParser(description="采集官方 doc 的 HTML 片段当解析器夹具")
    parser.add_argument("--doc-root", default=os.environ.get("VIRTUOSO_DOC_DIR"))
    args = parser.parse_args()
    if not args.doc_root or not os.path.isdir(args.doc_root):
        parser.error("需要 --doc-root（或 VIRTUOSO_DOC_DIR）指向 IC618 doc 根")
    doc_root = pathlib.Path(args.doc_root)

    rows: list[str] = []
    total = 0
    for kind, name, covers in TEST_TARGETS:
        info = index.query_function(name)
        if info is None:
            raise SystemExit(f"{name}: 本机索引里没有（先建索引）")
        rel = info["where"]["file"]
        text = (doc_root / rel).read_text(encoding="utf-8", errors="ignore")
        body, region = _topic_body(text, name)
        content = body if kind == "topic" else region
        # 全仓 LF：夹具要能与 golden/比对共存，行尾不能被 checkout 改掉。
        content = content.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        path = FIXTURES / kind / f"{name}.html"
        write_text(path, content)
        # 期望值 = 线上索引里的那条记录（与 test_render 的 fixture 同一来源、同一写法）：
        # 片段单独喂解析器，产出的 decl/sections/field_status/status 必须与之逐字段相同。
        write_text(FIXTURES / kind / f"{name}.json",
                   json.dumps(info, ensure_ascii=False, indent=1) + "\n")
        size = len(content.encode("utf-8"))
        total += size
        rows.append(f"| `{kind}/{name}.html` + `.json` | {size / 1024:.1f} KB | `{rel}` | {covers} |")
        print(f"{path.relative_to(REPO)}  {size} 字节  ← {rel}")

    write_text(FIXTURES / "README.md", "\n".join([
        "# 官方 doc 的 HTML 片段（解析器夹具）",
        "",
        "由 `tests/capture_official_html.py` 从本机官方 doc 切出，**只留判别特征 + 够解析的",
        "上下文**：`topic/` 是一个 topic 的正文（两个标记之间），`page/` 覆盖整个标记区间。",
        "每份片段对应解析器的一个格式族（族的清单见 `tests/README.md`「片段夹具覆盖的格式族」）。",
        "",
        "每份 `.html` 旁边有一份同名 `.json`，是**线上索引里的那条记录**（写法与",
        "`capture_fixtures.py` 一致）：片段单独喂解析器，产出的 `decl`/`sections`/",
        "`field_status`/`status` 必须与之逐字段相同——夹具自足与解析口径两条一起管。",
        "",
        "| 片段 | 体积 | 源文件（doc 根下） | 覆盖的格式族 |",
        "|---|---|---|---|",
        *rows,
        f"| **合计** | **{total / 1024:.1f} KB** | | |",
        "",
        "**这是 Cadence 官方文档的原文摘录**：进公开仓库前请确认符合其许可；要缩小暴露就",
        "减少族、或在切法上再删上下文（改 `TEST_TARGETS` 与切法，重跑采集脚本即可）。",
        "",
    ]) + "\n")
    print(f"\n合计 {total / 1024:.1f} KB；清单写入 fixtures/html/README.md")


if __name__ == "__main__":
    main()
