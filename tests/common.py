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


def store_of(lib):
    """库模块 → 它的 **`Store`**（索引存取那一份：`LIB.store`）。

    库接口故意不暴露"索引在哪、怎么重建"（那是内部实现），但测试要往里注入手写载荷。
    顺着 `LIB` 走，测试里就不必再记一张"哪个库的索引在哪个文件"的表。
    """
    return lib.LIB.store


def payload_problem(library, payload) -> str:
    """手写载荷过一遍**构建期校验**；通过给 `""`，不通过给原因（拿去当断言的实际值）。

    手写载荷本来就可能缺键、写错归属（`lib` 与它所在的库对不上）——让它在这一道过一遍，
    fixtures 才算数。
    """
    try:
        library.validate(payload)
        return ""
    except ValueError as exc:
        return str(exc)


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
        self.skipped = 0          # 环境不具备、没真跑的检查（不算过也不算错）
        self.skips: list[str] = []
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

    # ── 跳过 ───────────────────────────────────────────────────────
    def skip(self, case: str, reason: str) -> None:
        """这条检查**没能真跑**（环境不具备，如本机没索引）——单独计数并在汇总里露面。

        不写进 `failures`：环境问题不是回归。也不能当作通过记数：那会把"没验到"读成"验过了"。
        """
        self.skipped += 1
        self.skips.append(f"{case}：{reason}")

    # ── 汇总 ───────────────────────────────────────────────────────
    def merge(self, other: "Report") -> None:
        self.checked += other.checked
        self.asserted += other.asserted
        self.updated += other.updated
        self.skipped += other.skipped
        self.skips += other.skips
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
        if self.skipped:
            parts.append(f"跳过 {self.skipped} 次")
        if not parts:
            parts.append("没有检查项")
        return f"{mark} {self.name}: " + "、".join(parts)


def run_attr_cases(here: pathlib.Path, renderer, report: "Report", update: bool = False) -> None:
    """属性库的公共跑法：用例 = {params, rows}，逐条喂本库的渲染函数。

    三个属性库的用例形状相同，差别只在渲染函数与列格式，所以骨架放这里，
    各库的 test_render.py 只报"用哪个渲染函数"。

    **一进一出放在同一个目录、同一个 stem**（`cases/x.json` 是输入、`cases/x.txt` 是期望
    输出，靠扩展名区分角色）。期望值多于一份的（五档渲染）才退回 `fixtures/` + `golden/`。

    用例可带一个可选的 `object`——渲染层拿它印"这次问的是谁"那一行对象头；没有就相当于
    跨对象查询（或选择器没解析到），不印。那行里的字段都来自这个对象记录。
    """
    for fixture in sorted((here / "cases").glob("*.json")):
        case = read_json(fixture)
        got = renderer(case["rows"], **case["params"], obj=case.get("object"))
        report.check(fixture.stem, got, here / "cases" / f"{fixture.stem}.txt", update)


def run_attr_parse_cases(here: pathlib.Path, library: str, entry, report: "Report") -> None:
    """属性库解析器的公共跑法：片段 = `fixtures/html/<名>.html`，期望值 = 同名 `.json`。

    `entry(doc_path)` 是**"① 如实 ∘ ② 归一"那个入口**——收入口而不是收库模块，是为了让
    测试能按 src 的层对应：② 的测试（`core/test_decorate.py`）自己给 `decorate(parse(p))`，
    就不必反过来 import ③ 的 `extract_all`。所有入口都收**文件路径**，所以片段直接喂进去。
    不读索引、不碰缓存。

    比的是"**片段 ⇒ 那个对象**"与"**整份文件 ⇒ 同一个对象**"是否一致（切片边界、表头/前导
    两种父写法、类的字段区边界都在这儿露头）：

    * `db`：对象 = 父指针 + **自身属性记录**（名字/Modify/Type/说明，逐条比）；
    * `techdb`/`cdfdb`：对象（类）的全部属性记录**逐条比**（名字/说明，cdfdb 另比来源）；
    * `dd`：片段是**整节**（六个对象都在），所以比**每个对象各自的记录名**——那正是
      "物化"这一步要保证的（每条记录落到它适用的每个对象下）。

    逐对象存储之前这里只敢比"属性名"（同名属性在别的对象/类里是另一条记录，线上记录取自
    首发那家，逐字段比会假红），**现在各存各的，那条限制没有了**——所以四库**同形、都比全**。
    db 比 `type` 是因为原文的属性表真有 Type 列（是事实）；techdb/cdfdb 的 `type`/`rw` 是各库
    ② 推的，归各库 `core/test_decorate.py` 的推法断言管。
    """
    for fragment in sorted((here / "fixtures" / "html").glob("*.html")):
        want = read_json(fragment.with_suffix(".json"))
        payload = entry(str(fragment))
        if library == "dd":
            got = {oid: sorted(r["name"] for r in obj["attrs"])
                   for oid, obj in payload["objects"].items()}
            report.expect(f"片段/{fragment.stem} 六个对象各自的记录名", got, want["objects"])
            continue
        if library == "db":
            oid = want["object"]
            obj = payload["objects"].get(oid)
            fields = ("name", "modify", "type", "desc")
            got = None if obj is None else {
                "parent": obj["parent"],
                "attrs": sorted(({k: a[k] for k in fields} for a in obj["attrs"]),
                                key=lambda r: r["name"])}
            report.expect(f"片段/{fragment.stem} 对象 {oid} 的父与自身属性记录",
                          got, {"parent": want["parent"], "attrs": want["attrs"]})
            continue
        cid = want["class"]
        cls = payload["objects"].get(cid)
        # 这里比**原文那一侧**的字段：名字/说明，cdfdb 多比一个 `source`——它标的是"这条
        # 记录从原文哪儿来的"（实参那两条与字段区的那些要分得出来）。`type`/`rw` 是各库 ②
        # 按固定规则算出来的，归各库 `core/test_decorate.py` 的推法断言管，不在这儿比。
        fields = ("name", "desc", "source") if library == "cdfdb" else ("name", "desc")
        got = None if cls is None else sorted(
            ({k: a[k] for k in fields} for a in cls["attrs"]), key=lambda r: r["name"])
        report.expect(f"片段/{fragment.stem} 类 {cid} 的全部属性记录",
                      got, [{k: r[k] for k in fields} for r in want["attrs"]])


def run_attr_raw_cases(here: pathlib.Path, parser, report: "Report") -> None:
    """**① 解析器（如实层）** 的 golden：`fixtures/raw/<名>.html` + 同名 `.json`。

    `parser` 传的是**① 那一层的模块**（`database/<库>/core/parse.py`，调它的 `.parse()`）。
    按层拆开之后每个库自己一个文件，所以这里收模块而不是收库——否则又要用模块名去猜层在哪。

    比的是 `parse()` 的**整体输出**，不按库分支——各库 raw 的形状本来就不同，那正是
    "解析器各写各的"该留下的差异。② 那半边的对照则早就有：各库 `core/test_decorate.py` 里的
    自造 HTML 用例断言的是 `decorate(parse(...))`（= ① 之后接 ②）。

    这一层**没有线上对照**（索引里只有 ② 归一后的形状），所以这些 `.json` 是**录下来的
    变更探测器，不是正解**——改动解析器时它只说"raw 变了"，对不对得人来判。因此只用
    **自造的小片段**（几百字节），不拿 44 KB 的官方片段再存一份。
    """
    root = here / "fixtures" / "raw"
    for fragment in sorted(root.glob("*.html")):
        want = read_json(fragment.with_suffix(".json"))
        report.expect(f"raw/{fragment.stem} ① 解析器输出",
                      parser.parse(str(fragment)), want)


def run_attr_search_cases(here: pathlib.Path, lib, report: "Report") -> None:
    """属性库检索的公共跑法：fixture = {payload, cases}，逐条断言返回的**行**。

    `lib` 传**库模块**（`from knowledge_virtuoso.database import db`）——**走它的公开接口**：
    `lib.search` 是共用入口（`core/query.py` 的 `Query` 按声明现绑），`lib.LIB` 是那份声明
    （借它校验载荷、往里注入载荷）。测试因此和 MCP 工具走同一道门，不碰内部件。

    ``payload`` 是**手写**的索引载荷（不引厂商原文）：检索只认载荷，不碰磁盘、不需要 doc。
    跑完必须还原——载荷是 `Store` 的进程内缓存，留着会把 fixtures 漏给后面的模块。
    """
    library = lib.LIB                      # 声明：校验与注入用它
    for fixture in sorted((here / "fixtures").glob("*.json")):
        case = read_json(fixture)
        problem = payload_problem(library, case["payload"])
        report.truthy(f"{fixture.stem}/手写载荷自己就合法（顶层三键、lib 对得上、两层键集）",
                      problem == "", problem)
        saved = library.store._data
        library.store._data = case["payload"]
        try:
            for item in case["cases"]:
                got = lib.search(**item["params"])
                report.expect(f"{fixture.stem}/{sorted(item['params'].items())}",
                              got, item["expect"])
        finally:
            library.store._data = saved
