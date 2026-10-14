#!/usr/bin/env python3
"""
knowledge_virtuoso.database.techdb.core.catalog — 解析 appA.html，按**类**查询 tech 属性。

原文（`sktechfile/appA.html` 附录 A）的形状：**每个 `techID~>X` 小节 = 一个类**，
小节里一张 `Attributes` 表 = 该类自己的属性（2 列：属性名 | 说明；说明折行会变成
独立的续行）。**没有继承、没有父指针**——每个类的清单是平铺写全的。

所以载荷 = **每个类各存自己那份**：

    {"version": 1, "classes": {cid: {id, title, desc, attrs: [{name, type, desc}]}}}

**为什么不能"全局按属性名去重"**（本库 0.3.0 之前就是这么存的）：实测有 **24 个属性名
挂在多个类下**，而同一个名字在不同类里说明与类型可以不同（`name` 在 9 个类里各有一句
自己的说明）。按名去重只会静默留下第一个类的——`snapPatternDefs~>layer` 因此被显示成
`l_objId`，而该类原文 "A list of layers on which…" 推出来是 `l_string`。

载荷里**不存 `rw`**：原文没有读写列，`?` 是"无信息"的表示，属于行形状（见 `_row`）。
`type` 是**从该类自己的说明里推的**（`infer_type`），推不出来就是空串——不是文档给的。

索引存取见 `database/core/store.py`；行 → 文本见 `../render.py`。
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

_DEFAULT_INDEX = index_path("techdb")

# 载荷格式版本。v1 = "每个类各存自己的属性"（此前是全局按名去重）；
# v2 = 并入 `database/core/objects.py` 的共用对象模型（`classes` → `objects`）。
_PAYLOAD_VERSION = 2

# 选择器的**兼容别名**：这些 objType 取值（如 `stdViaDef`）在原文里只出现在正文与输出
# 例子里（`tfid~>viaDefs~>objType => ("stdViaDef" …)`），抽不成表，所以**不进索引载荷**
# ——索引只放解析器读出来的事实——只作用于查找入口。要"纯粹按文档"就清空这张表。
_ALIASES = {
    "stdViaDef": "viaDefs",
    "customViaDef": "viaDefs",
    "stdViaVariant": "viaVariants",
    "customViaVariant": "viaVariants",
    # 原文两处写法不一致：siteDefs 表里写的是复数的 scalarSiteDefs / arraySiteDefs，
    # 而 elsewhere 用单数。两种都收。
    "scalarSiteDef": "siteDefs",
    "arraySiteDef": "siteDefs",
    "scalarSiteDefs": "siteDefs",
    "arraySiteDefs": "siteDefs",
}

_NOISE = {"attribute", "note", "include", "modify", "object", "the"}


def _strip(html: str) -> str:
    t = unescape(re.sub(r'<[^>]+>', ' ', html))
    t = t.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _is_name_token(tok: str) -> bool:
    """表首列像不像属性名。

    **形状偏脆**：`^[a-z]` 拒大写开头的名字、`_NOISE` 是词表——两者都可能误伤（`db` 那边
    就吃过亏：`DBUPerUU` 与 `value` 被吃掉）。本文档里实测无误伤，故暂不动；真要改，
    应先把 `_NOISE` 换成"位置规则"（表头行、`include` 行按位置认）再动正则。
    """
    return bool(re.match(r'^[a-z][a-zA-Z0-9]*$', tok)) and tok.lower() not in _NOISE


def infer_type(desc: str) -> str:
    """从**该类自己的说明文字**里推类型；推不出返回 ``""``。

    这是本库的弱信号——原文的 Attributes 表只有"属性名 | 说明"两列，没有类型列。
    """
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


def parse_section(heading: str, section: str) -> dict:
    """解析单个 `techID~>` 小节 → `{id, desc, attrs: [{name, desc}]}`。

    `desc` 取原文自己的 `Description` 小节（不是手写的类说明）。
    """
    class_id = heading.replace("techID~>", "").rstrip("~> ").strip()
    class_id = re.sub(r'\s*\(.*?\)\s*$', '', class_id).strip()
    if not class_id:
        class_id = "techID"

    desc = ""
    m = re.search(r'<h4[^>]*>\s*<a[^>]*>Description</a>\s*</h4>(.*?)(?=<h4|</body>|<h3)',
                  section, re.DOTALL)
    if m:
        desc = _strip(m.group(1))[:200]

    attrs = []
    am = re.search(r'<h4[^>]*>\s*<a[^>]*>Attributes</a>\s*</h4>(.*?)(?=<h4|</body>|<h3)',
                   section, re.DOTALL)
    if am:
        pending = None
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', am.group(1), re.DOTALL):
            tds = [_strip(td) for td in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
            tds = [t for t in tds if t]
            if not tds:
                continue
            first = tds[0].lstrip('*')
            if _is_name_token(first):
                if pending:
                    attrs.append(pending)
                pending = {"name": first,
                           "desc": re.sub(r'\s+', ' ', ' '.join(tds[1:])).strip()[:250]}
            else:
                # 说明折行成的续行：并进上一条（仅当上一条还没有说明）
                if pending and not pending["desc"]:
                    pending["desc"] = re.sub(r'\s+', ' ', ' '.join(tds)).strip()[:250]
        if pending:
            attrs.append(pending)

    seen = {}
    for a in attrs:
        seen.setdefault(a["name"], a)
    return {"id": class_id, "desc": desc, "attrs": list(seen.values())}


def extract_all(doc_path: str) -> dict:
    """从 appA.html 提取每个 `techID~>` 类的自身属性表，返回索引载荷。

    **类集合来自标题**，不靠手写白名单：文档里有几个 `techID~>` 小节就有几个类。
    """
    text = Path(doc_path).read_text(encoding='utf-8', errors='ignore')

    objects: dict[str, dict] = {}
    h3s = list(re.finditer(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h3>', text, re.DOTALL))
    for i, m in enumerate(h3s):
        heading = _strip(m.group(1))
        if not heading.startswith("techID~>"):
            continue
        end = h3s[i + 1].start() if i + 1 < len(h3s) else len(text)
        parsed = parse_section(heading, text[m.end():end])
        cid = parsed["id"]
        objects[cid] = {
            "id": cid,
            "title": "techID~>" if cid == "techID" else f"techID~>{cid}",
            "section": None,          # 本附录里没有更有用的分组（类就是 h3 本身）
            "desc": parsed["desc"],   # 原文自己的 Description 小节
            "parent": None,           # 本库原文没有继承：全是根节点
            "attrs": [{"name": a["name"], "type": infer_type(a["desc"]), "desc": a["desc"]}
                      for a in parsed["attrs"]],
        }
    return {"objects": objects}


def _validated(payload: dict) -> dict:
    """构建期校验 + 打格式版本（见 `store.Store` 的 `version`）。

    校验放在**构建**而不是**解析**：解析要能吃半页片段（测试里的夹具就是一小节），
    而一旦要落成索引，类与属性就得站得住。
    """
    objects_mod.validate_objects(payload["objects"])
    for cid, cls in payload["objects"].items():
        # 这两条是本库自己的：类 id 是标识符（不是 db 那种带空格的表标题），
        # 且每个类都该有属性（db 允许"纯转发"对象自身 0 条，本库没有这种对象）。
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', cid):
            raise ValueError(f"类名形状不对：{cid!r}")
        if not cls["attrs"]:
            raise ValueError(f"{cid}: 一个属性都没解析到（h4 或表结构变了？）")
    return {"version": _PAYLOAD_VERSION, **payload}


# 本库交给共用索引存取的配置：位置、称呼、来源文档、解析、构建期校验 + 格式版本。
_STORE = store.Store(
    index_path=_DEFAULT_INDEX,
    label="techdb_attr",
    lib="techdb",
    doc_parts=("sktechfile", "appA.html"),
    parse=extract_all,
    payload=_validated,
    version=_PAYLOAD_VERSION,
)


def build_from_html(doc_path: str | None = None) -> dict:
    """从 appA.html 解析，返回与 JSON 相同结构的 dict。"""
    return _STORE.build(doc_path)


def _load() -> dict:
    """索引载荷（进程内缓存；缺失或损坏时从官方 doc 重建）——查询都从这里取。"""
    return _STORE.load()


def _row(name: str, info: dict, classes) -> dict:
    """本库的行形状：多一列 `classes`。

    `classes` 是**查询时算的**"哪些类都声明了这个名字"（原文会在每个类里各列一遍），
    而 `type`/`desc` 取自**被查的那个类**——这正是按名去重做不到的。
    `rw` 原文没有读写列，恒为 `?`（"无信息"），渲染层据此决定藏不藏该列。
    """
    return {"name": name, "rw": "?", "type": info.get("type", ""),
            "desc": info.get("desc", ""), "classes": list(classes)}


def search_tech_attr(className: str = "", keyword: str = "") -> list[dict]:
    """按类和关键词搜索 tech 属性。

    不给类时**每个类各出一行**（同一名字在不同类里类型可能不同，合并成一行只会静默
    挑一个——那正是本库重构要除掉的毛病）。选择器解析与继承合并在
    `database/core/objects.py`（本库 `parent` 恒为 None，合并退化成"取自身"）。
    """
    objects = _load()["objects"]
    declared = objects_mod.declared_in(objects)

    if className:
        cid = objects_mod.resolve(objects, className, _ALIASES)
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
    """CLI：从 appA.html 提取 tech 对象属性，重建 index.json。"""
    import argparse
    parser = argparse.ArgumentParser(description="从 sktechfile/appA.html 提取 tech 对象属性")
    parser.add_argument("--doc", default=None,
                        help="appA.html 路径 (默认取 VIRTUOSO_DOC_DIR/sktechfile/appA.html)")
    parser.add_argument("--output", default=str(_DEFAULT_INDEX), help="输出 JSON 路径")
    args = parser.parse_args()

    result = build_from_html(args.doc)
    atomic_write_json(Path(args.output), result)

    print(f"\n已导出到 {args.output}")
    print(f"  classes:     {len(result['classes'])} 个 tech 类")
    print(f"  attributes:  {sum(len(c['attrs']) for c in result['classes'].values())} 条自身属性")


if __name__ == "__main__":
    main()
