#!/usr/bin/env python3
"""测试公共件：定位、读写、逐字节比对、断言与报告。

只用标准库。文本一律 UTF-8 + LF 落盘（`.gitattributes` 里 `* text=auto eol=lf`——
行尾被 checkout 改掉会让 golden 全红）。

测试分两种，报告都能收：

* **golden 比对**（`report.check`）——测"输出**变没变**"：录一份期望文本，逐字节比。
* **断言**（`report.expect` / `report.truthy`）——测"行为**对不对**"：直接判返回值、
  异常、副作用。契约、信封、装配这类"对错"用断言，渲染输出用 golden。
"""

from __future__ import annotations

import json
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parent
REPO = TESTS.parent

# 与 src/knowledge_virtuoso 同构的测试树；每个 `test_*.py` 挨着它测的数据。
MIRROR = TESTS / "knowledge_virtuoso"

# 控制台编码兜底：Windows 默认 cp936 打不出 ✓/✗ 一类符号，报告本身别把检查搞崩。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_bytes(path) -> bytes:
    return pathlib.Path(path).read_bytes()


def read_text(path) -> str:
    return read_bytes(path).decode("utf-8")


def write_text(path, text: str) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def read_json(path):
    return json.loads(read_text(path))


def first_difference(want: str, got: str) -> str:
    """第一处差异的行号与上下文——逐字节比对失败时，直接能定位到行。"""
    want_lines, got_lines = want.split("\n"), got.split("\n")
    for index, (a, b) in enumerate(zip(want_lines, got_lines)):
        if a != b:
            return (f"第 {index + 1} 行不同\n        期望: {a[:160]}\n        实际: {b[:160]}")
    return f"行数不同：期望 {len(want_lines)} 行，实际 {len(got_lines)} 行"


class Report:
    """一个测试模块的一次运行：比了多少 golden、断言了多少条、哪些没过。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.checked = 0          # golden 逐字节比对
        self.asserted = 0         # 断言
        self.updated = 0          # 重录的 golden
        self.failures: list[str] = []

    # ── golden 比对 ────────────────────────────────────────────────
    def check(self, case: str, got: str, golden_path, update: bool = False) -> None:
        """与 golden 逐字节比；``update`` 时改写 golden。"""
        golden_path = pathlib.Path(golden_path)
        if update:
            write_text(golden_path, got)
            self.updated += 1
            return
        self.checked += 1
        if not golden_path.exists():
            self.failures.append(f"{case}: 缺 golden（{golden_path}）")
            return
        want = read_text(golden_path)
        if want != got:
            self.failures.append(f"{case}: {first_difference(want, got)}")

    # ── 断言 ───────────────────────────────────────────────────────
    def expect(self, case: str, actual, expected) -> None:
        self.asserted += 1
        if actual != expected:
            self.failures.append(f"{case}: 期望 {expected!r}，实际 {actual!r}")

    def truthy(self, case: str, condition, detail: str = "") -> None:
        """条件为假即失败；``detail`` 写清"为什么该为真"，失败时才有用。"""
        self.asserted += 1
        if not condition:
            self.failures.append(f"{case}: 断言不成立" + (f"（{detail}）" if detail else ""))

    # ── 汇总 ───────────────────────────────────────────────────────
    def merge(self, other: "Report") -> None:
        self.checked += other.checked
        self.asserted += other.asserted
        self.updated += other.updated
        self.failures += other.failures

    def summary(self) -> str:
        if self.updated:
            return f"{self.name}: 更新 {self.updated} 份 golden"
        mark = "✓" if not self.failures else "✗"
        parts = []
        if self.checked:
            parts.append(f"{self.checked} 份 golden 一致")
        if self.asserted:
            parts.append(f"{self.asserted} 条断言通过")
        if not parts:
            parts.append("没有检查项")
        return f"{mark} {self.name}: " + "、".join(parts)


def run_attr_cases(here: pathlib.Path, renderer, report: "Report", update: bool = False) -> None:
    """属性库的公共跑法：fixture = {params, rows}，逐条喂本库的渲染函数。

    三个属性库的用例形状相同，差别只在渲染函数与列格式，所以骨架放这里，
    各库的 test_render.py 只报"用哪个渲染函数"。
    """
    for fixture in sorted((here / "fixtures").glob("*.json")):
        case = read_json(fixture)
        got = renderer(case["rows"], **case["params"])
        report.check(fixture.stem, got, here / "golden" / f"{fixture.stem}.txt", update)
