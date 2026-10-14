#!/usr/bin/env python3
"""官方解析器（断言式）：`sources/official/catalog.py` —— 输入是官方 doc 的**最小片段**。

夹具在 `fixtures/html/`：`topic/<函数>.html` 是一个 topic 的**正文**（两个标记之间），
`page/<函数>.html` 覆盖**整个标记区间**（含 `[TOPIC_START_OPEN]…[TOPIC_END]`）。每份片段
对应解析器的一个格式族，族的判别特征、代码位置与实测数量见 `tests/README.md`；出处与切法
由 `tests/capture_official_html.py` 写进 `fixtures/html/README.md`。

两类检查，分工不同：

1. **自足 + 口径**：片段**单独**喂进解析器，产出的 `decl`/`sections`/`field_status`/`status`
   必须与旁边那份 `.json`（线上索引里的记录）逐字段相同。夹具切得不全、或解析口径变了，
   这里就红。topic 片段走 `_extract_full_from_topic`，page 片段走 `build_entries`（顺带覆盖
   文件层：docset 白名单、标记协议）。
2. **族专项**：每族一条断言，写清"这族要是坏了会怎样"。它们锁的是**为什么**这么做，
   不随夹具重录而松动。

**不读本机索引、不需要 doc**：夹具就是输入。`page` 用例在临时目录里按 `where.file` 的原
路径放片段——文件层只认**目录名**（docset 白名单）与**文件名**，不需要真内容。
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_json  # noqa: E402

from knowledge_virtuoso.functions.sources.official import catalog  # noqa: E402

HTML = HERE / "fixtures" / "html"
# 与线上记录比这四个键；`where`/`also_at` 依赖文件层（page 用例里能复现，topic 用例里没有）。
COMPARED = ("decl", "sections", "field_status", "status")

TOPIC_TARGETS = ("hiSetCursor", "rodCreatePath", "error", "evalstring", "pcreCompile",
                 "gdmstatus", "absAbstract", "awvCreateBus", "asiMapInstanceName")
PAGE_TARGETS = ("ccpGetAutoRename", "caaar")


def text_of(kind: str, name: str) -> str:
    return (HTML / kind / f"{name}.html").read_text(encoding="utf-8")


def expected(kind: str, name: str) -> dict:
    return read_json(HTML / kind / f"{name}.json")


def parsed(name: str) -> dict:
    """topic 片段单独解析——不喂文件名、不喂索引，只有正文。"""
    return catalog._extract_full_from_topic(name, text_of("topic", name))


def built(name: str) -> tuple[dict, dict]:
    """把 page 片段按原路径放进临时 doc 根，走完整的文件层。"""
    record = expected("page", name)
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / record["where"]["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text_of("page", name), encoding="utf-8")
        return catalog.build_entries(tmp)


def run(report: Report, update: bool = False) -> None:
    # ── 1. 自足 + 口径 ──
    for name in TOPIC_TARGETS:
        got, want = parsed(name), expected("topic", name)
        for key in COMPARED:
            report.expect(f"topic/{name}:{key} 与线上记录一致", got[key], want[key])

    for name in PAGE_TARGETS:
        entries, _stats = built(name)
        got, want = entries.get(name), expected("page", name)
        report.truthy(f"page/{name} 片段能被收录", got is not None,
                      f"收到的是 {sorted(entries)}")
        for key in COMPARED:
            report.expect(f"page/{name}:{key} 与线上记录一致", got[key], want[key])

    # ── 2. A 文件 / topic 标记层 ──
    entries, stats = built("ccpGetAutoRename")
    report.expect("A2 一个标记含多个函数标题 → 按 <h3> 切成三个独立条目",
                  sorted(entries), ["ccpExpandConfig", "ccpGetAutoRename", "ccpSetAutoRename"])
    report.expect("A2 报表记的是切分后的 topic 数", stats["topics_considered"], 3)
    where = entries["ccpGetAutoRename"]["where"]
    report.expect("A2 where.topic 是切分后的函数名", where["topic"], "ccpGetAutoRename")
    report.truthy("A2 marker_text 仍是原标记文本（切分后两者不再相同）",
                  where["marker_text"] and where["marker_text"] != where["topic"],
                  f"marker_text={where['marker_text']!r}")

    entries, stats = built("caaar")
    report.expect("A3 名字在散文里列出 → 一个 topic 展开成 28 个函数",
                  (len(entries), stats["topics_considered"], stats["accepted_functions"]),
                  (28, 1, 28))
    caaar = entries["caaar"]
    report.expect("F5 无自带声明 → 取同 topic 的 <dl>，状态记 shared_declaration",
                  caaar["field_status"]["decl"], "shared_declaration")
    report.truthy("F5 decl.shared_from 记的是归属标记文本",
                  caaar["decl"][0]["shared_from"].startswith("caar, caaar,"),
                  caaar["decl"][0]["shared_from"][:40])

    # A1 标记协议：缺 `[TOPIC_END]` 的 topic 静默跳过（不能只收一半）。
    with tempfile.TemporaryDirectory() as tmp:
        record = expected("page", "caaar")
        target = pathlib.Path(tmp) / record["where"]["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text_of("page", "caaar").replace("<!-- [TOPIC_END] -->", ""),
                          encoding="utf-8")
        entries, stats = catalog.build_entries(tmp)
    report.expect("A1 缺 [TOPIC_END] 的 topic 被跳过（不产出半条记录）",
                  (dict(entries), stats.get("topics_considered", 0)), ({}, 0))

    # A5 文件层：docset 白名单只认**目录名**，白名单外一律不收。
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "notadocset" / "list.html"
        target.parent.mkdir(parents=True)
        target.write_text(text_of("page", "caaar"), encoding="utf-8")
        entries, stats = catalog.build_entries(tmp)
    report.expect("A5 不在 docset 白名单里的目录不收",
                  (dict(entries), stats.get("topics_considered", 0)), ({}, 0))

    # ── 3. B 标题与节名层 ──
    report.expect("B2 官方笔误标题「value returned\\」也认成返回值节",
                  parsed("asiMapInstanceName")["field_status"]["returns"], "present")
    report.expect("B3 Arguments<br>Values Returned 的后半算**独立节**（返回节只剩散文）",
                  parsed("error")["field_status"]["returns"], "text_fallback")
    rod = parsed("rodCreatePath")
    report.expect("B3 Arguments<br><br>Master Path Arguments 的后半算**节内子范围**",
                  (rod["sections"]["arguments"]["root"]["title"],
                   rod["field_status"]["arguments"]),
                  ("Master Path Arguments", "present"))
    report.expect("B4 节里明写 None → documented_none（不是 not_documented 也不是 unparsed）",
                  parsed("absAbstract")["field_status"]["arguments"], "documented_none")

    # ── 4. C 声明与表格行层 ──
    report.expect("C7 裸 <tr> 续排的整张大表都收进参数表（hiSetCursor 94 条）",
                  len(parsed("hiSetCursor")["sections"]["arguments"]["root"]["items"]), 94)
    report.expect("C9 允许取值表收成参数的 values、不额外产出参数条目（evalstring）",
                  ([a["name"] for a in parsed("evalstring")["sections"]["arguments"]["root"]["items"]],
                   [row["value"] for row in
                    parsed("evalstring")["sections"]["arguments"]["root"]["items"][1]["values"]]),
                  (["t_string", "s_langMode"], ["'ils", "'il"]))
    report.expect("C4 首列被占位的续排行按**名称行**收成条目（pcreCompile 的 PCRE_* 常量）",
                  [a["name"] for a in parsed("pcreCompile")["sections"]["arguments"]["root"]["items"]][:3],
                  ["t_pattern", "PCRE_CASELESS", "PCRE_MULTILINE"])
    gdm = {a["name"] for a in parsed("gdmstatus")["sections"]["arguments"]["root"]["items"]}
    report.truthy("C4 首列被占位时真参数没被丢（gdmstatus）",
                  {"G_gdmSpec", "q_gdmSpecList", "x_information"} <= gdm, sorted(gdm)[:8])
    lists = rod["sections"]["arguments"]["lists"]
    report.expect("C10 四个子参数列表都按类型名连回根参数（大小写不敏感也算命中）",
                  [(group["list_type"], group["parent"]["match"]) for group in lists],
                  [("rodConnectivityArgs", "exact"), ("l_offsetSubpathArgs", "exact"),
                   ("l_encSubpathArgs", "case_insensitive"), ("l_subrectArgs", "case_insensitive")])
    report.expect("C10 子列表的条目都挂在根参数上（parent.arg 指向根条目）",
                  [group["parent"]["arg"] for group in lists],
                  ["rodConnectivityArgs...", "l_offsetSubpathArgs...",
                   "l_encSubPathArgs...", "l_subRectArgs..."])
    report.truthy("C2 ROD 的超长声明完整保留（没被截断）",
                  len(rod["decl"][0]["text"]) > 300, str(len(rod["decl"][0]["text"])))

    # ── 5. D 返回节层 ──
    report.truthy("D2 返回值里没有 ROD 的编号步骤（1. 2. …）",
                  all(not re.fullmatch(r"\d+\.", row["value"])
                      for row in rod["sections"]["returns"]["items"]),
                  [row["value"] for row in rod["sections"]["returns"]["items"]])
    error = parsed("error")
    report.expect("D3 返回节只有散文：条目不产出、原文照录、状态 text_fallback",
                  (error["sections"]["returns"]["items"],
                   error["field_status"]["returns"],
                   len(error["sections"]["returns"]["text"]) > 0),
                  ([], "text_fallback", True))

    # ── 6. E 其他节 ──
    awv = parsed("awvCreateBus")
    report.expect("E3 description 缺失、只有 definition（两节各留各的，取舍在渲染层）",
                  ("description" in awv["sections"], "definition" in awv["sections"]),
                  (False, True))
    report.truthy("E4 option_descriptions 是独立节且很长（2 万字级，所以它进 full 档）",
                  len(parsed("absAbstract")["sections"]["option_descriptions"]["text"]) > 20000,
                  str(len(parsed("absAbstract")["sections"]["option_descriptions"]["text"])))

    # ── 7. 夹具本身没被换掉 / 删掉 ──
    on_disk = sorted(p.stem for p in (HTML / "topic").glob("*.html"))
    report.expect("夹具/topic 片段齐全（少一份就少一族的覆盖）", on_disk, sorted(TOPIC_TARGETS))
    on_disk = sorted(p.stem for p in (HTML / "page").glob("*.html"))
    report.expect("夹具/page 片段齐全", on_disk, sorted(PAGE_TARGETS))
    for name in TOPIC_TARGETS + PAGE_TARGETS:
        kind = "topic" if name in TOPIC_TARGETS else "page"
        report.truthy(f"夹具/{kind}/{name} 有配套的 .json 期望值",
                      (HTML / kind / f"{name}.json").is_file(), "期望值缺失")


if __name__ == "__main__":
    report = Report("functions/sources/official/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
