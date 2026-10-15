#!/usr/bin/env python3
"""属性库共用的索引存取（断言式）：`database/core/store.py`。

三个属性库的 `_load`/`_rebuild`/`build_from_html` 曾是三份逐字复制，收敛到这里之后，
**恢复语义只此一处**——所以这一份要锁住：缓存、坏索引从 doc 重建并原子写回、没有
doc 时报什么错、默认文档怎么定位、关键词过滤与排序。**不碰真索引**：索引路径与来源
文档都指向临时目录，`VIRTUOSO_DOC_DIR` 用完还原。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, write_text  # noqa: E402

from knowledge_virtuoso.database.core import store  # noqa: E402


@contextlib.contextmanager
def env(**values):
    """临时改环境变量（`load`/`build` 的 doc 根从环境取），用完逐个还原。"""
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update({key: value for key, value in values.items() if value is not None})
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def make_store(root: pathlib.Path, parsed=None, error: Exception | None = None):
    """一个指向临时目录的 Store；`parse` 是桩，记下被调用时的路径。"""
    calls: list[str] = []
    parsed = {"attributes": {}, "classes": {}} if parsed is None else parsed

    def parse(doc_path: str) -> dict:
        calls.append(doc_path)
        if error is not None:
            raise error
        return dict(parsed)

    instance = store.Store(index_path=root / "lib" / "index.json", label="lib_attr",
                           lib="lib", doc_parts=("sub", "doc.html"), parse=parse)
    return instance, calls


def run(report: Report, update: bool = False) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        index = root / "lib" / "index.json"

        # ── 读：有索引就照读，且进程内只读一次 ──
        write_text(index, json.dumps({"lib": "lib", "attributes": {"a": {"name": "a"}},
                                      "classes": {}}))
        instance, calls = make_store(root)
        first = instance.load()
        report.expect("读/直接读 JSON", first["attributes"]["a"]["name"], "a")
        report.expect("读/没走重建", calls, [])
        write_text(index, json.dumps({"lib": "lib", "attributes": {"b": {"name": "b"}},
                                      "classes": {}}))
        report.expect("读/第二次命中的是进程内缓存（不再读盘）",
                      instance.load()["attributes"]["a"]["name"], "a")

        # ── 是**别人的**索引：版本对也不算数（`lib` 是类型区分字段）──
        write_text(index, json.dumps({"lib": "别人", "attributes": {"c": {"name": "c"}},
                                      "classes": {}}))
        instance, _calls = make_store(root)
        with env(VIRTUOSO_DOC_DIR=None):
            try:
                instance.load()
            except RuntimeError as exc:
                message = str(exc)
            else:
                message = "(没拿它当好的用)"
        report.truthy("读/lib 与库名不符 → 不当好的用（报错里点出两边各是谁）",
                      "lib='别人'" in message and "'lib'" in message, message[:160])

        # ── 坏索引 + 有 doc：从 doc 重建、原子写回、警告出声 ──
        doc = root / "sub" / "doc.html"
        write_text(doc, "<html>桩</html>")
        write_text(index, "{ 这不是 JSON")
        instance, calls = make_store(root, parsed={"attributes": {"z": {"name": "z"}}, "classes": {}})
        stderr = io.StringIO()
        with env(VIRTUOSO_DOC_DIR=str(root)), contextlib.redirect_stderr(stderr):
            rebuilt = instance.load()
        report.expect("坏索引/重建用的是默认来源文档", calls, [str(doc)])
        report.expect("坏索引/返回重建结果", sorted(rebuilt["attributes"]), ["z"])
        report.expect("坏索引/写回后索引可读",
                      sorted(json.loads(index.read_text(encoding="utf-8"))["attributes"]), ["z"])
        report.truthy("坏索引/警告里带来源称呼与索引路径",
                      "lib_attr" in stderr.getvalue() and "index.json" in stderr.getvalue(),
                      stderr.getvalue()[:120])

        # ── 坏索引 + 没有 doc 根：报错要给出路（称呼、子命令、索引路径）──
        write_text(index, "{ 还是坏")
        instance, _calls = make_store(root)
        with env(VIRTUOSO_DOC_DIR=None):
            try:
                instance.load()
            except RuntimeError as exc:
                message = str(exc)
            else:
                message = "(没报错)"
        report.truthy("无 doc/报 RuntimeError 并给出路",
                      "lib_attr 索引不可用" in message and "knowledge-virtuoso-build lib" in message
                      and "index.json" in message,
                      message[:160])

        # ── 坏索引 + doc 根指向不存在的文件：说清是文档没有，不是"无法重建" ──
        instance, _calls = make_store(root)
        with env(VIRTUOSO_DOC_DIR=str(root / "nope")), contextlib.redirect_stderr(io.StringIO()):
            try:
                instance.load()
            except FileNotFoundError as exc:
                message = str(exc)
            else:
                message = "(没报错)"
        report.truthy("无文档/报 FileNotFoundError 指出路径", "文档不存在" in message, message[:160])

        # ── build：显式给路径 / 缺省取环境 / 缺环境时给出路 ──
        instance, calls = make_store(root, parsed={"attributes": {"q": {}}, "classes": {}})
        report.expect("build/显式路径", sorted(instance.build(str(doc))["attributes"]), ["q"])
        report.expect("build/解析收到的是给的路径", calls, [str(doc)])
        with env(VIRTUOSO_DOC_DIR=str(root)):
            instance.build()
        report.expect("build/缺省路径 = doc 根 + 默认子路径", calls[-1], str(doc))
        with env(VIRTUOSO_DOC_DIR=None):
            try:
                instance.build()
            except FileNotFoundError as exc:
                message = str(exc)
            else:
                message = "(没报错)"
        report.truthy("build/没设 doc 根时报错并给出路",
                      "VIRTUOSO_DOC_DIR 未设置" in message
                      and "knowledge-virtuoso-build lib" in message, message[:160])

        # ── 载荷包装：解析结果 → 落盘形状（属性库各有各的包装）──
        wrapped, _calls = make_store(root, parsed={"raw": 1})
        wrapped.payload = lambda parsed: {"wrapped": parsed["raw"]}
        report.expect("载荷/包装在解析之后、落盘之前",
                      wrapped.build(str(doc)), {"wrapped": 1})

    # ── 行选择：三库共用这一段 ──
    attrs = {"bBox": {"rw": "ro"}, "netName": {"rw": "rw"}, "Boxy": {"rw": "ro"}}
    seen: list[tuple] = []

    def row(name, info):
        seen.append((name, info))
        return {"name": name, "rw": info.get("rw", "?")}

    report.expect("行/空关键词 = 全取且按名字排序",
                  [r["name"] for r in store.query_rows(attrs, set(attrs), "", row)],
                  ["Boxy", "bBox", "netName"])
    report.expect("行/关键词是子串且不区分大小写",
                  [r["name"] for r in store.query_rows(attrs, set(attrs), "box", row)],
                  ["Boxy", "bBox"])
    report.expect("行/只留空白的词等于不过滤",
                  [r["name"] for r in store.query_rows(attrs, set(attrs), "   ", row)],
                  ["Boxy", "bBox", "netName"])
    report.expect("行/名字在载荷里没有记录时跳过",
                  [r["name"] for r in store.query_rows(attrs, {"bBox", "缺的"}, "", row)],
                  ["bBox"])
    report.expect("行/行工厂收到 (名, 记录) 两项", seen[0], ("Boxy", {"rw": "ro"}))


if __name__ == "__main__":
    report = Report("database/core/test_store")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
