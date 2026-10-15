#!/usr/bin/env python3
"""属性库共用的**装配**：`database/core/assembly.py`（`Library`）。

**与 src 一一对应**——本文件在 `database/core/` 下，对着同级的 `assembly.py`。

"一份声明装出来的是什么"四库都一样，所以这一份要锁住：

- **载荷**：② 之后打上版本与 `lib`（类型区分字段），顶层键集固定，**校验覆盖最终形状**；
- **入口**：`search` / `describe` 就是**共用那一个**（`(object, keyword)` / `(object)`），
  别名与跨对象口径取声明里那两份；
- **索引存取**：`build` / `load` 转给 `Store`（恢复语义锁在 `core/test_store.py`）；
- **CLI**：`main` 打"落点 + lib/版本 + 对象数 + 记录数"，外加各库自己的 `summary`。

用**桩**（假的 parse / decorate / check）测装配本身——不读真文档、不碰真索引。
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, write_text  # noqa: E402

from knowledge_virtuoso.database.core.assembly import Library  # noqa: E402
from knowledge_virtuoso.database.core.objects import PAYLOAD_KEYS, record  # noqa: E402


def _obj(oid: str, names=("a",)) -> dict:
    return {"id": oid, "title": oid, "runtime": None, "section": None, "desc": None,
            "parent": None, "attrs": [record(n, kind="attr") for n in names]}


def _make(library_doc: pathlib.Path, **kw) -> Library:
    """一个指向临时目录的 `Library`；`parse`/`decorate` 都是桩。"""
    def parse(doc_path):
        return {"桩": str(doc_path)}

    def decorate(raw):
        return {"objects": {"x": _obj("x"), "y": _obj("y", ("b",))}}

    return Library(name="stub", version=7, doc_parts=("sub", "doc.html"),
                   parse=parse, decorate=decorate, **kw)


def run(report: Report, update: bool = False) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        doc = root / "sub" / "doc.html"
        write_text(doc, "<html>桩</html>")

        # ── 载荷：② 之后打版本与 lib，校验覆盖最终形状 ──
        lib = _make(doc)
        payload = lib.payload({"任何": "raw"})
        report.expect("载荷/顶层键集固定（version / lib / objects），顺序即落盘顺序",
                      tuple(payload), PAYLOAD_KEYS)
        report.expect("载荷/带上了本库的名字与版本（`lib` 就是类型区分字段）",
                      (payload["lib"], payload["version"]), ("stub", 7))
        report.expect("载荷/对象来自 ②", sorted(payload["objects"]), ["x", "y"])
        report.expect("载荷/索引落在以库名命名的目录下（`index_path(name)`）",
                      pathlib.Path(lib.store.index_path).parent.name, "stub")

        # 本库自己的校验在共用的那道门之后跑：它抛就抛
        def _angry(objects):
            raise ValueError("本库说不行")

        try:
            _make(doc, check=_angry).payload({})
            report.truthy("载荷/本库自己的校验会被调用", False, "没有抛错")
        except ValueError as exc:
            report.truthy("载荷/本库自己的校验会被调用", "本库说不行" in str(exc), str(exc))

        # 共用的那道门先响：`lib` 对不上时轮不到本库的校验
        order = []

        def _spy(objects):
            order.append("check")

        bad = _make(doc, check=_spy)
        try:
            bad.validate({"version": 7, "lib": "别的库", "objects": {"x": _obj("x")}})
            report.truthy("载荷/顶层与库名对不上时先炸", False, "没有抛错")
        except ValueError as exc:
            report.truthy("载荷/顶层与库名对不上时先炸（在调用本库的校验之前）",
                          "lib=" in str(exc) and order == [], f"{exc} / order={order}")

        # ── 入口不在这：`Library` 只管装配（查询入口归 `core/query.py` 的 `Query`）──
        lib = _make(doc)
        report.expect("装配/**不提供查询入口**（入口归查询那一层，见 `core/test_query.py`）",
                      [hasattr(lib, "search"), hasattr(lib, "describe")], [False, False])

        # ── CLI：落点 + lib/版本 + 两个计数（外加本库的 summary）──
        out = root / "out" / "index.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            _make(doc, summary=lambda objects: [f"本库多说一句：{len(objects)}"]).main(
                ["--doc", str(doc), "--output", str(out)])
        text = stdout.getvalue()
        report.expect("CLI/写到了 --output，且内容是那份载荷",
                      json.loads(out.read_text(encoding="utf-8"))["lib"], "stub")
        report.truthy("CLI/打印落点、lib/版本、对象数与记录数",
                      all(s in text for s in (str(out), "stub v7", "对象:      2 个",
                                              "记录:      2 条")), text)
        report.truthy("CLI/本库的 summary 也被打出来", "本库多说一句：2" in text, text)


if __name__ == "__main__":
    report = Report("database/core/test_assembly")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
