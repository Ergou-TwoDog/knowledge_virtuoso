#!/usr/bin/env python3
"""
knowledge_virtuoso.database.cdfdb.core.catalog — 解析 chap21.html，按类查 CDF 对象属性。

原文（`skartistref/chap21.html` 第 21 章 "CDF Functions"）里，CDF 的数据模型是**两个
SKILL 对象类**：`g_cdfDataId`（描述对象，5 个字段 + "Displaying Parameters" 表 4 个）与
`g_cdfParamId`（参数对象，14 个字段）。**没有继承、没有父指针**，两类的属性清单各自平铺。

载荷 = **每个类各存自己那份**：

    {"version": 1, "classes": {cid: {id, desc, attrs: [{name, rw, type, desc, source}]}}}

两个类**零重名**，所以"逐类存储"在这里只统一形状、不改结果（`techdb` 那边就不同了：
它 24 个名字跨类，全局去重会丢东西）。

两处**不在字段区**的属性（`name` / `description`）只有 `cdfCreateParam` 的实参形式，
用 `source: "arg"` 标出来源：`name` 的说明取原文实参说明，`description` 原文**没给说明**
（如实留空，不替它编一句）。

用法:
  search_cdf_attr(className="cdfParamId")              → 列出该类全部属性
  search_cdf_attr(className="cdfParamId", keyword="param")
  search_cdf_attr(keyword="value")                     → 全部类中搜
"""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import store

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DEFAULT_INDEX = index_path("cdfdb")

# 载荷格式版本。v1 = "每个类各存自己的属性"；v2 = 并入 `database/core/objects.py`
# 的共用对象模型（`classes` → `objects`）。
_PAYLOAD_VERSION = 2

# ─── 类的成员：字段区里的 h4 小节 ───
_DATA_FIELDS = ("id", "type", "parameters", "doneProc", "formInitProc")
_PARAM_FIELDS = ("use", "paramType", "defValue", "value", "prompt", "choices",
                 "units", "editable", "callback", "parseAsNumber", "dontSave",
                 "parseAsCEL", "storeDefault", "display")

# ─── 没有独立 h4 小节、只在 `cdfCreateParam` 实参里出现的属性 ───
# 说明取自原文实参表：`?name t_name The name of the parameter.`；
# `?description t_description` **原文没给说明**，所以这里就是空的。
SUPPLEMENT_PARAM_ATTRS = [
    {"name": "name", "desc": "The name of the parameter.", "source": "arg"},
    {"name": "description", "desc": "", "source": "arg"},
]


def _strip(html: str) -> str:
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _h4_index(text: str) -> dict[str, tuple[int, int, str]]:
    """`h4 文本 → (开始, 结束, 所属 h3 小节)`，同名取第一次。

    按**文本**认而不是按 `<h4><a>名字</a></h4>` 这个形状认：原文里
    `parseAsNumber` 的小节写作 `<h4><a name="parseAsNumber"></a><a name="303193">
    parseAsNumber</a></h4>`——**首个锚点是空的**，按形状匹配会整个漏掉它，
    于是它一度只能靠"手写补录"混进来。
    """
    marks = [(m.start(), m.end(), "h3", _strip(m.group(1))) for m in
             re.finditer(r'<h3[^>]*>(.*?)</h3>', text, re.DOTALL | re.IGNORECASE)]
    marks += [(m.start(), m.end(), "h4", _strip(m.group(1))) for m in
              re.finditer(r'<h4[^>]*>(.*?)</h4>', text, re.DOTALL | re.IGNORECASE)]
    marks.sort()
    out: dict[str, tuple[int, int, str]] = {}
    section = ""
    for start, end, kind, name in marks:
        if kind == "h3":
            section = name                     # 字段正文到下一个 h3/h4 为止，够用
        elif name and name not in out:
            out[name] = (start, end, section)
    return out


def _body_after(text: str, end: int) -> str:
    """从 h4 结束位置取到下一个 h4/h3 或 TOPIC_END 的正文。"""
    nxt = len(text)
    for tag in ('<h4', '<h3', '<!-- [TOPIC_END]'):
        pos = text.find(tag, end)
        if pos != -1:
            nxt = min(nxt, pos)
    return text[end:nxt]


def _extract_field(text: str, h4s: dict, fieldname: str) -> dict | None:
    """取一个字段小节的 h4：`{name, desc, rw, source}`；没有返回 None。"""
    found = h4s.get(fieldname)
    if not found:
        return None
    desc = _strip(_body_after(text, found[1]))
    return {"name": fieldname, "desc": desc[:250],
            "rw": 'ro' if 'not editable' in desc.lower() else 'rw',
            "source": "field", "section": found[2]}


def _extract_display_table(text: str, h4s: dict) -> list[dict]:
    """cdfDataId 的 "Displaying Parameters" 表（fieldWidth 等）。"""
    found = h4s.get("Displaying Parameters")
    if not found:
        return []
    fields = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>',
                          _body_after(text, found[1]), re.DOTALL):
        tds = [_strip(td) for td in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
        tds = [t for t in tds if t]
        if not tds or not re.match(r'^[a-z][a-zA-Z]+$', tds[0]):
            continue
        fields.append({"name": tds[0], "desc": ' '.join(tds[1:])[:250],
                       "rw": "rw", "source": "field", "section": found[2]})
    return fields


def _infer_type(name: str, desc: str) -> str:
    """字段记录没有自带类型时**从说明里推**（原文没有类型列）。"""
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
    """从 chap21.html 提取两个 SKILL 对象类各自的属性表，返回索引载荷。"""
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')
    h4s = _h4_index(text)

    def _record(attr: dict) -> dict:
        """记录自带类型优先，推的作兜底。"""
        return {"name": attr["name"], "rw": attr.get("rw", "rw"),
                "type": attr.get("type") or _infer_type(attr["name"], attr["desc"]),
                "desc": attr["desc"], "source": attr.get("source", "field")}

    data_attrs = [f for f in (_extract_field(text, h4s, fn) for fn in _DATA_FIELDS) if f]
    data_attrs.extend(_extract_display_table(text, h4s))

    param_attrs = [f for f in (_extract_field(text, h4s, fn) for fn in _PARAM_FIELDS) if f]
    param_attrs.extend(SUPPLEMENT_PARAM_ATTRS)

    def _object(cid: str, title: str, attrs: list[dict]) -> dict:
        return {"id": cid,
                "title": title,                       # 原文对这个对象的称呼
                "section": attrs[0].get("section", "") if attrs else "",   # 字段所属的 h3 小节
                "parent": None,                       # 本库原文没有继承：全是根节点
                "attrs": [_record(a) for a in attrs]}

    return {"objects": {
        "cdfDataId": _object("cdfDataId", "g_cdfDataId", data_attrs),
        "cdfParamId": _object("cdfParamId", "g_cdfParamId", param_attrs),
    }}


def _validated(payload: dict) -> dict:
    """构建期校验 + 打格式版本（见 `store.Store` 的 `version`）。

    校验放在**构建**而不是**解析**：解析要能吃半页片段（测试夹具就是一小段），
    而一旦要落成索引，类与属性就得站得住。
    """
    objects_mod.validate_objects(payload["objects"])
    for cid, obj in payload["objects"].items():
        # 这两条是本库自己的：类 id 是标识符（不是 db 那种带空格的表标题），
        # 且每个类都该有属性（db 允许"纯转发"对象自身 0 条，本库没有这种对象）。
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', cid):
            raise ValueError(f"类名形状不对：{cid!r}")
        if not obj["attrs"]:
            raise ValueError(f"{cid}: 一个属性都没解析到（h4 结构变了？）")
    return {"version": _PAYLOAD_VERSION, **payload}


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、构建期校验 + 格式版本。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="cdfdb_attr",
    lib="cdfdb",
    doc_parts=("skartistref", "chap21.html"),
    parse=extract_all,
    payload=_validated,
    version=_PAYLOAD_VERSION,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 chap21.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def _row(name: str, info: dict, classes) -> dict:
    """本库的行形状：多一列 `classes`（同名属性可以同时挂在两类上；本库实测零重名）。"""
    return {"name": name, "rw": info.get("rw", "?"), "type": info.get("type", ""),
            "desc": info.get("desc", ""), "source": info.get("source", ""),
            "classes": list(classes)}


def search_cdf_attr(className: str = "", keyword: str = "") -> list[dict]:
    """按类（cdfDataId / cdfParamId）和关键词搜索 CDF 属性。

    不给类时**每个类各出一行**——与 techdb 同一口径（同名属性在不同类里可以是不同字段）。
    选择器解析与继承合并在 `database/core/objects.py`（本库 `parent` 恒为 None，
    合并退化成"取自身"）。
    """
    objects = _load()["objects"]
    declared = objects_mod.declared_in(objects)

    if className:
        cid = objects_mod.resolve(objects, className)
        if cid is None:
            return []                      # 不认识的选择器：区别于"认识但筛完没属性"
        oids = [cid]
    else:
        oids = list(objects)

    rows = []
    for oid in oids:
        rows += objects_mod.query(objects, oid, keyword,
                                  lambda n, a, oid=oid: _row(n, a, declared.get(n, [oid])))
    rows.sort(key=lambda r: (r["name"], r["classes"]))
    return rows


def main() -> None:
    """CLI：从 chap21.html 提取 CDF 对象属性，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 skartistref/chap21.html 提取 CDF 对象属性")
    parser.add_argument("--doc", default=None,
                        help="chap21.html 路径 (默认取 VIRTUOSO_DOC_DIR/skartistref/chap21.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    result = build_from_html(args.doc)
    atomic_write_json(Path(args.output), result)

    print(f"\n已导出到 {args.output}")
    print(f"  classes:     {len(result['classes'])} 个 CDF 对象类")
    for cid, cls in result["classes"].items():
        print(f"    {cid}: {len(cls['attrs'])} 属性")


if __name__ == "__main__":
    main()
