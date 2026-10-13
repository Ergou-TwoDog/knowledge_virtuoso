#!/usr/bin/env python3
"""记录契约的接受/拒绝表 + 派生字段（断言式：测"行为对不对"）。

这张表是 `core/SPEC.md` §2/§4 的可执行版本——**改契约时必须同步改这里**。
拒绝消息断言到完整字符串：格式变了（比如字段路径换了写法）这里会红。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.functions.core import contract  # noqa: E402

BASE = {"decl": [{"text": "f( t_in )"}], "where": {"file": "a.il"},
        "sections": {}, "field_status": {}, "status": "active"}


def outcome(record) -> str:
    """跑一遍契约：通过返回 `通过`，否则返回异常消息。"""
    try:
        contract._rebuild_runtime_indexes({"f": record})
        return "通过"
    except ValueError as exc:
        return str(exc)


# (用例, 记录, 期望)  —— 期望是 "通过" 或完整的拒绝消息
CASES = [
    ("最小合法记录", dict(BASE), "通过"),
    ("type 不校验（缺了也行）", {k: v for k, v in BASE.items()}, "通过"),
    ("缺 where.file（空串也算 str）", dict(BASE, where={}), "通过"),
    ("多带未知键 origin/origin_meta/lint", dict(BASE, origin="custom", lint=["x"]), "通过"),
    ("记录本身不是 dict", "not-a-record", "f must be dict"),
    ("decl 不是 list", dict(BASE, decl="f()"), "f.decl must be list"),
    ("decl 条目缺 text", dict(BASE, decl=[{}]), "f.decl item text must be str"),
    ("decl 为空 list（能过，但查不到——见 SPEC §4.1）", dict(BASE, decl=[]), "通过"),
    ("sections 不是 dict", dict(BASE, sections=[]), "f.sections must be dict"),
    ("节的 text 不是字符串", dict(BASE, sections={"description": {"text": 123}}),
     "f.sections.description.text must be str"),
    ("参数条目缺 desc", dict(BASE, sections={"arguments": {"root": {"items": [{"name": "a"}]}, "lists": []}}),
     "f.sections.arguments.root.items.desc must be str"),
    ("子列表缺 title", dict(BASE, sections={"arguments": {"root": {"items": []},
                                                        "lists": [{"items": []}]}}),
     "f.sections.arguments.lists.title must be str"),
    ("返回值条目缺 value", dict(BASE, sections={"returns": {"items": [{"desc": "x"}]}}),
     "f.sections.returns.items.value must be str"),
    ("返回值条目缺 desc", dict(BASE, sections={"returns": {"items": [{"value": "t_out"}]}}),
     "f.sections.returns.items.desc must be str"),
    ("返回值条目齐备", dict(BASE, sections={"returns": {"items": [{"value": "t_out", "desc": "输出"}]}}),
     "通过"),
    ("field_status 的值不是字符串", dict(BASE, field_status={"description": 1}),
     "f.field_status.description must be str"),
    ("status 不是字符串", dict(BASE, status=1), "f.status must be str"),
]

TOKEN_CASES = [
    ("dbCreateRect", ["db", "create", "rect"]),
    ("hiSetCursor", ["hi", "set", "cursor"]),
    ("absAbstract", ["abs", "abstract"]),
    ("pstddev", ["pstddev"]),          # 拆不出 ≥2 字的分词就整名一块
    ("RODCreatePath", ["rod", "create", "path"]),
]


def run(report: Report, update: bool = False) -> None:
    for label, record, expected in CASES:
        report.expect(f"契约/{label}", outcome(record), expected)

    for name, expected in TOKEN_CASES:
        report.expect(f"分词/{name}", contract._tokenize_name(name), expected)

    # 派生字段：文件里写什么都不作数，按函数名重算后覆盖。
    index, keywords, prefixes = contract._rebuild_runtime_indexes(
        {"dbCreateRect": dict(BASE, prefix="乱写", tokens=["乱", "写"])})
    report.expect("派生/prefix 被重算", index["dbCreateRect"]["prefix"], "db")
    report.expect("派生/tokens 被重算", index["dbCreateRect"]["tokens"], ["db", "create", "rect"])
    report.expect("派生/来源记录未被改动", "prefix" in BASE, False)

    # 三个返回结构：函数名 → 记录、分词 → 函数集、前缀 → 函数集。
    report.expect("结构/keywords 建对", sorted(keywords.get("create", ())), ["dbCreateRect"])
    report.expect("结构/prefixes 建对", sorted(prefixes.get("db", ())), ["dbCreateRect"])

    # 顶层：空记录集直接拒（不是逐条记录的错，所以走它自己的消息）。
    try:
        contract._rebuild_runtime_indexes({})
        report.truthy("顶层/空记录集被拒", False, "空 dict 应当被拒")
    except ValueError as exc:
        report.expect("顶层/空记录集被拒", str(exc), "function records must be a nonempty object")


if __name__ == "__main__":
    report = Report("functions/core/test_contract")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
