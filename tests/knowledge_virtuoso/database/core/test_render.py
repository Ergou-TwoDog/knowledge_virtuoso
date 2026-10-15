#!/usr/bin/env python3
"""属性库共用的表格渲染：`database/core/render.py`。

四个库的渲染器现在只是**一份列声明**，表格本体在这里，所以它自己的行为要单独钉住——
各库的 `test_render.py` 只覆盖"我这份声明长什么样"（那些是逐字节 golden），
覆盖不到列机制本身：隐藏整列、截断、列表拼接、最后一列的分隔线宽度、提示文案。

不读索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.database.core.render import (Column, RenderSpec,  # noqa: E402
                                                     render_attrs, render_table)

_COLS = (
    Column("a", "a", 3),
    Column("b", "b", 3, hide_if_null=True),   # 整列都是 None（= 没有这一项）就不占列
    Column("c", "c", 0, join=",", sep=4),     # 列表值拼接；最后一列的分隔线宽 4
)


def _render(rows, **kw):
    kw.setdefault("subject", "zz")
    kw.setdefault("selector_label", "类")
    kw.setdefault("all_label", "全部类")
    return render_table(rows, _COLS, **kw)


def run(report: Report, update: bool = False) -> None:
    # ── 表格：表头补齐、分隔线（最后一列用该列自己的 sep）、行按列宽对齐 ──
    report.expect("表格/整列都是 None（没有这一项）的列不占列，其余按列宽对齐",
                  _render([{"a": "x", "b": None, "c": ["p", "q"]}]),
                  "\n".join(["匹配 1 个zz:", "  a   c", "  --- ----", "  x   p,q"]))
    report.expect("表格/只要有一行不是 None，该列就露出来",
                  _render([{"a": "x", "b": None, "c": ["p"]}, {"a": "y", "b": "s", "c": ["q"]}])
                  .splitlines()[1], "  a   b   c")
    report.expect("表格/键缺失与 None 一样看待（少了键不该被读成有值）",
                  _render([{"a": "x", "c": ["p"]}, {"a": "y", "b": None, "c": ["q"]}])
                  .splitlines()[1], "  a   c")

    # ── 单元格：截断（超长才截，末尾给 `…`）、列表拼接、None 当空串 ──
    def _one_col(rows, **col_kw):
        col = (Column("t", "t", 0, **col_kw),)
        return render_table(rows, col, subject="", selector_label="类", all_label="全部类")

    # 最后一列的分隔线用该列自己的 `sep`（默认 30），**不是列宽**
    report.expect("单元格/超长截断到该宽度并加 `…`",
                  _one_col([{"t": "abcdefgh"}], truncate=5),
                  "匹配 1 个:\n  t\n  " + "-" * 30 + "\n  abcd…")
    report.expect("单元格/没超长就不动它",
                  _one_col([{"t": "abcde"}], truncate=5).splitlines()[-1], "  abcde")
    report.expect("单元格/None 当空串、列表按 join 拼（右侧补齐的空格不算）",
                  _render([{"a": "x", "c": None}]).splitlines()[-1].rstrip(), "  x")

    # ── 提示：给了选择器就把选择器与关键词写进去，没给就说"全部…" ──
    report.expect("提示/带选择器与关键词",
                  _render([], selector="layers", keyword="valid"),
                  "未找到匹配 类='layers' keyword='valid' 的zz。")
    report.expect("提示/只给选择器",
                  _render([], selector="layers"), "未找到匹配 类='layers' 的zz。")
    report.expect("提示/都不给",
                  _render([]), "未找到匹配 全部类 的zz。")

    # ── 标题：`subject` 连中英交界那个空格一起写（db 是"属性"、另三家是" tech 属性"）──
    report.expect("标题/subject 原样拼在「个」后面",
                  _render([{"a": "x", "c": ["p"]}], subject=" tech 属性").splitlines()[0],
                  "匹配 1 个 tech 属性:")
    report.expect("标题/note 跟在 subject 之后（dd 用它说明「原文没给类型与说明」）",
                  _render([{"a": "x", "c": ["p"]}], note="（原文未给）").splitlines()[0],
                  "匹配 1 个zz（原文未给）:")

    # ── 对象头：只在"解析到了"时印一行，把"这次问的是谁"回显出来 ──
    _SPEC = RenderSpec(columns=_COLS, subject="zz", selector_label="类", all_label="全部类",
                       header_fields=(("title", "title"), ("runtime", "runtime"),
                                      ("section", "section")))
    rows = [{"a": "x", "c": ["p"]}]
    plain = render_attrs(rows, _SPEC, selector="rect")
    report.expect("对象头/没给 obj（没解析到，或跨对象查询）就不印，输出与不带对象头一致",
                  render_attrs(rows, _SPEC, selector="rect", obj=None), plain)
    report.expect("对象头/给了 obj 就在最前面加一行，其余逐字不动",
                  render_attrs(rows, _SPEC, selector="rect",
                               obj={"id": "Rectangle", "title": "Rectangle Attributes",
                                    "runtime": None, "section": "Attributes of Shapes"}),
                  "对象 Rectangle  title=Rectangle Attributes  section=Attributes of Shapes\n" + plain)
    report.expect("对象头/原文没给的项（null / 空串）整项略去，连标签都不印",
                  render_attrs(rows, _SPEC, obj={"id": "Marker", "title": "", "runtime": None,
                                                 "section": None}).splitlines()[0],
                  "对象 Marker")
    report.expect("对象头/值超长截到 80 字加 `…`（它是回声，不是数据本身）",
                  render_attrs(rows, _SPEC, obj={"id": "x", "title": "t" * 200}).splitlines()[0],
                  "对象 x  title=" + "t" * 79 + "…")
    report.expect("对象头/解析到了但筛完没匹配**也印**（「认出来了」与「没认出来」要分得开）",
                  render_attrs([], _SPEC, selector="rect", keyword="zz",
                               obj={"id": "Rectangle", "title": "Rectangle Attributes"}
                               ).splitlines(),
                  ["对象 Rectangle  title=Rectangle Attributes",
                   "未找到匹配 类='rect' keyword='zz' 的zz。"])
    report.expect("对象头/声明里没有 header_fields 的库（dd），那行就只有 `对象 <id>`",
                  render_attrs(rows, RenderSpec(columns=_COLS, subject="zz", selector_label="类",
                                                all_label="全部类"),
                               obj={"id": "lib"}),
                  "对象 lib\n" + plain)


if __name__ == "__main__":
    report = Report("database/core/test_render")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
