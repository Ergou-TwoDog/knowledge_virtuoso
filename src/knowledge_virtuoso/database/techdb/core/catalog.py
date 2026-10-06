#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.core.catalog — 从 index.json 查询 tech 数据库对象类及其 ~> 属性。

查询只读取 JSON；索引缺失或损坏时报错。可显式调用构建入口从 appA.html 重建。

与 knowledge_virtuoso.database.db.core.catalog 平行：db_attr 查设计库对象属性，本模块查 techFile 对象属性。

用法:
  from knowledge_virtuoso.database.techdb.core.catalog import search_tech_attr, build_from_html
"""

import os
import re
import json
import sys
from pathlib import Path
from html import unescape
from threading import RLock

from knowledge_virtuoso._paths import atomic_write_json, index_path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("techdb")

_data: dict | None = None
_lock = RLock()

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


def build_from_html(doc_path: str | None = None) -> dict:
    """从 appA.html 解析，返回与 JSON 相同结构的 dict。"""
    if doc_path is None:
        doc_root = os.environ.get("VIRTUOSO_DOC_DIR")
        if not doc_root:
            raise FileNotFoundError(
                "index.json 缺失，且 VIRTUOSO_DOC_DIR 未设置，无法重建。"
                "请设置 VIRTUOSO_DOC_DIR 或运行 knowledge-virtuoso-build techdb")
        doc_path = os.path.join(doc_root, "sktechfile", "appA.html")

    if not Path(doc_path).exists():
        raise FileNotFoundError(f"文档不存在: {doc_path}，请检查 VIRTUOSO_DOC_DIR 环境变量")

    return extract_all(doc_path)


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
            f"techdb_attr 索引不可用: {_DEFAULT_INDEX} ({primary})。"
            f"设置 VIRTUOSO_DOC_DIR 后可自动从官方 doc 重建，或运行: knowledge-virtuoso-build techdb"
        ) from primary
    print(f"techdb_attr 索引缺失/损坏 ({_DEFAULT_INDEX}): {primary}；从 {doc_root!r} 重建", file=sys.stderr)
    payload = build_from_html()
    atomic_write_json(_DEFAULT_INDEX, payload)
    return payload


def search_tech_attr(className: str = "", keyword: str = "") -> list[dict]:
    """按类和关键词搜索 tech 属性。"""
    d = _load()
    attrs = d["attributes"]

    if className:
        cls = d["classes"].get(className)
        if cls is None:
            return []
        names = set(cls.get("attributes", []))
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
                "type": info.get("type", ""),
                "desc": info.get("desc", ""),
                "classes": info.get("classes", []),
            })
    return results


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
