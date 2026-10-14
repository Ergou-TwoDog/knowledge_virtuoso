#!/usr/bin/env python3
"""tech 库：检索 + 解析（断言式）：`database/techdb/core/catalog.py`。

设计要点见 `src/knowledge_virtuoso/database/techdb/__init__.py` 与 catalog 的模块 docstring：
**每个 `techID~>X` 类各存自己那份属性**（载荷里没有"全局按名去重"的字典了——那是本库
以前的病根：24 个属性名跨类，只留第一个类的说明与类型）。

本文件锁住：

- **检索**：类名怎么认（类名 / objType 别名 / 忽略大小写）、关键词怎么筛、行多一列
  `classes`；**跨类查询每个类各出一行**（同一名字在不同类里类型可能不同）。
- **解析**：`fixtures/html/` 的官方 doc 片段 + 自造 HTML 钉住 `<h3>` 定位、类名归一、
  续行并入、**类集合来自标题而非手写白名单**。
- **构建期校验**：空类 / 类内重名 / 名字形状不对都要抛错，不许静默。

不读真索引、不需要 doc。
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "common.py").exists())))

from common import Report, run_attr_parse_cases, run_attr_search_cases  # noqa: E402

from knowledge_virtuoso.database.core import objects as objects_mod  # noqa: E402
from knowledge_virtuoso.database.techdb.core import catalog  # noqa: E402

_SYNTHETIC = (
    '<h3><a>techID~>viaDefs (含尾注)</a></h3>'
    '<h4><a>Description</a></h4><p>Retrieves via definitions. 手写的第二句不算数。</p>'
    '<h4><a>Attributes</a></h4><table>'
    '<tr><td>firstName</td></tr>'
    '<tr><td>This row continues the description of firstName.</td></tr>'
    '<tr><td>secondName</td><td>Inline description.</td></tr>'
    '</table>'
    '<h4><a>Rules</a></h4><p>表后的小节，充当边界。</p>'
    # 类集合来自标题：这一节没有"白名单"挡着，它就该成为一个类
    '<h3><a>techID~>anotherClass</a></h3>'
    '<h4><a>Attributes</a></h4><table><tr><td>kept</td><td>不再被丢弃</td></tr></table>'
    '</body>'
)


def parse_synthetic(html: str) -> dict:
    """自造 HTML 写成文件喂给 `extract_all`（它收路径）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "appA.html"
        path.write_text(html, encoding="utf-8")
        return catalog.extract_all(str(path))


def run(report: Report, update: bool = False) -> None:
    run_attr_search_cases(HERE, catalog, "search_tech_attr", report)

    # ── 片段回放：官方 doc 的一个类段 → 该类的全部属性记录（名字/类型/说明）──
    run_attr_parse_cases(HERE, "techdb", catalog, report)
    report.expect("片段/夹具齐全",
                  sorted(p.stem for p in (HERE / "fixtures" / "html").glob("*.html")),
                  ["class_layers", "class_viaDefs"])

    # ── 自造片段：类段语法（`<h3>` + Description / Attributes 两个 h4 小节）──
    # 表后留一个 `<h4>`：解析器的小节正则靠"到下一个 h4/h3/</body> 为止"收尾，缺了这个
    # 边界它会整节取不到（真实文件里表后本来还有别的小节）。
    payload = parse_synthetic(_SYNTHETIC)
    report.expect("解析/只认 techID~> 开头的 h3，去掉类名尾注，且**类集合来自标题**",
                  sorted(payload["objects"]), ["anotherClass", "viaDefs"])
    report.expect("解析/类记录的形状（desc 取自原文的 Description 小节，不是手写表）",
                  {k: payload["objects"]["viaDefs"][k] for k in ("id", "title", "desc")},
                  {"id": "viaDefs", "title": "techID~>viaDefs",
                   "desc": "Retrieves via definitions. 手写的第二句不算数。"})
    report.expect("解析/名称行开新条目、续行并进上一条目的 desc（名称行没有 desc 时）",
                  [(a["name"], a["desc"]) for a in payload["objects"]["viaDefs"]["attrs"]],
                  [("firstName", "This row continues the description of firstName."),
                   ("secondName", "Inline description.")])
    report.expect("解析/type 由该类自己的说明推，推不出是空串（'continues…' 无线索）",
                  [a["type"] for a in payload["objects"]["viaDefs"]["attrs"]], ["", ""])

    # ── 类型推断：由描述猜类型，猜不中给空串 ──
    for desc, want in (("list of database identifiers for the net", "l_objId"),
                       ("the database identifier of the shape", "objId"),
                       ("list of layer names", "l_string"),
                       ("t or nil", "boolean"),
                       ("name of the tech file", "string"),
                       ("描述里什么线索都没有", "")):
        report.expect(f"解析/infer_type({desc!r})", catalog.infer_type(desc), want)

    # ── 构建期校验：空类 / 类内重名 / 名字形状不对都要炸，不许静默 ──
    def _bad(cls) -> bool:
        try:
            catalog._validated({"objects": cls})
            return False
        except ValueError:
            return True

    report.expect("校验/一个属性都没有的类要抛错",
                  _bad({"x": {"id": "x", "title": "t", "desc": "", "attrs": []}}), True)
    report.expect("校验/类内属性名重复要抛错",
                  _bad({"x": {"id": "x", "title": "t", "desc": "",
                              "attrs": [{"name": "a", "type": "", "desc": ""}] * 2}}), True)
    report.expect("校验/属性名形状不对要抛错",
                  _bad({"x": {"id": "x", "title": "t", "desc": "",
                              "attrs": [{"name": "9bad", "type": "", "desc": ""}]}}), True)
    report.expect("校验/通过时打上格式版本",
                  catalog._validated({"objects": {"x": {"id": "x", "title": "t", "desc": "",
                                                        "attrs": [{"name": "a", "type": "", "desc": ""}]}}})
                  ["version"], catalog._PAYLOAD_VERSION)

    # ── 载荷里没有 rw（原文没有读写列：“?”是行形状，不是事实）──
    report.truthy("解析/载荷不存 rw（它属于行形状）",
                  all("rw" not in a for c in payload["objects"].values() for a in c["attrs"]))

    # ── 选择器：objType 别名是查询时词汇，不进索引 ──
    classes = {"viaDefs": {"attrs": [{"name": "a", "type": "", "desc": ""}]}}
    report.expect("检索/类名 / objType 别名 / 忽略大小写 / 不认识",
                  [objects_mod.resolve(classes, "viaDefs"),
                   objects_mod.resolve(classes, "stdViaDef", catalog._ALIASES),
                   objects_mod.resolve(classes, "VIADEFS"),
                   objects_mod.resolve(classes, "没有这个")],
                  ["viaDefs", "viaDefs", "viaDefs", None])


if __name__ == "__main__":
    report = Report("database/techdb/core/test_catalog")
    run(report)
    print(report.summary())
    print("\n".join(report.failures[:10]))
    raise SystemExit(1 if report.failures else 0)
