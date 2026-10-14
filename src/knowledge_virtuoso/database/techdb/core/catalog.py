#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.core.catalog — 从 index.json 查询 tech 数据库对象类及其 ~> 属性。

本模块只管**本库的内容**：appA.html 怎么解析成载荷、载荷怎么变成行。索引在哪、怎么读、坏了
怎么从官方 doc 重建（缓存、锁、原子写回）都在 `database/core/store.py`——三个属性库共用
那一份，这里只给出索引路径、来源文档与载荷包装。

与 knowledge_virtuoso.database.db.core.catalog 平行：db_attr 查设计库对象属性，本模块查 techFile 对象属性。

用法:
  from knowledge_virtuoso.database.techdb.core.catalog import search_tech_attr, build_from_html
"""

import re
import sys
from pathlib import Path
from html import unescape

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import store

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("techdb")

# ─── 类 → 该类的 objType 运行时值 ───
CLASS_OBJTYPE = {
    "viaDefs":                ["stdViaDef", "customViaDef"],
    "viaVariants":            ["stdViaVariant", "customViaVariant"],
    "siteDefs":               ["scalarSiteDef", "arraySiteDef"],
}

# ─── 类 → 简短描述 ───
CLASS_DESC = {
    "techID":                   "techFile 顶层属性",
    "layers":                   "层",
    "derivedLayers":            "衍生层",
    "purposeDefs":              "用途定义",
    "lps":                      "层-用途对 LPP",
    "viaDefs":                  "通孔定义",
    "viaVariants":              "通孔变体",
    "viaSpecs":                 "通孔规格",
    "siteDefs":                 "单元定义",
    "snapPatternDefs":          "吸附模式 (ICADVM18.1)",
    "widthSpacingSnapPatternDefs": "宽距模式 (ICADVM18.1)",
}


def infer_type(desc: str) -> str:
    d = desc.lower()
    if "list of database identifiers" in d or "list of database ids" in d:
        return "l_objId"
    if "the database identifier" in d:
        return "objId"
    if "list of " in d and ("names" in d or "layers" in d or "purposes" in d):
        return "l_string"
    if any(k in d for k in ("true or false", "t or nil", "flag", "whether ")):
        return "boolean"
    if "name of the " in d:
        return "string"
    return ""


_NOISE = {"attribute", "note", "include", "modify", "object", "the"}


def _strip(html: str) -> str:
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _is_name_token(tok: str) -> bool:
    return bool(re.match(r'^[a-z][a-zA-Z0-9]*$', tok)) and tok.lower() not in _NOISE


def parse_section(heading: str, section: str) -> dict:
    """解析单个 h3 节：返回 {class_id, desc, attributes:[{name, desc}]}。"""
    class_id = heading.replace("techID~>", "").rstrip("~> ").strip()
    class_id = re.sub(r'\s*\(.*?\)\s*$', '', class_id).strip()
    if not class_id:
        class_id = "techID"

    desc = ""
    m = re.search(r'<h4[^>]*>\s*<a[^>]*>Description</a>\s*</h4>(.*?)(?=<h4|</body>|<h3)', section, re.DOTALL)
    if m:
        desc = _strip(m.group(1))[:200]

    attrs = []
    am = re.search(r'<h4[^>]*>\s*<a[^>]*>Attributes</a>\s*</h4>(.*?)(?=<h4|</body>|<h3)', section, re.DOTALL)
    if am:
        table_html = am.group(1)
        pending = None
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL):
            tds = [_strip(td) for td in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
            tds = [t for t in tds if t]
            if not tds:
                continue
            first = tds[0].lstrip('*')
            if _is_name_token(first) and len(tds) >= 1:
                if pending:
                    attrs.append(pending)
                pending = {"name": first,
                           "desc": re.sub(r'\s+', ' ', ' '.join(tds[1:])).strip()[:250]}
            else:
                if pending and not pending["desc"]:
                    pending["desc"] = re.sub(r'\s+', ' ', ' '.join(tds)).strip()[:250]
        if pending:
            attrs.append(pending)

    seen = {}
    for a in attrs:
        if a["name"] not in seen:
            seen[a["name"]] = a
    attrs = list(seen.values())

    return {"class_id": class_id, "desc": desc, "attributes": attrs}


def extract_all(doc_path: str) -> dict:
    """从 appA.html 提取所有 tech 类及属性，返回 {classes, attributes}。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')

    classes: dict[str, dict] = {}
    attributes: dict[str, dict] = {}

    h3s = list(re.finditer(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', text, re.DOTALL))
    for i, m in enumerate(h3s):
        heading = _strip(m.group(1))
        if not heading.startswith("techID~>"):
            continue
        end = h3s[i + 1].start() if i + 1 < len(h3s) else len(text)
        section = text[m.end():end]

        parsed = parse_section(heading, section)
        cid = parsed["class_id"]
        if cid not in CLASS_DESC:
            continue

        attr_names = [a["name"] for a in parsed["attributes"]]
        classes[cid] = {
            "name": cid,
            "path": "techID~>" if cid == "techID" else f"techID~>{cid}",
            "desc": CLASS_DESC[cid],
            "objType": CLASS_OBJTYPE.get(cid),
            "attributes": attr_names,
        }

        for a in parsed["attributes"]:
            name = a["name"]
            if name not in attributes:
                attributes[name] = {
                    "name": name,
                    "rw": "?",
                    "type": infer_type(a["desc"]),
                    "desc": a["desc"],
                    "classes": [cid],
                }
            else:
                if cid not in attributes[name]["classes"]:
                    attributes[name]["classes"].append(cid)
                if not attributes[name]["desc"] and a["desc"]:
                    attributes[name]["desc"] = a["desc"]

    return {"classes": classes, "attributes": attributes}


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、载荷包装（本库载荷就是解析结果）。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="techdb_attr",
    lib="techdb",
    doc_parts=("sktechfile", "appA.html"),
    parse=extract_all,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 appA.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def _row(name: str, info: dict) -> dict:
    """本库的行形状：多一列 `classes`（同一属性可属于多个 tech 类）。"""
    return {"name": name, "rw": info.get("rw", "?"), "type": info.get("type", ""),
            "desc": info.get("desc", ""), "classes": info.get("classes", [])}


def search_tech_attr(className: str = "", keyword: str = "") -> list[dict]:
    """按类和关键词搜索 tech 属性。"""
    data = _load()
    attrs = data["attributes"]
    if className:
        found = data["classes"].get(className)
        if found is None:
            return []                      # 没这个类：区别于"有类但筛完没属性"
        names = set(found.get("attributes", []))
    else:
        names = set(attrs)
    return store.query_rows(attrs, names, keyword, _row)


def main() -> None:
    """CLI：从 appA.html 提取 tech 对象属性，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 sktechfile/appA.html 提取 tech 对象属性")
    parser.add_argument("--doc", default=None,
                        help="appA.html 路径 (默认取 VIRTUOSO_DOC_DIR/sktechfile/appA.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    result = build_from_html(args.doc)

    output_path = Path(args.output)
    atomic_write_json(output_path, result)
    print(f"\n已导出到 {output_path}")
    print(f"  classes:     {len(result['classes'])} 个 tech 类")
    print(f"  attributes:  {len(result['attributes'])} 个属性")


if __name__ == "__main__":
    main()
