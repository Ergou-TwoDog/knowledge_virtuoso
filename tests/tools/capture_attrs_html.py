#!/usr/bin/env python3
"""采集属性库的 **HTML 片段**当解析器夹具（手动跑，需要本机 doc 与本机索引）。

```bash
VIRTUOSO_DOC_DIR=<IC618 doc 根> uv run python -B tests/capture_attrs_html.py
```

三个属性库的解析器（`database/<库>/core/catalog.py` 的 `extract_all`）各按自己的方式在整份
HTML 里**扫**：db 按标题走（h4 = 一个对象，紧随的第一张表 = 它的属性表）、techdb 靠
`techID~>` 的 `<h3>` 段、cdfdb 靠按字段名找 `<h4>`。所以片段就是"该解析器会看成一段"的
那块 HTML：

  database/<库>/core/fixtures/html/<片段>.html   片段
  database/<库>/core/fixtures/html/<片段>.json   期望值（**取自线上索引**，非解析器跑出来的）

期望值的取法（这段 HTML 在线上索引里对应谁）：**db 取该对象在整份文件里的样子**
（父 + 自身属性名），比"片段 ⇒ 对象"与"整份文件 ⇒ 同一个对象"是否一致；techdb/cdfdb
按 `classes[cid].attributes` 取归属名字集合。这样夹具与"用户机器上真正在用的索引"对齐，
而不是与解析器自己对齐。

**techdb 不比 `desc`**：线上记录的 desc 来自**第一次**出现该名字的那个节，片段之外的节
可能才是首发者；解析器在片段里给出的 desc 与线上不同是正常的。比的是名字集合与
`rw`/`type`（以及归属关系）。cdfdb 单类片段不存在这个问题，它比 desc。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent      # tests/tools
TESTS = HERE.parent                                  # tests/
REPO = TESTS.parent                                  # 仓库根
sys.path.insert(0, str(TESTS))

from common import write_text  # noqa: E402

from knowledge_virtuoso.database.cdfdb.core import catalog as cdf_cat  # noqa: E402
from knowledge_virtuoso.database.dd.core import catalog as dd_cat  # noqa: E402
from knowledge_virtuoso.database.db.core import catalog as db_cat  # noqa: E402
from knowledge_virtuoso.database.techdb.core import catalog as tech_cat  # noqa: E402

FIXTURES = TESTS / "knowledge_virtuoso" / "database"

# (库, 片段名, 源文件, 归属)。归属是"这段 HTML 属于谁"：db 用节短语与运行时类型，
# techdb/cdfdb 用类名。实测数量/为何选它写在 tests/README.md 的族清单里。
TARGETS = (
    ("db", "section_cellview", "skdfref/attrib.html",
     {"kind": "phrase", "phrase": "Attributes of Cellviews", "object": "Cellview"}),
    ("db", "section_inst", "skdfref/attrib.html",
     {"kind": "phrase", "phrase": "Attributes of Instances, Instance Headers, and Mosaics",
      "object": "Instance"}),
    ("db", "shape_pathSeg", "skdfref/attrib.html",
     {"kind": "shape", "heading": "pathSeg Attributes", "object": "pathSeg"}),
    # Rectangle 一节原文只有一句 "include Generic Shape Attributes"，没有自己的属性行——
    # 它是"自身 0 条、全部靠继承"的真实样例（父 = Generic Shape）。
    ("db", "shape_rect_note_only", "skdfref/attrib.html",
     {"kind": "shape", "heading": "Rectangle Attributes", "object": "Rectangle"}),
    ("techdb", "class_viaDefs", "sktechfile/appA.html",
     {"kind": "h3", "class": "viaDefs"}),
    ("techdb", "class_layers", "sktechfile/appA.html",
     {"kind": "h3", "class": "layers"}),
    ("cdfdb", "class_cdfDataId", "skartistref/chap21.html",
     {"kind": "class", "class": "cdfDataId"}),
    ("cdfdb", "class_cdfParamId", "skartistref/chap21.html",
     {"kind": "class", "class": "cdfParamId"}),
    # ② 数据管理对象：整节（h2 到下一个 h2）——本节里没有 h3/h4，转置表与关系表都在里头
    ("dd", "dd_section", "skdfref/chap3.html",
     {"kind": "h2", "heading": "Attributes of Data Management Objects"}),
)

_LIVE = {}


def live(library: str) -> dict:
    """线上索引载荷（进程内只读一次）。"""
    if library not in _LIVE:
        module = {"db": db_cat, "techdb": tech_cat, "cdfdb": cdf_cat, "dd": dd_cat}[library]
        _LIVE[library] = module._STORE.load()
    return _LIVE[library]


def _nth_occurrence(text: str, needle: str) -> int:
    """解析器自己的定位规则：第 3 次出现（不足则退第 2 次、第 1 次）。"""
    first = text.find(needle)
    second = text.find(needle, first + 10) if first != -1 else -1
    third = text.find(needle, second + 10) if second != -1 else -1
    return third if third != -1 else (second if second != -1 else first)


def slice_db(text: str, spec: dict) -> str:
    """db 的节：短语 → 下一个 ``<h3``；形状节取该标题的**最后一次**出现。"""
    if spec["kind"] == "phrase":
        start = _nth_occurrence(text, spec["phrase"])
        if start == -1:
            raise SystemExit(f"找不到节短语 {spec['phrase']!r}")
        end = text.find("<h3", start + 10)
        return text[start:end if end != -1 else min(start + 15000, len(text))], start
    last, idx = -1, 0
    while True:
        pos = text.find(spec["heading"], idx)
        if pos == -1:
            break
        last, idx = pos, pos + 1
    if last == -1:
        raise SystemExit(f"找不到形状标题 {spec['heading']!r}")
    # 起点要从**标题元素开头**算：`last` 落在 `<h4><a …>pathSeg Attributes</a></h4>` 的
    # 文字上，从那里切会把开标签切掉。解析器按标题走，片段得从 `<h4` 起。
    start = text.rfind("<h4", 0, last)
    last = start if start != -1 else last
    end = last
    for tag in ("<h4", "<h3"):
        nxt = text.find(tag, last + 10)
        if nxt != -1 and nxt < last + 10000:
            end = nxt
            break
    else:
        end = last + 5000
    return text[last:end], last


def slice_techdb(text: str, spec: dict) -> str:
    """techdb 的一个类：该 ``<h3><a>techID~>X</a></h3>`` 到下个 h3。"""
    heads = list(re.finditer(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', text, re.DOTALL))
    for i, match in enumerate(heads):
        heading = tech_cat._strip(match.group(1))
        if not heading.startswith("techID~>"):
            continue
        cid = re.sub(r"\s*\(.*?\)\s*$", "", heading.replace("techID~>", "").rstrip("~> ").strip()).strip()
        if cid == spec["class"]:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[match.start():end], match.start()
    raise SystemExit(f"techdb 找不到类 {spec['class']!r}")


def slice_cdfdb(text: str, spec: dict) -> str:
    """cdfdb 的一个对象类：从该类的第一个字段到**下一个对象类的第一个字段或下一个 h3**。

    两个类的字段在原文里是前后排布的（cdfDataId 在前、cdfParamId 在后），所以后者的结尾
    得靠 ``<h3`` / ``[TOPIC_END]`` 兜——否则会把文件尾巴整段收进来。
    """
    fields = {"cdfDataId": ("id", "type", "parameters", "doneProc", "formInitProc"),
              "cdfParamId": ("use", "paramType", "defValue", "value", "prompt", "choices",
                             "units", "editable", "callback", "parseAsNumber", "dontSave",
                             "parseAsCEL", "storeDefault", "display")}
    other = "cdfParamId" if spec["class"] == "cdfDataId" else "cdfDataId"

    def positions(names) -> list[int]:
        # 按 **h4 文本**找，与 catalog 的 `_h4_index` 同一口径：原文有 `parseAsNumber`
        # 这种"首个锚点为空"的写法，按 `<h4><a>名</a></h4>` 的形状匹配会整个漏掉。
        out = []
        for fn in names:
            m = re.search(r'<h4[^>]*>(?:(?!</h4>).)*?>' + re.escape(fn) + r'</a>\s*</h4>',
                          text, re.DOTALL)
            if not m:
                m = re.search(r'<h4[^>]*>(?:(?!</h4>).)*?' + re.escape(fn) +
                              r'(?:(?!</h4>).)*?</h4>', text, re.DOTALL)
            if m:
                out.append(m.start())
        return out

    starts = positions(fields[spec["class"]])
    if not starts:
        raise SystemExit(f"cdfdb 找不到类 {spec['class']!r} 的字段")
    start = min(starts)
    bounds = [p for p in positions(fields[other]) if p > start]
    bounds += [p for p in (text.find("<h3", start + 10), text.find("<!-- [TOPIC_END]", start + 10))
               if p != -1]
    return text[start:min(bounds) if bounds else len(text)], start


def slice_dd(text: str, spec: dict) -> str:
    """dd 的整节：该 ``<h2>`` 文字到下个 ``<h2``（本节里没有 h3/h4）。"""
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', text, re.DOTALL | re.IGNORECASE):
        if dd_cat._strip(m.group(1)) == spec["heading"]:
            nxt = re.search(r'<h2', text[m.end():], re.IGNORECASE)
            end = m.end() + nxt.start() if nxt else len(text)
            return text[m.start():end], m.start()
    raise SystemExit(f"dd 找不到小节 {spec['heading']!r}")


SLICERS = {"db": slice_db, "techdb": slice_techdb, "cdfdb": slice_cdfdb, "dd": slice_dd}


def with_boundary(text: str, region: str, start: int) -> str:
    """片段末尾补上"下一个标题的开头"当**边界记号**。

    三个解析器都靠"到下一个标题为止"收尾（db 找 ``<h3``、cdfdb 的正文与显示表用
    ``(?=<h4|<h3|…)`` 前瞻）。片段若正好切在边界上，这个标记就不在片段里了，于是退化成
    兜底截断——db 会只取前 15000 字符（62 条属性只剩 19 条）、cdfdb 的显示表整张取不到。
    真实文件里这个标题本来就在，补回来才是解析器真正看到的样子。
    """
    end = start + len(region)
    pos = min((p for p in (text.find("<h3", end), text.find("<h4", end), text.find("<h2", end))
               if p != -1), default=-1)
    if pos == -1:
        raise SystemExit(f"片段起点 {start} 之后找不到标题边界")
    close = text.find(">", pos)
    return region + text[pos:close + 1]


def expectation(library: str, spec: dict, payload: dict) -> dict:
    """这段 HTML 在线上索引里对应的那部分。

    期望值 = "那段 HTML 在整份文件里对应谁"：`db` 取该对象的父与自身属性名；其余库取该类的
    **全部属性记录**（名字/类型/说明）。比的是"片段 ⇒ 对象"与"整份文件 ⇒ 同一个对象"一致
    （切片边界、表头/前导两种父写法、类的字段区边界都在这露头）。
    """
    if library == "dd":
        # 期望值 = 这一节在整份文件里解析出来的三样：对象全集 / 属性 / 关系
        return {"objectTypes": payload["objectTypes"], "attributes": payload["attributes"],
                "relations": payload["relations"]}
    if library == "db":
        obj = payload["objects"][spec["object"]]
        return {"object": obj["id"], "parent": obj["parent"],
                "own": sorted(a["name"] for a in obj["attrs"])}

    # 逐类存储之后不必再退而求其次只比"唯一名字"——同名属性出现在别的类里也不影响本类。
    cls = payload["objects"][spec["class"]]
    attrs = sorted(({"name": a["name"], "type": a["type"], "desc": a["desc"]}
                    for a in cls["attrs"]), key=lambda r: r["name"])
    return {"class": cls["id"], "attrs": attrs}


def main() -> None:
    parser = argparse.ArgumentParser(description="采集属性库解析器的 HTML 片段夹具")
    parser.add_argument("--doc-root", default=os.environ.get("VIRTUOSO_DOC_DIR"))
    args = parser.parse_args()
    if not args.doc_root or not os.path.isdir(args.doc_root):
        parser.error("需要 --doc-root（或 VIRTUOSO_DOC_DIR）指向 IC618 doc 根")
    doc_root = pathlib.Path(args.doc_root)

    rows: dict[str, list[str]] = {}
    totals: dict[str, int] = {}
    for library, name, rel, spec in TARGETS:
        text = (doc_root / rel).read_text(encoding="utf-8", errors="ignore")
        region, offset = SLICERS[library](text, spec)
        fragment = with_boundary(text, region, offset)
        # 全仓 LF（夹具要能逐字节比对，行尾不能被 checkout 改掉）。
        fragment = fragment.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        out = FIXTURES / library / "core" / "fixtures" / "html"
        write_text(out / f"{name}.html", fragment)
        want = {"source": rel, **spec, **expectation(library, spec, live(library))}
        write_text(out / f"{name}.json", json.dumps(want, ensure_ascii=False, indent=1) + "\n")
        size = len(fragment.encode("utf-8"))
        totals[library] = totals.get(library, 0) + size
        rows.setdefault(library, []).append(
            f"| `{name}.html` | {size / 1024:.1f} KB | `{rel}` | "
            f"{spec.get('phrase') or spec.get('heading') or spec['class']} |")
        if library == "db":
            count = len(want["own"])
        elif library == "dd":
            count = len(want["attributes"]) + len(want["relations"])
        else:
            count = len(want["attrs"])
        print(f"{library}/{name}: {size} 字节  ← {rel}  期望 {count} 条属性")

    for library, lines in rows.items():
        write_text(FIXTURES / library / "core" / "fixtures" / "html" / "README.md",
                   "\n".join([
                       f"# {library} 解析器的 HTML 片段（夹具）",
                       "",
                       "由 `tests/capture_attrs_html.py` 从本机官方 doc 切出。片段就是**本库解析器",
                       "会看成一段**的那块 HTML：db 是节短语到下一个 `<h3`（形状节取标题最后一次",
                       "出现），techdb 是一个 `techID~>` 的 `<h3>` 段，cdfdb 是一个对象类的字段区。",
                       "",
                       "同名 `.json` 是期望值，**取自线上索引**（按片段的归属过滤），不是解析器跑出来",
                       "的：db 按 `objTypes` 含本节运行时类型、techdb/cdfdb 按 `classes[cid].attributes`。",
                       "`names` 是归属成员、**全部要比**；`unique` 是只属于本片段的名字——只有它们的",
                       "字段可比（另一个节也列过的名字，线上字段取自首发节，见 `expectation()`）。",
                       "",
                       "| 片段 | 体积 | 源文件（doc 根下） | 归属 |",
                       "|---|---|---|---|",
                       *lines,
                       f"| **合计** | **{totals[library] / 1024:.1f} KB** | | |",
                       "",
                       "**这是 Cadence 官方文档的原文摘录**：进公开仓库前请确认符合其许可；要缩小",
                       "暴露就减少片段（改 `capture_attrs_html.py` 的 `TARGETS` 后重跑，测试会报出",
                       "缺了哪些夹具）。",
                       "",
                   ]) + "\n")
    print(f"\n合计 {sum(totals.values()) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
