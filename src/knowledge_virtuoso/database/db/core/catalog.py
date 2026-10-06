#!/usr/bin/env python3
"""
knowledge_virtuoso.database.db.core.catalog — 从 index.json 查询数据库对象属性信息。

查询只读取 JSON；索引缺失或损坏时报错。可显式调用构建入口从 attrib.html 重建。

用法:
  from knowledge_virtuoso.database.db.core.catalog import search_attr, build_from_html

  search_attr(objType="rect")              → 列出 rect 的全部属性
  search_attr(objType="rect", keyword="box")    → 按关键词过滤
  build_from_html()                        → 从 attrib.html 显式构建索引
"""

import os
import re
import json
import sys
from pathlib import Path
from html import unescape
from collections import defaultdict
from threading import RLock

from knowledge_virtuoso._paths import atomic_write_json, index_path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("db")

_data: dict | None = None
_lock = RLock()

# ─── section 名 → ~>objType 运行时值 ───
OBJTYPE_MAP = {
    "Arc":         {"name": "arc",         "desc": "椭圆弧线"},
    "Donut":       {"name": "donut",       "desc": "环形"},
    "Dot":         {"name": "dot",         "desc": "点"},
    "Ellipse":     {"name": "ellipse",     "desc": "椭圆"},
    "Label":       {"name": "label",       "desc": "标签"},
    "Line":        {"name": "line",        "desc": "线段"},
    "Path":        {"name": "path",        "desc": "路径"},
    "pathSeg":     {"name": "pathSeg",     "desc": "路径段"},
    "Polygon":     {"name": "polygon",     "desc": "多边形"},
    "Rect":        {"name": "rect",        "desc": "矩形"},
    "TextDisplay": {"name": "textDisplay", "desc": "文本显示"},
    "Cellview":    {"name": "cellview",    "desc": "设计视图"},
    "Instance":    {"name": "inst",        "desc": "实例（含 Pcell）"},
    "Mosaic":      {"name": "mosaic",      "desc": "二维实例阵列"},
    "InstTerm":    {"name": "instTerm",    "desc": "实例终端"},
    "Pin":         {"name": "pin",         "desc": "引脚"},
    "Terminal":    {"name": "term",        "desc": "终端"},
    "Net":         {"name": "net",         "desc": "线网"},
    "StdVia":      {"name": "stdVia",      "desc": "标准通孔"},
    "CustomVia":   {"name": "customVia",   "desc": "自定义通孔"},
    "ViaHeader":   {"name": "viaHeader",   "desc": "通孔头"},
    "InstHeader":  {"name": "instHeader",  "desc": "实例头"},
    "BusDef":      {"name": "busDef",      "desc": "总线定义"},
    "Signal":      {"name": "signal",      "desc": "信号"},
    "LP":          {"name": "lp",          "desc": "Layer-Purpose Pair"},
    "LayerHeader": {"name": "layerHeader", "desc": "层头"},
    "Group":       {"name": "group",       "desc": "对象组"},
    "Property":    {"name": "prop",        "desc": "属性"},
}

# ─── 继承链 ───
INHERITANCE = {
    "rect":        ["Generic Shape", "Generic Figure", "Generic Object"],
    "polygon":     ["Generic Shape", "Generic Figure", "Generic Object"],
    "path":        ["Generic Shape", "Generic Figure", "Generic Object"],
    "pathSeg":     ["Generic Shape", "Generic Figure", "Generic Object"],
    "line":        ["Generic Shape", "Generic Figure", "Generic Object"],
    "arc":         ["Generic Shape", "Generic Figure", "Generic Object"],
    "ellipse":     ["Generic Shape", "Generic Figure", "Generic Object"],
    "donut":       ["Generic Shape", "Generic Figure", "Generic Object"],
    "dot":         ["Generic Shape", "Generic Figure", "Generic Object"],
    "label":       ["Generic Shape", "Generic Figure", "Generic Object"],
    "textDisplay": ["Generic Shape", "Generic Figure", "Generic Object"],
    "inst":        ["Generic anyInst", "Generic Figure", "Generic Object"],
    "mosaic":      ["Generic Object"],
    "stdVia":      ["Generic Via", "Generic Object"],
    "customVia":   ["Generic Via", "Generic Object"],
    "viaHeader":   ["Generic Via Header", "Generic Object"],
    "instHeader":  ["Generic Object"],
    "cellview":    ["Generic Object"],
    "net":         ["Generic Object"],
    "instTerm":    ["Generic Object"],
    "pin":         ["Generic Object"],
    "term":        ["Generic Object"],
    "group":       ["Generic Object"],
    "prop":        ["Generic Object"],
}

# ─── Generic 层所包含的属性 ───
GENERIC_ATTRS = {
    "Generic Object": [
        {"name": "cellView", "rw": "ro", "type": "objId",  "desc": "所属 cellview ID"},
        {"name": "objType",  "rw": "ro", "type": "string", "desc": "对象类型字符串"},
        {"name": "prop",     "rw": "ro", "type": "l_objId","desc": "属性列表"},
    ],
    "Generic Figure": [
        {"name": "bBox",              "rw": "ro", "type": "bBox",    "desc": "包围盒（rect/dot/ellipse/textDisplay 可写）"},
        {"name": "net",               "rw": "rw", "type": "objId",   "desc": "关联的 net"},
        {"name": "parent",            "rw": "rw", "type": "objId",   "desc": "父 figure"},
        {"name": "pin",               "rw": "ro", "type": "objId",   "desc": "关联的 pin"},
        {"name": "purpose",           "rw": "rw", "type": "string",  "desc": "layer purpose"},
        {"name": "isAnyInst",         "rw": "ro", "type": "boolean", "desc": "t=instance, nil=shape"},
        {"name": "isShape",           "rw": "ro", "type": "boolean", "desc": "t=shape, nil=instance"},
        {"name": "children",          "rw": "ro", "type": "l_objId", "desc": "以当前对象为 parent 的子对象"},
        {"name": "groupMembers",      "rw": "ro", "type": "l_objId", "desc": "group 成员列表"},
        {"name": "figGroup",          "rw": "ro", "type": "objId",   "desc": "所属 figGroup"},
        {"name": "assocTextDisplays", "rw": "ro", "type": "l_objId", "desc": "关联的 textDisplay 列表"},
        {"name": "textDisplays",      "rw": "ro", "type": "l_objId", "desc": "拥有的 textDisplay 列表"},
        {"name": "markers",           "rw": "ro", "type": "l_objId", "desc": "关联的 marker 列表"},
        {"name": "matchPoints",       "rw": "rw", "type": "boolean", "desc": "子对象点匹配"},
    ],
    "Generic Shape": [
        {"name": "layerName",    "rw": "rw", "type": "string",  "desc": "层名"},
        {"name": "layerNum",     "rw": "rw", "type": "integer", "desc": "层号"},
        {"name": "lpp",          "rw": "rw", "type": "list",    "desc": "layer-purpose pair"},
        {"name": "routeStatus",  "rw": "rw", "type": "string",  "desc": "normal/fixed/locked"},
        {"name": "connRoutes",   "rw": "ro", "type": "l_objId", "desc": "连接的 route 列表"},
        {"name": "isUnshielded", "rw": "rw", "type": "boolean", "desc": "是否未屏蔽"},
        {"name": "shieldedNet1", "rw": "rw", "type": "netId",   "desc": "屏蔽 net 1"},
        {"name": "shieldedNet2", "rw": "rw", "type": "netId",   "desc": "屏蔽 net 2"},
    ],
    "Generic anyInst": [
        {"name": "name",       "rw": "rw", "type": "string",  "desc": "实例名称"},
        {"name": "master",     "rw": "rw", "type": "objId",   "desc": "master cellview 指针"},
        {"name": "cellName",   "rw": "ro", "type": "string",  "desc": "master cell 名称"},
        {"name": "libName",    "rw": "ro", "type": "string",  "desc": "master lib 名称"},
        {"name": "viewName",   "rw": "ro", "type": "string",  "desc": "master view 名称"},
        {"name": "baseName",   "rw": "rw", "type": "string",  "desc": "实例基础名"},
        {"name": "instHeader", "rw": "ro", "type": "objId",   "desc": "所属 instHeader"},
        {"name": "instTerms",  "rw": "ro", "type": "l_objId", "desc": "实例终端列表"},
        {"name": "numInst",    "rw": "rw", "type": "integer", "desc": "迭代次数"},
    ],
}


def extract_attrs_from_table(html_section: str) -> list[dict]:
    """从 HTML 表格中提取属性行。"""
    attrs = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_section, re.DOTALL)
    for row in rows:
        if re.search(r'<th', row, re.IGNORECASE):
            continue
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(tds) < 3:
            continue
        t1 = unescape(re.sub(r'<[^>]+>', ' ', tds[0])).strip()
        if not re.match(r'^[a-z][a-zA-Z]+$', t1):
            continue
        noise = {'attribute', 'note', 'include', 'type', 'modify',
                 'description', 'name', 'value'}
        if t1.lower() in noise:
            continue

        rw_raw = unescape(re.sub(r'<[^>]+>', ' ', tds[1])).strip()
        type_raw = unescape(re.sub(r'<[^>]+>', ' ', tds[2])).strip()
        rw = 'rw' if 'yes' in rw_raw.lower() else 'ro'
        typ = re.sub(r'\s+', ' ', type_raw)[:40]

        desc_parts = []
        for td in tds[3:]:
            d = unescape(re.sub(r'<[^>]+>', ' ', td)).strip()
            if d:
                desc_parts.append(d)
        desc = re.sub(r'\s+', ' ', ' '.join(desc_parts)).strip()[:200]

        attrs.append({"name": t1, "rw": rw, "type": typ, "desc": desc})
    return attrs


def extract_all(doc_path: str) -> dict:
    """从 attrib.html 提取所有属性定义。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')

    all_attrs: dict[str, dict] = {}

    def add_attr(attr: dict, runtime_name: str):
        name = attr["name"]
        if name not in all_attrs:
            attr["objTypes"] = [runtime_name]
            all_attrs[name] = attr
        else:
            if runtime_name not in all_attrs[name]["objTypes"]:
                all_attrs[name]["objTypes"].append(runtime_name)

    sections = {
        "cellview": ("Attributes of Cellviews", None),
        "inst":      ("Attributes of Instances, Instance Headers, and Mosaics", None),
        "instTerm":  ("Attributes of Instance Terminals, Pins, and Terminals", None),
        "net":       ("Attributes of Bus Definitions, Nets, and Signals", None),
        "lp":        ("Attributes of Layer Purpose Pairs and Layer Headers", None),
        "group":     ("Attributes of Groups, Group Members, and Properties", None),
    }

    for runtime_name, (needle, _) in sections.items():
        first = text.find(needle)
        if first == -1:
            continue
        second = text.find(needle, first + 10)
        if second == -1:
            second = first
        third = text.find(needle, second + 10)
        start_idx = third if third != -1 else second

        end_idx = text.find('<h3', start_idx + 10)
        if end_idx == -1:
            end_idx = min(start_idx + 15000, len(text))
        for a in extract_attrs_from_table(text[start_idx:end_idx]):
            add_attr(a, runtime_name)

    shape_headings = {
        "arc":         "Arc Attributes",
        "donut":       "Donut Attributes",
        "dot":         "Dot Attributes",
        "ellipse":     "Ellipse Attributes",
        "label":       "Label Attributes",
        "line":        "Line Attributes",
        "path":        "Path Attributes",
        "pathSeg":     "pathSeg Attributes",
        "polygon":     "Polygon Attributes",
        "rect":        "Rectangle Attributes",
        "textDisplay": "Text Display Attributes",
    }

    for runtime_name, heading in shape_headings.items():
        idx = 0
        last_idx = -1
        while True:
            pos = text.find(heading, idx)
            if pos == -1:
                break
            last_idx = pos
            idx = pos + 1
        if last_idx == -1:
            continue
        end = last_idx
        for tag in ['<h4', '<h3']:
            nxt = text.find(tag, end + 10)
            if nxt != -1 and nxt < end + 10000:
                end = nxt
                break
        else:
            end = last_idx + 5000
        for a in extract_attrs_from_table(text[last_idx:end]):
            add_attr(a, runtime_name)

    for layer_name, layer_attrs in GENERIC_ATTRS.items():
        for ga in layer_attrs:
            name = ga["name"]
            if name not in all_attrs:
                all_attrs[name] = {
                    "name": name,
                    "rw": ga["rw"],
                    "type": ga["type"],
                    "desc": ga["desc"],
                    "objTypes": ["_generic"],
                }
            else:
                if "_generic" not in all_attrs[name]["objTypes"]:
                    all_attrs[name]["objTypes"].append("_generic")
                if ga["desc"] and len(ga["desc"]) > len(all_attrs[name].get("desc", "")):
                    all_attrs[name]["desc"] = ga["desc"]

    return all_attrs


def expand_objtype(attrs: dict) -> dict:
    """为每个 objType 展开完整属性列表（含继承链）。"""
    expanded = {}
    for rt_name, chain in INHERITANCE.items():
        all_names = set()
        for layer in chain:
            for ga in GENERIC_ATTRS.get(layer, []):
                all_names.add(ga["name"])
        for name, info in attrs.items():
            if rt_name in info.get("objTypes", []):
                all_names.add(name)
        expanded[rt_name] = sorted(all_names)
    return expanded


def build_from_html(doc_path: str | None = None) -> dict:
    """从 attrib.html 解析，返回与 JSON 相同结构的 dict。"""
    if doc_path is None:
        doc_root = os.environ.get("VIRTUOSO_DOC_DIR")
        if not doc_root:
            raise FileNotFoundError(
                "index.json 缺失，且 VIRTUOSO_DOC_DIR 未设置，无法重建。"
                "请设置 VIRTUOSO_DOC_DIR 或运行 knowledge-virtuoso-build db")
        doc_path = os.path.join(doc_root, "skdfref", "attrib.html")

    if not Path(doc_path).exists():
        raise FileNotFoundError(f"文档不存在: {doc_path}，请检查 VIRTUOSO_DOC_DIR 环境变量")

    attrs = extract_all(doc_path)
    return {
        "objTypes": OBJTYPE_MAP,
        "inheritance": INHERITANCE,
        "genericLayers": {k: [a["name"] for a in v] for k, v in GENERIC_ATTRS.items()},
        "attributes": attrs,
        "expanded": expand_objtype(attrs),
    }


def _load() -> dict:
    global _data
    if _data is None:
        with _lock:
            if _data is None:
                try:
                    with open(_DEFAULT_INDEX, encoding="utf-8") as f:
                        _data = json.load(f)
                except (OSError, json.JSONDecodeError) as primary:
                    _data = _rebuild(primary)
    return _data


def _rebuild(primary: Exception) -> dict:
    doc_root = os.environ.get("VIRTUOSO_DOC_DIR")
    if not doc_root:
        raise RuntimeError(
            f"db_attr 索引不可用: {_DEFAULT_INDEX} ({primary})。"
            f"设置 VIRTUOSO_DOC_DIR 后可自动从官方 doc 重建，或运行: knowledge-virtuoso-build db"
        ) from primary
    print(f"db_attr 索引缺失/损坏 ({_DEFAULT_INDEX}): {primary}；从 {doc_root!r} 重建", file=sys.stderr)
    payload = build_from_html()
    atomic_write_json(_DEFAULT_INDEX, payload)
    return payload


def search_attr(objType: str = "", keyword: str = "") -> list[dict]:
    """按对象类型和关键词搜索属性。"""
    d = _load()
    attrs = d["attributes"]

    if objType:
        names = set(d["expanded"].get(objType, []))
        if not names:
            return []
    else:
        names = set(attrs.keys())

    kw = keyword.lower().strip()
    if kw:
        names = {n for n in names if kw in n.lower()}

    results = []
    for name in sorted(names):
        info = attrs.get(name)
        if info:
            results.append({
                "name": name,
                "rw": info.get("rw", "?"),
                "type": info.get("type", "?"),
                "desc": info.get("desc", ""),
            })

    return results


def main() -> None:
    """CLI：从 attrib.html 提取 dbObject 属性定义，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 attrib.html 提取 dbObject 属性定义")
    parser.add_argument("--doc", default=None,
                        help="attrib.html 路径 (默认取 VIRTUOSO_DOC_DIR/skdfref/attrib.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    output = build_from_html(args.doc)

    output_path = Path(args.output)
    atomic_write_json(output_path, output)
    print(f"\n已导出到 {output_path}")
    print(f"  objTypes:    {len(output['objTypes'])} 个运行时类型映射")
    print(f"  attributes:  {len(output['attributes'])} 个属性")
    print(f"  inheritance: {len(output['inheritance'])} 条继承链")
    print(f"  expanded:    {len(output['expanded'])} 个类型的完整属性列表")


if __name__ == "__main__":
    main()


