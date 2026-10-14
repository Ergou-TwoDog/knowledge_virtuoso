#!/usr/bin/env python3
"""
knowledge_virtuoso.database.dd.core.catalog — 解析 chap3.html，按**对象**查数据管理对象的属性与关系。

原文（`skdfref/chap3.html` 第 19 章 *Design Management Functions* 的
"Attributes of Data Management Objects" 一节）的记法与另外三个库**都不同**：它是
**转置**的——一张表一行一个属性，后面每个适用对象各占一格：

    Attribute Names | Object Types Attribute is Valid For
    group           | libFile | cellFile | viewFile
    name            | lib | cell | view | libFile | cellFile | viewFile

再加一张关系表：`关系名 | 基数 | 适用对象…`（`cells | 1:n | lib`）。

于是本库的载荷**照原文存**（一行一条记录 + 它适用于哪些对象），按对象取是**查询时**的事：

    {"version": 1,
     "objectTypes": ["lib", "cell", "view", "libFile", "cellFile", "viewFile"],
     "attributes": {name: {name, kind: "attr",     objectTypes: [...]}},
     "relations":  {name: {name, kind: "relation", cardinality: "1:n", objectTypes: [...]}}}

**为什么不像 db/techdb/cdfdb 那样逐对象存**：那三库的原文是"每个对象一张表"，同名属性在
不同对象里可以是不同的东西（techdb 实测 24 个名字跨类、类型各不相同），不逐对象存就会
丢。本库原文一条记录只说一遍，**同一个名字对所有适用对象是同一回事**，逐对象复制反而
是重复——所以这里没有可丢的信息，照原文存最忠实。

**本库拿不到类型也拿不到说明**：原文的属性表只有"名字 | 适用对象"两列；类型图例虽然
在 HTML 里（一张 9 行表：b/d/f/g/l/n/s/t/x），但**逐条字母只出现在没进 HTML 的图里**，
所以行里没有 type、也没有 desc。这一点写进了工具 docstring 与 `README.md`。

索引存取见 `database/core/store.py`；行 → 文本见 `../render.py`。
"""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import store

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("dd")

# 载荷格式版本。v1 = 建库；v2 = `objects` → `objectTypes` 改名——统一后的
# `objects` 是"对象 id → 记录"的字典，而本库它原本是**对象名列表**，同名不同义是个坑。
_PAYLOAD_VERSION = 2

_SECTION = "Attributes of Data Management Objects"
_ATTR_HEADER = "Attribute Names"
_RELATION_HEADER = "Relation names"
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CARD_RE = re.compile(r"^\d+:(?:\d+|n)$")     # 原文只有 `1:1` 与 `1:n` 两种


def _strip(html: str) -> str:
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _rows(table_html: str) -> list[list[str]]:
    """表格 → 非空格子组成的行（格子本身是字符串）。"""
    out = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL):
        cells = [_strip(td) for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def _section_html(text: str) -> str:
    """取该 h2 小节（到下一个 h2 为止）。这一节里没有 h3/h4。"""
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', text, re.DOTALL | re.IGNORECASE):
        if _strip(m.group(1)) == _SECTION:
            nxt = re.search(r'<h2', text[m.end():], re.IGNORECASE)
            return text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    raise ValueError(f"找不到小节 {_SECTION!r}")


def _pick(tables: list[list[list[str]]], header: str) -> list[list[str]]:
    """按**表头签名**挑表：本节里还有运算符表与类型图例表，靠表头避掉。"""
    for rows in tables:
        if rows and rows[0] and rows[0][0] == header:
            return rows[1:]
    raise ValueError(f"找不到表头为 {header!r} 的表")


def extract_all(doc_path: str) -> dict:
    """从 chap3.html 提取该小节的属性表与关系表，返回索引载荷。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')
    tables = [_rows(t) for t in re.findall(r'<table.*?</table>', _section_html(text), re.DOTALL)]

    attributes = {}
    for cells in _pick(tables, _ATTR_HEADER):
        attributes[cells[0]] = {"name": cells[0], "kind": "attr", "objectTypes": cells[1:]}

    relations = {}
    for cells in _pick(tables, _RELATION_HEADER):
        relations[cells[0]] = {"name": cells[0], "kind": "relation",
                               "cardinality": cells[1] if len(cells) > 1 else "",
                               "objectTypes": cells[2:]}

    return {"objectTypes": _universe(relations), "attributes": attributes,
            "relations": relations}


def _universe(relations: dict) -> list[str]:
    """对象全集与顺序：取**枚举得最全的那些关系行**（原文里 `lib` 与 `parent` 把 6 个
    对象依次列全），并要求它们彼此一致。表 19-1 的 6 个适用列没有列名，顺序只能从这儿来。
    """
    counts = [(len(r["objectTypes"]), r) for r in relations.values()]
    if not counts:
        return []
    widest = max(n for n, _ in counts)
    full = [r["objectTypes"] for n, r in counts if n == widest]
    first = full[0]
    if any(o != first for o in full[1:]):
        raise ValueError(f"对象全集的候选行彼此不一致：{full}")
    return list(first)


def _validated(payload: dict) -> dict:
    """构建期校验 + 打格式版本。

    这里校验得比别的库细：本库的解析靠"表头签名"和"最全的那行给出对象顺序"，
    排版一变就可能悄悄错位——宁可构建失败，也不要产出一张看起来正常的错表。
    """
    objects = payload["objectTypes"]
    if not objects:
        raise ValueError("对象全集是空的（关系表里没有把对象列全的行？）")
    if not payload["attributes"] and not payload["relations"]:
        raise ValueError("属性表与关系表都是空的（表头签名变了？）")
    known = set(objects)
    for kind, records in (("属性", payload["attributes"]), ("关系", payload["relations"])):
        for name, rec in records.items():
            if not _NAME_RE.match(name):
                raise ValueError(f"{kind}名形状不对：{name!r}")
            if not rec["objectTypes"]:
                raise ValueError(f"{kind} {name!r} 没列出任何适用对象")
            unknown = [o for o in rec["objectTypes"] if o not in known]
            if unknown:
                raise ValueError(f"{kind} {name!r} 的适用对象不在对象全集里：{unknown}")
            if kind == "关系" and not _CARD_RE.match(rec.get("cardinality", "")):
                raise ValueError(f"关系 {name!r} 的基数不像 `1:n`：{rec.get('cardinality')!r}")
    clash = set(payload["attributes"]) & set(payload["relations"])
    if clash:
        raise ValueError(f"属性名与关系名撞了：{sorted(clash)}")
    return {"version": _PAYLOAD_VERSION, **payload}


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、构建期校验 + 格式版本。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="dd_attr",
    lib="dd",
    doc_parts=("skdfref", "chap3.html"),
    parse=extract_all,
    payload=_validated,
    version=_PAYLOAD_VERSION,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 chap3.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def _resolve(objects, selector: str) -> str | None:
    """对象选择器 → 对象名：精确 → 忽略大小写。认不出返回 None。"""
    if not selector:
        return None
    if selector in objects:
        return selector
    low = selector.lower()
    for oid in objects:
        if oid.lower() == low:
            return oid
    return None


def _row(name: str, info: dict) -> dict:
    """本库的行形状：`kind` 区分属性/关系；关系才有 `cardinality`。

    没有 `type`、也没有 `desc`——原文没给（见模块 docstring）。
    """
    return {"name": name, "kind": info.get("kind", "attr"),
            "cardinality": info.get("cardinality", ""),
            "objectTypes": list(info.get("objectTypes", []))}


def search_dd_attr(object: str = "", keyword: str = "") -> list[dict]:
    """按对象与关键词搜索数据管理对象的属性与关系。

    参数名就叫 `object`（数据管理对象：lib/cell/view/libFile/cellFile/viewFile）——
    它同时是 MCP 工具的第一个参数名，别改名。
    """
    data = _load()
    records = {**data["attributes"], **data["relations"]}   # 实测两类名字两两不重

    if object:
        oid = _resolve(data["objectTypes"], object)
        if oid is None:
            return []                      # 不认识的选择器：区别于"认识但筛完没结果"
        names = {n for n, rec in records.items() if oid in rec["objectTypes"]}
    else:
        names = set(records)
    return store.query_rows(records, names, keyword, _row)


def main() -> None:
    """CLI：从 chap3.html 提取数据管理对象的属性与关系，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 skdfref/chap3.html 提取数据管理对象属性")
    parser.add_argument("--doc", default=None,
                        help="chap3.html 路径 (默认取 VIRTUOSO_DOC_DIR/skdfref/chap3.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    result = build_from_html(args.doc)
    atomic_write_json(Path(args.output), result)

    print(f"\n已导出到 {args.output}")
    print(f"  objectTypes: {len(result['objectTypes'])} 个 → {', '.join(result['objectTypes'])}")
    print(f"  attributes:  {len(result['attributes'])} 条")
    print(f"  relations:   {len(result['relations'])} 条")


if __name__ == "__main__":
    main()
