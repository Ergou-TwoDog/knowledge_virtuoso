#!/usr/bin/env python3
"""装配与查询（断言式）：`index.py` 的合并规则、内存索引与查询/搜索/建议。

**不读本机索引**：装配用桩来源喂 `_optional_plan` / `_publish_merged` / `build_index_file`，
查询则先发布一份 3 条记录的微型语料。测试期间会动模块级内存索引，**跑完恢复原状**
（`run_tests.py` 在同一进程里依次跑所有模块）。
"""

from __future__ import annotations

import contextlib
import gzip
import io
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report  # noqa: E402

from knowledge_virtuoso.functions import index, registry  # noqa: E402
from knowledge_virtuoso.functions.core import contract  # noqa: E402
from knowledge_virtuoso.functions.core.envelope import _canonical_index_path  # noqa: E402


def record(file: str, text: str = "f( t_in )") -> dict:
    return {"type": "function", "decl": [{"text": text, "shared_from": None}],
            "where": {"file": file, "topic": "f", "marker_text": "f", "anchor": "f"},
            "also_at": [], "sections": {"description": {"text": "说明 " + file}},
            "field_status": {"description": "present"}, "status": "active"}


class StubSource:
    """最小来源：只实现装配会用到的那几样。"""

    def __init__(self, label: str, paths, entries=None, error: Exception | None = None):
        self.NAME = self.LABEL = label
        self.REQUIRED = False
        self.ORDER = 0
        self.CORPUS = {"product": "stub"}
        self.PROFILE = None
        self._paths = tuple(paths)
        self._entries = entries or {}
        self._error = error

    def index_paths(self):
        return self._paths

    def read(self, path):
        if self._error is not None:
            raise self._error
        return dict(self._entries)

    def rebuild(self, doc_root):
        return dict(self._entries), {}

    def owns(self, entry):
        return False


@contextlib.contextmanager
def stub_sources(base, optional):
    saved = (registry.BASE, registry.OPTIONAL)
    registry.BASE, registry.OPTIONAL = base, tuple(optional)
    try:
        yield
    finally:
        registry.BASE, registry.OPTIONAL = saved


@contextlib.contextmanager
def tiny_index(entries: dict):
    """把一份微型语料当成"当前索引"，用完恢复。

    **必须连 registry 一起换成桩**：查询入口内部会触发 `_build_index()`，若基准来源还是
    官方，它会把本机索引（或报错）盖到这份语料上——那样这个测试就不密闭了，换台没有
    索引的机器就会红。桩来源只从内存返回这份语料，不碰磁盘。
    """
    base = StubSource("stub", ["stub.json"], entries)
    with stub_sources(base, ()):
        with index._index_lock:
            saved = (index._index, index._keyword_index, index._prefix_index, index._index_sources,
                     index._index_lengths, index._index_built)
            index._publish(contract._rebuild_runtime_indexes(entries), ("stub.json",), {})
        try:
            yield
        finally:
            with index._index_lock:
                (index._index, index._keyword_index, index._prefix_index, index._index_sources,
                 index._index_lengths, index._index_built) = saved


def run(report: Report, update: bool = False) -> None:
    # ── 装配计划：同一份文件不当两个来源；顺序 = 来源顺序 × 路径顺序 ──
    # 基准路径故意写成相对形式：计划里必须把它规范化后再比，否则去重会静默失灵。
    with stub_sources(StubSource("base", ["base.json"]),
                      [StubSource("one", ["a.json", "base.json"]), StubSource("two", ["b.json"])]):
        plan = [path for _source, path in index._optional_plan(("base.json",))]
    report.expect("计划/排除与基准重合的路径（按规范化后比较）+ 保持来源与路径顺序",
                  plan, [_canonical_index_path("a.json"), _canonical_index_path("b.json")])

    # ── 合并：可选来源覆盖基准，遮蔽出声；坏源跳过、不拖垮别人 ──
    base = StubSource("base", ["base.json"], {"dup": record("base.il"), "onlyBase": record("base.il")})
    good = StubSource("one", ["a.json"], {"dup": record("a.il"), "onlyA": record("a.il")})
    broken = StubSource("two", ["b.json"], error=FileNotFoundError("nope"))
    empty = StubSource("three", ["c.json"], {})
    stderr = io.StringIO()
    with stub_sources(base, (good, broken, empty)):
        plan = index._optional_plan(("base.json",))
        with index._index_lock, contextlib.redirect_stderr(stderr):
            index._publish_merged({"dup": record("base.il"), "onlyBase": record("base.il")},
                                  ("base.json", "a.json", "b.json", "c.json"), plan)
            merged = dict(index._index)
            report.expect("合并/可选来源覆盖基准", merged["dup"]["where"]["file"], "a.il")
            report.expect("合并/两边各自独有的都在",
                          ("onlyBase" in merged, "onlyA" in merged), (True, True))
            report.truthy("合并/没被坏源拖垮", "b.json" not in index._index_sources[:1] and merged,
                          "坏源只应跳过自己")
            report.expect("合并/发布的来源是计划而非成功集合",
                          index._index_sources, ("base.json", "a.json", "b.json", "c.json"))
    log = stderr.getvalue()
    report.truthy("合并/遮蔽有警告", "覆盖同名函数 dup" in log, "同名覆盖必须留痕")
    report.truthy("合并/坏源有警告", "索引跳过" in log and "FileNotFoundError" in log,
                  "坏源跳过要出声")
    report.truthy("合并/空源有警告", "索引为空" in log, "空源要出声")

    # ── 健康检查：源集合变了就不算健康（决定要不要重新装配） ──
    with stub_sources(StubSource("base", ["base.json"], {"x": record("x.il")}), ()):
        with contextlib.redirect_stderr(io.StringIO()):
            with index._index_lock:
                index._publish_merged({"x": record("x.il")}, ("base.json",), ())
        report.expect("健康/刚发布过", index._memory_healthy(("base.json",)), True)
        report.expect("健康/源集合变了", index._memory_healthy(("other.json",)), False)

    # ── 查询：发布 3 条记录的微型语料 ──
    corpus = {"dbCreateRect": record("skdfref/chap2.html", "dbCreateRect( d_cv )"),
              "rodCreateRect": record("rodskillref/x.html", "rodCreateRect( d_cv )"),
              "hiSetCursor": record("skuiref/y.html", "hiSetCursor( t_cursor )")}
    with tiny_index(corpus):
        got = index.query_function("dbCreateRect")
        report.expect("查询/命中并补 name", (got["name"], got["where"]["file"]),
                      ("dbCreateRect", "skdfref/chap2.html"))
        report.expect("查询/未命中给 None", index.query_function("nope"), None)
        got["where"]["file"] = "改了"          # 返回值是深拷贝：改它不该动内存索引
        report.expect("查询/深拷贝", index._index["dbCreateRect"]["where"]["file"],
                      "skdfref/chap2.html")
        fetched = index.entries(["hiSetCursor", "nope"])
        # entries() 给的是**原始记录**（`name` 是 query_function 才补的扩展键）。
        report.expect("entries/与输入同序且未知名给空",
                      (fetched[0]["where"]["file"], fetched[1]), ("skuiref/y.html", {}))

        page = index.search_page("db", "create rect", 0, 30)
        report.expect("搜索/前缀+关键词", (page["total"], page["names"]), (1, ["dbCreateRect"]))
        page = index.search_page("", "create", 0, 1)
        report.expect("搜索/分页 total、本页数与 next_offset",
                      (page["total"], len(page["names"]), page["next_offset"]), (2, 1, 1))
        report.expect("搜索/驼峰与无边界写法都能命中",
                      (index.search_page("db", "createRect", 0, 30)["names"],
                       index.search_page("db", "createrect", 0, 30)["names"]),
                      (["dbCreateRect"], ["dbCreateRect"]))
        report.expect("搜索/by_components 就是 names",
                      index.search_by_components("rod", "create", 0, 30), ["rodCreateRect"])

        hints = index.suggest_names("dbCreatRect")
        report.truthy("建议/给相近名且首位最像", hints and hints[0] == "dbCreateRect", f"实际 {hints}")
        report.expect("建议/限前缀内", index.suggest_names("dbCreatRect", prefix="rod"),
                      ["rodCreateRect"])
        try:
            index.search_page("", "", -1, 30)
            report.truthy("搜索/负 offset 被拒", False, "负 offset 应抛 ValueError")
        except ValueError as exc:
            report.expect("搜索/负 offset 被拒", str(exc),
                          "offset must be a nonnegative integer; limit must be 1..500")

    # ── 构建：从（桩）原始材料产出索引文件，落盘 + 发布 ──
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "index.json"
        base = StubSource("base", ["base.json"], {"myFunc": record("my.il")})
        with stub_sources(base, ()):
            count = index.build_index_file("ignored-doc-root", out)
        report.expect("构建/返回条数", count, 1)
        report.truthy("构建/落盘且是 gzip", out.read_bytes()[:2] == b"\x1f\x8b", "应 gzip 落盘")
        blob = json.loads(gzip.decompress(out.read_bytes()).decode("utf-8"))
        report.expect("构建/信封里的语料来自基准来源", blob["corpus"], {"product": "stub"})
        report.expect("构建/记录不含派生键", sorted(blob["functions"]["myFunc"]),
                      sorted(record("my.il")))


if __name__ == "__main__":
    report = Report("functions/test_index")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
