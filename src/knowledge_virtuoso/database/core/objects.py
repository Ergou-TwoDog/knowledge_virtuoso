#!/usr/bin/env python3
"""属性库共用的**对象模型**：校验、选择器解析、继承合并。

四个库的载荷是同一套形状（见各库的 `core/README.md`）：**顶层、对象层、记录层三层都定了
固定键集**。

    {"version": 5, "lib": "db",
     "objects": {<id>: {"id", "title", "runtime", "section", "desc",
                        "parent", "attrs": [<记录>]}}}

顶层三键见 `PAYLOAD_KEYS`——其中 **`lib` 是类型区分字段**：索引文件自己说得出"我是哪个库
的"，装载时与库名核对（对不上就当损坏，见 `validate_payload`）。

**三层各有一套公共键**（缺则 `null`）。定键的判据是同一条：**能完整保留下、且能加深 LLM
理解与区分每条数据**的字段，不是"今天的代码读不读它"。

对象层 `OBJECT_KEYS`：

    id        我们的归一化键（父指针指向它、选择器解析到它）
    title     原文对这个对象的称呼（db 是表标题、techdb 是 `techID~>x`、cdfdb 是 `g_cdfDataId`）
    runtime   原文自报的运行时名（只有 db 的原文报了）——**选择器词汇**
    section   原文自己的分组（这张表/这个类在哪个 h3 下）
    desc      原文对**这个对象**的说明散文（只有 techdb 的原文有）
    parent    继承指针（只有 db 有）
    attrs     记录列表

记录层 `ATTR_KEYS`：

    name         属性/关系的名字（**查询只筛这一个键**）
    kind         `attr` 还是 `relation`（只有 dd 的原文分这两类，别家恒 `attr`）
    type         类型。db 是原文的 Type 列；techdb/cdfdb 原文没有类型列，是从说明里推的
                 （推法在各库 ②）；dd 原文没给
    rw           读写。db 由原文的 `modify` 收成两值、cdfdb 由散文里的 "not editable" 推；
                 techdb 原文没有读写列；dd 原文没给
    desc         原文对这一条的说明（dd 原文没给）
    modify       db 原文的 Modify 列（`no`/`yes`/`no/yes`）——**原样留着**
    source       cdfdb 的出处（`field` 字段区 / `arg` 实参形式）
    cardinality  关系的基数（只有 dd）；属性为 `null`
    objectTypes  适用对象（只有 dd；原文那张表自带的一列）

**`null` 的含义因此有两种，且都读得出来**：一是**原文没给**（dd 的 `type`/`desc`、
techdb 的 `rw`）；二是**本库没有这个概念**（三库的 `cardinality`）。两条都由上表与各库
`core/decorate.py` 的说明定死，不是随手补的空值。

**"有没有继承"不用旗子标**：没有继承的库，`parent` 全是 `None`，`merged()` 的循环
走一遍就返回自身——退化情形本身就是如实的表示（"该库全是根节点"）。校验同理：
没有父就没有环可查。

**② 允许算，算完就落盘。** 记录层里带"呈现"性质的几个键（db 的 `rw`、techdb/cdfdb 的
`type`、cdfdb 的 `rw`）由各库的 `core/decorate.py` 按固定规则算出后写进记录——因为
**查询那一侧要不认识"哪家有什么"，各家就得在 ② 把话说全**。原文那一侧照旧原样留着
（db 的 `modify`、cdfdb 的 `source`、dd 的 `objectTypes`），两类并列而不互相顶替，所以
"原文怎么写的"与"我们怎么呈现的"都还在索引里，读得出区别。

代价是**改推法必须重建索引**：推法冻结在盘上，不像以前那样下次查询就跟着变。改
`core/decorate.py` 里的规则（或 `ATTR_KEYS` 本身）都要抬载荷版本号并重建，否则盘上留着
旧规则算出的值，看着却是新的。

各库真正不同的只剩两样，且都在库自己那边：

* **解析器**——原文怎么读成对象与记录（四份文档的记法各不相同）；
* **声明**——库名、载荷版本、来源文档、别名表、跨对象口径，以及本库自己的构建期校验
  （各库 `index.py` 里的一份 `Library(...)`，装配由 `core/assembly.py` 出、查询入口由
  `core/query.py` 的 `Query` 出）；
* **渲染声明**——列布局与前后缀是各库自己的表示（一份 `RenderSpec`）。

跨对象（不给选择器）时的口径也各库不同，但它现在是**一句声明**（`LIB.cross`），不再是
各写一遍的一段代码：db/dd 按名去重（`POOL`），techdb/cdfdb 每个对象各一行（`EACH`）
——因为 db 的表**没有"所属对象"列**、dd 的同一条记录本来就摊在多个对象下，分行只会印出
一堆看着重复又分不出归属的行；另两库的表有"所属类"列，分行才读得出归属。
**口径跟着各自的表走。**
"""

from __future__ import annotations

import re

from knowledge_virtuoso.database.core import store

# 对象 id 与属性名的合法形状：**允许大写开头**（`DBUPerUU`、`IOBox` 是原文里的合法名字）。
# 这是**一条规矩**，所以只有一份：各库解析时判"这格子像不像属性名"也用它（`db` 与 `dd`
# 直接 import），别在库里再抄一遍正则——抄了就会在"该不该放大写开头"上分家。
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 载荷顶层的公共键，顺序即落盘顺序。
#
# `lib` 是**类型区分字段**：索引文件凭什么自称"我是哪个库的"。它换来的不只是一句话——
# 装载时拿它与库名/目录名核对（`store.Store._mismatch`），于是"把 db 的索引拷成 dd 的"
# "某棵树放错了地方"这类错**当场炸**，而不是往后某个查询里给出看着正常的结果。
# 它**只打在顶层**：四库 880 多条记录逐条带一个同样的常量，换不到别的东西——把一条记录
# 单独揪出来的场合，你本来就得连着它的顶层一起拿。
PAYLOAD_KEYS = ("version", "lib", "objects")

# 对象字典的公共键，顺序即落盘顺序（`json.dumps` 直接照 dict 顺序写，**顺序变了索引字节就变**）。
OBJECT_KEYS = ("id", "title", "runtime", "section", "desc", "parent", "attrs")

# 记录（`attrs` 里的一条）的公共键，同样**顺序即落盘顺序**。
# 两层各管一段：对象层答"这是谁、挂在哪"，记录层答"这条数据长什么样"。
ATTR_KEYS = ("name", "kind", "type", "rw", "desc", "modify", "source",
             "cardinality", "objectTypes")


def record(name: str, **fields) -> dict:
    """建一条记录：`ATTR_KEYS` 全给，没写的补 `null`。

    各库的 ② 一律用它建记录，免得手写键集时漏一个——漏了会在构建期被
    `validate_objects` 抓住，但那时要翻回解析器找是哪条。`fields` 只收 `ATTR_KEYS`
    里的名字：写错键名在这里就炸，不会静默多出一个没人读的字段。
    """
    unknown = sorted(set(fields) - set(ATTR_KEYS))
    if unknown:
        raise ValueError(f"{name}: 记录里没有这些键 {unknown}（应为 {list(ATTR_KEYS)}）")
    return {"name": name, **{k: fields.get(k) for k in ATTR_KEYS if k != "name"}}


def validate_payload(payload: dict, lib: str) -> None:
    """**整份载荷**的不变量：顶层键集、`lib` 与库名一致、然后是 `validate_objects`。

    构建期与装载期都过这一道（前者在 `assembly.Library.payload`，后者在
    `store.Store._mismatch` 里查前两项——那两样是"这份 JSON 是不是我的"，必须能独立回答）。
    """
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    extra = [k for k in payload if k not in PAYLOAD_KEYS]
    if missing or extra:
        raise ValueError(f"载荷键集不对，缺 {missing}、多 {extra}（应为 {list(PAYLOAD_KEYS)}）")
    if payload["lib"] != lib:
        raise ValueError(f"载荷里的 lib={payload['lib']!r} 与它所在的库 {lib!r} 不符"
                         "（索引放错目录了？）")
    validate_objects(payload["objects"])


def validate_objects(objects: dict) -> None:
    """四家共有的构建期不变量：两层键集、属性名形状、对象内无重名、父可解析、链不成环。

    校验放在**构建**而不是**解析**：解析要能吃半份文档（测试里的 HTML 片段就是一节），
    而一旦要落成索引，这些就得站得住。

    两条**不在这里**，因为它们是库自己的事实：

    * **对象 id 的形状**——db 的 id 是**带空格的表标题**（`Generic Object`、
      `Layer-Purpose Pair`），techdb/cdfdb 的才是标识符（`layers`、`cdfDataId`）；
    * **"每个对象至少一条属性"**——那对 techdb/cdfdb 成立，对 db 不成立
      （Rectangle 之类的"纯转发"对象自身就是 0 条）。
    """
    for oid, obj in objects.items():
        missing = [k for k in OBJECT_KEYS if k not in obj]
        extra = [k for k in obj if k not in OBJECT_KEYS]
        if missing or extra:
            # 这是**唯一同时看见四库载荷**的地方，键集不齐就该在构建期炸掉：
            # 少一个键，使用者要等到某次查询才从 `KeyError` 里发现。
            raise ValueError(f"{oid}: 对象键集不对，缺 {missing}、多 {extra}（应为 {list(OBJECT_KEYS)}）")

    for oid, obj in objects.items():
        for attr in obj["attrs"]:
            missing = [k for k in ATTR_KEYS if k not in attr]
            extra = [k for k in attr if k not in ATTR_KEYS]
            if missing or extra:
                # 同对象层那条：记录层的键集是**查询能一家通吃**的前提
                # （`core/query.py` 只按名字筛，其余字段原样交给各库的渲染声明）。
                raise ValueError(f"{oid}/{attr.get('name')!r}: 记录键集不对，"
                                 f"缺 {missing}、多 {extra}（应为 {list(ATTR_KEYS)}）")

    for oid, obj in objects.items():
        names = [a["name"] for a in obj["attrs"]]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"{oid}: 对象内属性名重复 {dup}")
        bad = [n for n in names if not NAME_RE.match(n)]
        if bad:
            raise ValueError(f"{oid}: 属性名形状不对 {bad[:5]}")

    for oid, obj in objects.items():
        p = obj.get("parent")
        if p is not None and p not in objects:
            # 文档里每个非 root 的对象都有可解析的父；解析不到只可能是**漏收了那张表**，
            # 所以必须炸掉——静默当空会产出"看起来正常的错答案"。
            raise ValueError(f"{oid}: 父对象 {p!r} 不在索引里（原文有表、本解析没收到？）")

    for oid in objects:
        seen, cur = set(), oid
        while cur:
            if cur in seen:
                raise ValueError(f"{oid}: 继承链成环（{cur} 重复出现）")
            seen.add(cur)
            cur = objects[cur].get("parent")


def validate_identifier_objects(objects: dict) -> None:
    """两条**对象 id 是标识符**的库共用的构建期校验（techdb / cdfdb 逐字相同，故收在这儿）：

    * 对象 id 必须是标识符——它们是原文里那种"类名"，不是 db 那种带空格的表标题；
    * 每个对象至少有一条记录——db 允许"纯转发"对象自身 0 条，这两家没有这种对象。

    dd 有自己的三条（关系基数、同名不既当属性又当关系…），那些在它自己的声明里。
    """
    for oid, obj in objects.items():
        if not NAME_RE.match(oid):
            raise ValueError(f"类名形状不对：{oid!r}")
        if not obj["attrs"]:
            raise ValueError(f"{oid}: 一个属性都没解析到（h4 或表结构变了？）")


def resolve(objects: dict, selector: str, aliases: dict | None = None) -> str | None:
    """选择器 → 对象 id。顺序：**精确 id → 原文自报的运行时名 → 忽略大小写与空格 → 兼容别名**。

    别名表由各库自己给（是它自己的选择器词汇，不进索引载荷）。运行时名只有 db 的载荷
    带（原文有 16 张表自报了 `~>objType` 的取值），别的库没有这个字段，
    `runtime_matches` 恒返回 None，等于跳过。
    """
    if not selector:
        return None
    if selector in objects:
        return selector
    hit = runtime_matches(objects, selector)
    if hit:
        return hit
    flat = re.sub(r"[\s_]+", "", selector).lower()
    for oid in objects:
        if re.sub(r"[\s_]+", "", oid).lower() == flat:
            return oid
    return (aliases or {}).get(selector)


def runtime_matches(objects: dict, selector: str) -> str | None:
    """按**原文自报的运行时名**找对象（`obj~>objType` 的取值）。"""
    for oid, obj in objects.items():
        if obj.get("runtime") == selector:
            return oid
    return None


def merged(objects: dict, oid: str) -> dict[str, dict]:
    """`自身属性 ∪ attrs(父)`：子先到先占（**子覆盖父**），并记下每条来自哪一层。

    没有继承的库（`parent` 全为 None）走一遍就返回自身——不需要特判。
    """
    out: dict[str, dict] = {}
    cur, guard = oid, 0
    while cur and guard < 64:
        for attr in objects[cur]["attrs"]:
            if attr["name"] not in out:
                out[attr["name"]] = {**attr, "definedIn": cur}
        cur, guard = objects[cur].get("parent"), guard + 1
    return out


def declared_in(objects: dict) -> dict[str, list[str]]:
    """名字 → 声明它的对象（文档顺序）。供那些表里有"所属对象"列的行用。"""
    out: dict[str, list[str]] = {}
    for oid, obj in objects.items():
        for attr in obj["attrs"]:
            out.setdefault(attr["name"], []).append(oid)
    return out


def query(objects: dict, oid: str, keyword: str, row) -> list[dict]:
    """查**一个对象**的行：合并该对象的属性（无父即自身）→ 关键词过滤 → 组行。"""
    attrs = merged(objects, oid)
    return store.query_rows(attrs, set(attrs), keyword, row)
