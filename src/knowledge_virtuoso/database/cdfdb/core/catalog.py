#!/usr/bin/env python3
"""
knowledge_virtuoso.database.cdfdb.core.catalog — 从 index.json 查询 CDF 对象（cdfDataId / cdfParamId）的 ~> 属性。

本模块只管**本库的内容**：chap21.html 怎么解析成载荷、载荷怎么变成行。索引在哪、怎么读、
坏了怎么从官方 doc 重建（缓存、锁、原子写回）都在 `database/core/store.py`——三个属性库
共用那一份，这里只给出索引路径、来源文档与载荷包装。

与 knowledge_virtuoso.database.db.core.catalog / knowledge_virtuoso.database.techdb.core.catalog 平行：db 查设计库对象属性，techdb 查 techFile 对象属性，
本模块查 CDF 对象属性（独立数据模型，锚定在 cell/library 上）。

用法:
  from knowledge_virtuoso.database.cdfdb.core.catalog import search_cdf_attr, build_from_html

  search_cdf_attr(className="cdfParamId")              → 列出该对象全部属性
  search_cdf_attr(className="cdfParamId", keyword="param")  → 按关键词过滤
  search_cdf_attr(keyword="value")                     → 全部类中搜
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

_DEFAULT_INDEX = index_path("cdfdb")

# ─── 类 → 简短描述 ───
CLASS_DESC = {
    "cdfDataId":  "CDF 描述对象（挂在 cell/library 上，含参数列表）",
    "cdfParamId": "CDF 参数对象（单个器件参数）",
}

# ─── 无独立 h4 小节、但确为 cdfParamId 属性（来自 cdfCreateParam 实参）───
SUPPLEMENT_PARAM_ATTRS = [
    {"name": "name",          "rw": "rw", "type": "string",  "desc": "参数名（亦可通过 cdfDataId~>paramName 访问）"},
    {"name": "parseAsNumber", "rw": "rw", "type": "string",  "desc": "字符串参数是否解析为浮点数（yes/no/don't use）"},
    {"name": "description",   "rw": "rw", "type": "string",  "desc": "参数 tooltip / 描述文本（Edit Properties / Create Instance 表单显示）"},
]


def _strip(html: str) -> str:
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _field_body(text: str, start: int) -> str:
    """从 h4 结束位置取到下一个 h4/h3 或 TOPIC_END 的正文。"""
    nxt = len(text)
    for tag in ('<h4', '<h3', '<!-- [TOPIC_END]'):
        pos = text.find(tag, start)
        if pos != -1:
            nxt = min(nxt, pos)
    return text[start:nxt]


def _extract_h4_field(text: str, fieldname: str) -> dict | None:
    """按字段名提取单个 h4 小节：{name, desc, rw}。"""
    m = re.search(
        r'<h4[^>]*>\s*<a[^>]*>' + re.escape(fieldname) + r'</a>\s*</h4>',
        text)
    if not m:
        return None
    desc = _strip(_field_body(text, m.end()))
    rw = 'ro' if 'not editable' in desc.lower() else 'rw'
    return {"name": fieldname, "desc": desc[:250], "rw": rw}


def _extract_display_table(text: str) -> list[dict]:
    """解析 cdfDataId 的 "Displaying Parameters" 表格（fieldWidth 等）。"""
    m = re.search(
        r'<h4[^>]*>\s*<a[^>]*>Displaying Parameters</a>\s*</h4>'
        r'(.*?)(?=<h4|<h3|<!-- \[TOPIC_END\])',
        text, re.DOTALL)
    if not m:
        return []
    fields = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.DOTALL):
        tds = [_strip(td) for td in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
        tds = [t for t in tds if t]
        if not tds:
            continue
        name = tds[0]
        if not re.match(r'^[a-z][a-zA-Z]+$', name):
            continue
        fields.append({"name": name, "desc": ' '.join(tds[1:])[:250], "rw": "rw"})
    return fields


def _infer_type(name: str, desc: str) -> str:
    d = desc.lower()
    if name == "id":
        return "objId"
    if name == "parameters":
        return "l_objId"
    if name == "choices":
        return "l_string"
    if name in ("paramType", "type", "name", "prompt", "units", "callback"):
        return "string"
    if "list of" in d:
        return "l_string"
    return ""


def extract_all(doc_path: str) -> dict:
    """从 chap21.html 提取 cdfDataId / cdfParamId 的 ~> 属性。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')

    classes: dict[str, dict] = {}
    attributes: dict[str, dict] = {}

    def add_attr(attr: dict, class_id: str):
        name = attr["name"]
        if name not in attributes:
            attributes[name] = {
                "name": name,
                "rw": attr["rw"],
                "type": _infer_type(name, attr["desc"]),
                "desc": attr["desc"],
                "classes": [class_id],
            }
        else:
            if class_id not in attributes[name]["classes"]:
                attributes[name]["classes"].append(class_id)
            if not attributes[name]["desc"] and attr["desc"]:
                attributes[name]["desc"] = attr["desc"]

    # ── cdfDataId 字段 ──
    data_attrs = []
    for fn in ("id", "type", "parameters", "doneProc", "formInitProc"):
        f = _extract_h4_field(text, fn)
        if f:
            data_attrs.append(f)
    data_attrs.extend(_extract_display_table(text))
    for a in data_attrs:
        add_attr(a, "cdfDataId")
    classes["cdfDataId"] = {
        "name": "cdfDataId",
        "desc": CLASS_DESC["cdfDataId"],
        "attributes": [a["name"] for a in data_attrs],
    }

    # ── cdfParamId 字段 ──
    param_attrs = []
    for fn in ("use", "paramType", "defValue", "value", "prompt", "choices",
               "units", "editable", "callback", "dontSave", "parseAsCEL",
               "storeDefault", "display"):
        f = _extract_h4_field(text, fn)
        if f:
            param_attrs.append(f)
    param_attrs.extend(SUPPLEMENT_PARAM_ATTRS)
    for a in param_attrs:
        add_attr(a, "cdfParamId")
    classes["cdfParamId"] = {
        "name": "cdfParamId",
        "desc": CLASS_DESC["cdfParamId"],
        "attributes": [a["name"] for a in param_attrs],
    }

    return {"classes": classes, "attributes": attributes}


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、载荷包装（本库载荷就是解析结果）。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="cdfdb_attr",
    lib="cdfdb",
    doc_parts=("skartistref", "chap21.html"),
    parse=extract_all,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 chap21.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def _row(name: str, info: dict) -> dict:
    """本库的行形状：多一列 `classes`（同一属性可同时挂在 cdfDataId 与 cdfParamId 上）。"""
    return {"name": name, "rw": info.get("rw", "?"), "type": info.get("type", ""),
            "desc": info.get("desc", ""), "classes": info.get("classes", [])}


def search_cdf_attr(className: str = "", keyword: str = "") -> list[dict]:
    """按类（cdfDataId/cdfParamId）和关键词搜索 CDF 属性。"""
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
    """CLI：从 chap21.html 提取 CDF 对象属性，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 skartistref/chap21.html 提取 CDF 对象属性")
    parser.add_argument("--doc", default=None,
                        help="chap21.html 路径 (默认取 VIRTUOSO_DOC_DIR/skartistref/chap21.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    result = build_from_html(args.doc)

    output_path = Path(args.output)
    atomic_write_json(output_path, result)
    print(f"\n已导出到 {output_path}")
    print(f"  classes:     {len(result['classes'])} 个 CDF 对象类")
    print(f"  attributes:  {len(result['attributes'])} 个属性")
    for cid, c in result["classes"].items():
        print(f"    {cid}: {len(c['attributes'])} 属性")


if __name__ == "__main__":
    main()
