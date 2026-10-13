#!/usr/bin/env python3
"""v3 信封的读/写与路径规范化（断言式）。

只碰临时目录，不读本机索引、不需要 doc。锁四件事：往返一致、压缩与否都能读、
版本/形态不符时的拒绝、写入可复现（同内容同字节）。
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, read_text  # noqa: E402

from knowledge_virtuoso.functions.core import envelope  # noqa: E402

CORPUS = {"product": "test-product", "scope": "test-scope"}
RECORD = {"type": "function", "decl": [{"text": "f( t_in )"}], "where": {"file": "a.il"},
          "also_at": [], "sections": {"description": {"text": "说明"}},
          "field_status": {"description": "present"}, "status": "active"}


def rejection(func, *args, **kwargs) -> str:
    try:
        func(*args, **kwargs)
        return "通过"
    except ValueError as exc:
        return str(exc)


def run(report: Report, update: bool = False) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        entries = {"myFunc": RECORD}

        # ① 往返：写盘（gzip）→ 读回，记录逐字一致（派生键不落盘，所以不带）。
        written = tmp / "index.json"
        envelope._write_index(written, entries, CORPUS)
        report.truthy("往返/写出的确是 gzip", written.read_bytes()[:2] == b"\x1f\x8b",
                      "v3 索引应 gzip 落盘")
        report.expect("往返/读回一致", envelope._read_index_entries(written), entries)

        # ② 写入可复现：同样内容两次写出的字节完全相同（gzip mtime=0）。
        again = tmp / "again.json"
        envelope._write_index(again, entries, CORPUS)
        report.expect("写入/同内容同字节", again.read_bytes(), written.read_bytes())

        # ③ 语料元数据来自调用方（core 不认识任何来源）。
        blob = json.loads(gzip.decompress(written.read_bytes()).decode("utf-8"))
        report.expect("信封/corpus 用调用方给的", blob["corpus"], CORPUS)
        report.expect("信封/schema_version", blob["schema_version"], 3)
        report.expect("信封/派生键不落盘",
                      sorted(blob["functions"]["myFunc"]), sorted(RECORD))

        # ④ 明文 JSON 也能读（旧文件兼容）。
        plain = tmp / "plain.json"
        plain.write_text(json.dumps({"schema_version": 3, "corpus": {}, "functions": entries},
                                    ensure_ascii=False), encoding="utf-8")
        report.expect("读入/明文亦可", envelope._read_index_entries(plain), entries)

        # ⑤ 版本不符：拒，且消息报出两个版本号。
        bad = tmp / "bad.json"
        bad.write_text(json.dumps({"schema_version": 2, "functions": entries}), encoding="utf-8")
        report.expect("拒绝/版本不符", rejection(envelope._read_index_entries, bad),
                      "索引格式版本不兼容（文件为 2，当前需要 3）")

        # ⑥ 形态：扁平记录只在“不要求信封”时收；要求信封时拒绝消息带来源称呼。
        flat = tmp / "flat.json"
        flat.write_text(json.dumps({"myFunc": RECORD}, ensure_ascii=False), encoding="utf-8")
        report.expect("形态/不要求信封时收扁平记录",
                      envelope._read_index_entries(flat, require_envelope=False), entries)
        report.expect("形态/要求信封时拒扁平记录",
                      rejection(envelope._read_index_entries, flat, require_envelope=True,
                                label="自定义"),
                      "自定义索引必须是 v3 envelope（含 schema_version=3）")

        # ⑦ 路径规范化：只做词法处理（用于去重与“换源没有”的比较），不 stat 磁盘。
        report.expect("路径/相对转绝对", envelope._canonical_index_path("a/b.json"),
                      envelope._canonical_index_path(str(pathlib.Path.cwd() / "a/b.json")))
        report.expect("路径/折叠 ..（同一份文件）",
                      envelope._canonical_index_path("x/../a.json"),
                      envelope._canonical_index_path("a.json"))
        report.expect("路径/大小写归一（Windows）",
                      envelope._canonical_index_path("A.JSON"),
                      envelope._canonical_index_path("a.json"))


if __name__ == "__main__":
    report = Report("functions/core/test_envelope")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
