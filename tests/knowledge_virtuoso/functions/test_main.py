#!/usr/bin/env python3
"""开发入口（断言式）：`functions/__main__.py`。

锁的是**"CLI 与 MCP 同源"**：查询走同一个渲染入口（`core/render.render_entry`），输出逐字
一致。改这个模块之前，它自己拼了一套简化输出——排障时看到的形状与 LLM 看到的不同（连
`（自定义）` 标记与 `load()` 前提行都没有），在这里锁死。

**不读本机索引**：查询入口整个换成桩（`suggest_names` 内部会触发 `_build_index()`，必须一起
换）；构建则把基准来源换成桩，验"重建只走来源接口"——桩没有官方解析器也能跑通。
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.functions import __main__ as dev_cli  # noqa: E402
from knowledge_virtuoso.functions import index, registry  # noqa: E402
from knowledge_virtuoso.functions.core import render  # noqa: E402


def record(name: str, origin: str | None = None) -> dict:
    entry = {"type": "function",
             "decl": [{"text": f"{name}( t_in ) => t_out", "shared_from": None}],
             "where": {"file": "src/my/func.il", "topic": name,
                       "marker_text": name, "anchor": name},
             "also_at": [],
             "sections": {
                 "description": {"text": "把 t_in 处理掉。"},
                 "arguments": {"root": {"title": None, "items": [
                     {"name": "t_in", "desc": "输入。", "values": None}]},
                     "lists": [], "text": "t_in\n输入。"},
                 "returns": {"items": [{"value": "t_out", "desc": "结果。"}],
                             "text": "t_out\n结果。"}},
             "field_status": {}, "status": "active"}
    if origin:
        entry["origin"] = origin
        entry["origin_meta"] = {origin: {"load": 'load("src/my/func.il")'}}
    return entry


@contextlib.contextmanager
def stub_query(info, hints=()):
    """查询入口与相近名建议一起换桩（后者内部会触发 `_build_index()`，不换就不密闭）。"""
    saved = (index.query_function, index.suggest_names)
    index.query_function = lambda name, doc_root=None: info
    index.suggest_names = lambda name, limit=5, prefix="": list(hints)
    try:
        yield
    finally:
        index.query_function, index.suggest_names = saved


class StubBase:
    """最小基准来源：只实现开发入口会用到的那几样。``printer`` 为假时不提供报告打印。"""

    NAME = "stub"
    REQUIRED = True
    ORDER = 0

    def __init__(self, entries: dict, report_payload: dict, printer: bool = True):
        self._entries, self._payload = entries, report_payload
        self.seen: tuple | None = None
        if printer:
            self.print_report = self._print_report

    def rebuild(self, doc_root):
        return dict(self._entries), dict(self._payload)

    def _print_report(self, entries, report_payload):
        self.seen = (entries, report_payload)


@contextlib.contextmanager
def stub_base(source):
    saved = registry.BASE
    saved_report = index.last_report()
    registry.BASE = source
    try:
        yield source
    finally:
        registry.BASE = saved
        index.set_last_report(saved_report)


def run_cli(argv: list[str]) -> tuple[str, object, str]:
    """跑一次开发入口 → (stdout, SystemExit 的 code 或 None, stderr)。"""
    out, err, code = io.StringIO(), io.StringIO(), None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            dev_cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    return out.getvalue(), code, err.getvalue()


def run(report: Report, update: bool = False) -> None:
    # ── 查询：与 MCP 同一入口，逐字一致（含档位与 sections 透传）──
    info = {**record("myProjectFunc"), "name": "myProjectFunc"}
    for detail, sections in (("brief", []), ("skel", []), ("digest", []), ("full", ["example"])):
        argv = ["myProjectFunc", "-d", detail] + (["-s", *sections] if sections else [])
        with stub_query(info):
            got, code, _err = run_cli(argv)
        want = render.render_entry(info, detail, sections or None,
                                   profile=registry.profile_for(info))
        report.expect(f"查询/{detail} 与 MCP 渲染逐字一致", got.rstrip("\n"), want)
        report.expect(f"查询/{detail} 正常退出", code, None)
    with stub_query(info):
        got, code, _err = run_cli(["myProjectFunc"])          # 不给 -d
    report.expect("查询/默认档位是 brief", got.rstrip("\n"),
                  render.render_entry(info, "brief", None, profile=registry.profile_for(info)))

    # 自定义来源：标记与前提行必须经由 profile 分派出现（CLI 侧不再自己拼字符串）。
    custom = {**record("ergDemo", origin="custom"), "name": "ergDemo"}
    with stub_query(custom):
        got_digest, _code, _err = run_cli(["ergDemo", "-d", "digest"])
        got_brief, _code, _err = run_cli(["ergDemo"])
    report.truthy("查询/自定义来源 digest 带来源标记", "（自定义）" in got_digest,
                  "profile.digest_marks 没被用上")
    report.truthy("查询/自定义来源 brief 带 load() 前提行", 'load("src/my/func.il")' in got_brief,
                  "profile.status_line 没被用上")

    # ── 未命中：退出码 1 + 相近名（与 MCP 同一句文案）──
    with stub_query(None, hints=["myProjectFunc"]):
        got, code, _err = run_cli(["myProjFunc"])
    report.expect("未命中/退出码", code, 1)
    report.expect("未命中/文案与 MCP 一致", got.rstrip("\n"),
                  render.render_not_found("myProjFunc", ["myProjectFunc"]))

    # ── 分派：构建旗标在最前才是构建；查询侧的 -d/-s 不能被误判 ──
    _out, code, err = run_cli(["--doc-root", str(HERE / "does-not-exist"), "--export", "x.txt"])
    report.truthy("分派/--doc-root 在最前走构建", "文档目录无效" in err, err.strip()[:120])
    report.expect("分派/无效 doc 退出码", code, 2)
    with stub_query(info):
        _out, code, err = run_cli(["myProjectFunc", "-d", "skel"])
    report.expect("分派/查询侧的 -d 不被当成构建", (code, err), (None, ""))

    # ── --sources：只扫目录，逐来源列出索引路径与角色 ──
    got, code, _err = run_cli(["--sources"])
    report.expect("--sources/正常退出", code, None)
    report.expect("--sources/每个来源一行索引", got.count("        索引:"), len(registry.SOURCES))
    report.truthy("--sources/标出基准与可选", "基准" in got and "可选" in got, got[:200])

    # ── 构建：重建走来源接口（桩没有官方解析器也要能跑），报告转交来源自己的 print_report ──
    entries = {"myProjectFunc": record("myProjectFunc")}
    with tempfile.TemporaryDirectory() as tmp:
        names = pathlib.Path(tmp) / "names.txt"
        with stub_base(StubBase(entries, {"分类统计": 7})) as stub:
            got, code, _err = run_cli(["--doc-root", tmp, "--export", str(names)])
            report.expect("构建/--export 退出码", code, None)
            report.expect("构建/--export 写出函数名（一行一个）",
                          names.read_text(encoding="utf-8"), "myProjectFunc\n")
            report.truthy("构建/--export 提示里报出条数", "已导出 1 个函数名" in got, got.strip()[:120])
            report.expect("构建/--export 没给 --report 就不打报告", stub.seen, None)

        with stub_base(StubBase(entries, {"分类统计": 7})) as stub:
            got, code, _err = run_cli(["--doc-root", tmp, "--export", str(names), "--report"])
            report.expect("构建/--export --report 退出码", code, None)
            report.truthy("构建/--export --report 把统计交给来源",
                          stub.seen == (entries, {"分类统计": 7}), f"实际 {stub.seen!r}")

        with stub_base(StubBase(entries, {"分类统计": 7})) as stub:
            got, code, _err = run_cli(["--doc-root", tmp, "--report"])
            report.truthy("构建/--report 把记录与统计一起交给来源", stub.seen == (entries, {"分类统计": 7}),
                          f"实际 {stub.seen!r}")
            report.expect("构建/--report 后统计进了 last_report", index.last_report(), {"分类统计": 7})

    # 没有 print_report 的来源：退化为原样打报告字典（不因缺少可选扩展点而报错）。
    with stub_base(StubBase(entries, {"分类统计": 7}, printer=False)):
        got, code, _err = run_cli(["--doc-root", tempfile.gettempdir(), "--report"])
    report.expect("构建/无 print_report 也正常退出", code, None)
    report.truthy("构建/无 print_report 时原样打字典", '"分类统计": 7' in got, got.strip()[:120])

    # ── 真来源的报告口径：`--report` 最终调到官方来源的 `semantic_analysis`/`print_report`。
    #    这一支曾因搬移时漏掉 `_PREFIX_RE` 而 NameError——只在这条路上才暴露，所以在这里
    #    用**真**官方函数跑一遍（桩测不出这一类"搬丢了名字"）。──
    from knowledge_virtuoso.functions.sources.official import catalog as official

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        official.print_report({"dbCreateRect": {"where": {"file": "skdfref/chap2.html"}}},
                              {"解析失败": 0})
    text = out.getvalue()
    report.truthy("报告/官方前缀统计可用（不是 NameError）",
                  "前缀 Top 30" in text and "db" in text, text.strip()[:120])

    # 重建路径（`build_entries` → `_iter_topics`）**没有直接测试**：要官方 doc 才跑得动
    # （见 tests/README「覆盖不到什么」）。而搬移时最容易出事的正是模块级名字：`_NAME_RE`
    # 与 `_PREFIX_RE` 随契约去了 `core/contract.py`，引用却留在这里——直到真跑一次重建才
    # NameError。这里做**名字级**兜底挡住这一类；解析正确性仍以真机重建比对为准。
    missing = [name for name in ("_NAME_RE", "_PREFIX_RE") if not hasattr(official, name)]
    report.expect("重建/解析用到的模块级名字都在（搬移丢名字的兜底）", missing, [])


if __name__ == "__main__":
    report = Report("functions/test_main")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
