# database/db/core：设计库对象属性

本模块把一个对象的属性表从官方 doc 解析出来、落成索引，并按**对象**回答
"它有哪些属性"。索引存取（读 JSON / 坏了从 doc 重建 / 缓存 / 锁）在
`database/core/store.py`，行形状与文本在 `database/db/render.py`。

唯一来源：`$VIRTUOSO_DOC_DIR/skdfref/attrib.html`
（*Virtuoso Design Environment SKILL Reference* IC6.1.8，第 18 章
*Attribute Retrieval and Modification: Database Access Functions*）。

**下面第一节是原文事实**（写了怎么认，可原样复核），**第二节起是本模块的契约**。

---

## 一、原文是怎么记的

| 事实 | 认法 |
|---|---|
| 一张表 = **表头行 → `Note: include …` 行 → 自己的属性行** | `include` 行固定在第 2 行（表头之后），69 张表无一例外 |
| **每张表最多 1 条 `include`** | 全章没有第二例 → **单父，是树不是图** |
| 父引用的是**另一张表的标题**，不是对象名 | `Note: include Generic Shape Attributes` |
| **写法的大小写／单复数不统一** | `include` 64 张 · `Includes` 4 张 · `includes` 1 张 → **匹配必须大小写不敏感**。漏掉大小写变体会一次丢掉 5 张表，而且毫无征兆（早期就是这么把 4 个 widthSpacing 族误判成"无父的孤立族"的） |
| 对象类型清单**是图片** | `Table 18-1` → `images/attrib.21.1.1.png`，带 `<map name="Jza84bbyEzc_1742003">`，**49 个热区**，每个 `href="#锚点"` 指向一张对象属性表 → **"有哪些对象"机械可解析**，不必人工抄 |
| `include` 行**不是无条件存在** | 7 张表没有（见第三节"根"） |
| 原文有笔误 | `Instance Header Attributes` 写作 `Note: include s Generic Object Attributes`（多一个 `s`） |
| **表头行不可靠** | `Bus Net Definition` / `Bus Terminal Definition` / `Vector Instance Definition` 三张的**表头行只有 3 格**（缺 `Type` 标签），但**数据行仍是 4 格**。判断列数要看数据行，别读表头 |
| `~>?` 的语义 = 本模块要做的事 | 原文："The list of attributes is based on the database object's type" —— **继承表就是官方对"这个对象有哪些属性"的定义** |

## 二、对象模型（本模块的契约）

```
对象 = {
  id:       "Marker"             # 表标题去掉 " Attributes"；**内部主键，父指针指向它**
  运行时名: "marker" | 未知       # 只是**选择器词汇**（第四节：52 个里只有 12 个有文档依据）
  父:       "Generic Object" | None     # id；**绝不能是运行时名**
  自身属性: [ { 名, 类型, 读写, 描述, 定义处 } ]
}

attrs(x) = 自身属性(x) ∪ attrs(父(x))      # 父为空即止
```

**父指针只能用 id（表标题），不能用运行时名**：链条由 `Note: include <表标题>` 定义，
69 条边一条不缺；而运行时名有 40 个对象文档根本没写，**7 个抽象族更是一个都没有**
（`Generic Figure` 之类的名字不会出现在任何 `objType` 行里）。缺名字只影响
"用户怎么开口问"，不影响链条本身。

### 为什么必须**逐对象**存自身属性，而不是全局按名去重

实测：**39 个属性名在不同对象里 `(Modify, Type)` 不同**，例如

```
bitOrder    Bus Net Definition=string · Bus Terminal Definition=integer · Vector Instance Definition=integer
instHeader  Generic anyInst=objId · Mosaic=string
height      float(Label/SiteDef) · integer(Dot) · yes/float(Stipple)
layer       integer · string · yes/string（四种对象各不同）
```

一张全局表"名 → 一条记录 + 它属于哪些对象"**表达不了这些差异**，只会静默留下其中一个。

### 记录的粒度：索引存事实，合并在查询时做

* **索引如实记录每张表自己的全部行**，包括与祖先同名的那些——**被覆盖的行不删**。
  它们是这个对象的**事实**，删了就没法解释"这里为什么有一条同名的"。
* **继承来的属性不落盘**，查询时算（与函数侧"派生键在加载时重算"同一套路），
  因此索引里**不需要** `_generic` 这类合成标签。
* **同名去重发生在"合并"这一步**（`attrs(x) = 自身属性(x) ∪ attrs(父(x))`），
  **不在渲染层**：`render.py` 的契约是"行 → 文本"，不该知道继承。

### 同名怎么办：子覆盖父（按位置，不按长度）

原文里父子同名**只出现过一种：`objType`**（15 处），而且**每一处都是子更具体**：

```
Generic Object :  The name of the object's type.                ← 只讲含义
Cellview       :  Type of the object, in this case "cellview".  ← 给出取值
```

文档的"特化"手段就是**在子表里重声明**，**取值只写在子表那一行里**。所以取**子**，
不是取父。也**不是"取更长的那条"**——实测 7 处父的泛化文本反而更长：

| 对象 | 子表说明 | 继承来的 | 「更长者胜」的结果 |
|---|--:|--:|---|
| `prBoundary` | 29 字 | 30 字 | 丢了 `"PRBoundary"` |
| Color / Display / Layer / Line Style / Stipple / Two-Layer | 27–31 字 | 93 字 | 全丢 |

* 每条属性记 **`定义处`**，否则查出来不知道是哪一层给的。
* **最大深度 3**，递归开销可忽略。

## 三、树的规模

**76 个节点 / 69 条边 / 7 个根 / 最大深度 3。**

| 角色 | 数量 | 说明 |
|---|--:|---|
| 根（无父） | 7 | 2 个带子（`Generic Object`、`Generic Technology File Object`）+ 5 个单节点树 |
| 抽象中间层（有父有子） | 7 | `Generic Figure / Shape / anyInst / Boundary / Blockage / Via / Via Header` |
| 叶子（有父无子） | 62 | 52 个设计库对象 + 6 个技术文件对象 + 4 个 widthSpacing 族 |

**关键：9 个"有子"的节点全部是抽象族，零个具体对象被继承** → 这棵树只有
2~3 层，不存在"对象继承对象"。

```
7 棵树：Generic Object(64 节点) · Generic Technology File Object(7)
       · 5 个单节点：Technology File · Via Spec · Via Def(standard)
         · Via Def(custom) · SiteDef

深度：0→7  1→42  2→15  3→12（11 个形状 + Instance）
```

**4 张表是"纯转发"**——表里只有表头行和 include 行，自身 **0 条**属性，
全部靠继承：`Rectangle`、`Ellipse`、`Standard Via Header`、`Custom Via Header`。
解析器必须容忍"表里除 include 什么都没有"。

主树（设计库）的层级：

```
Generic Object
├─ Generic Figure ─┬─ Generic Shape ──── 11 个形状（Arc Donut Dot Ellipse Label
│                  │                     Line Path pathSeg Polygon Rectangle TextDisplay）
│                  ├─ Generic anyInst ── Instance
│                  └─ Row
├─ Generic Boundary ── Area Boundary · Cluster Boundary · prBoundary · Snap Boundary
├─ Generic Blockage ── Area Blockage · Area Halo · Layer Blockage · Layer Halo
├─ Generic Via      ── Standard Via · Custom Via
├─ Generic Via Header ── Standard Via Header · Custom Via Header
├─ 直挂 Object 的 27 个：figGroup Route Guide Steiner Pin Mosaic Row Header Marker
│  Layer Header Layer-Purpose Pair Cluster Instance Header Track Pattern Signal Group
│  Group Member Net Instance Terminal Terminal BusNetDef BusTermDef VectorInstDef
│  Property Cellview GCellPatterns Custom viaVariant Standard viaVariant
└─ 4 个 widthSpacing 族（直挂 Object，**自己没有子**）：
   Generic widthSpacingPattern · widthSpacingPatternGroup
   · relatedSnapPattern · widthSpacingSnapPatternDef
```

**本文件不写每张表的属性条数**：那要由解析器算，不该在文档里断言（早期手抄过一版，
后来发现正则数不准——2 字符名 `xy`/`uX`/`uY` 和 `name` 都会被漏掉）。

## 四、运行时名（`~>objType` 的取值）从哪儿来

**18 张表在自己的 `objType` 行里直接写明了字符串**，其中 16 个给具体值：

```
cellview · pin · term · label · areaBlockage · layerBlockage · clusterBoundary
PRBoundary · snapBoundary · techFile · layer · display · color · stipple
lineStyle · twoLayer
```

再加正文例子里出现过的 `pathSeg`、`prop`、`rowHeader`，**共 19 个有据可查**
（认法：`objType` 行里 `Type of the object: "…"`）。

两个坑：`PRBoundary` **大写开头**；`Technology File` 写的是 `" techFile"`
（引号内**带前导空格**），取值要 strip。

**但"有哪些取值"文档只给了一半**：18 张表里 16 个自报了具体值（其中 7 个属技术文件表），
加正文例子里的 3 个，**52 个设计库对象里只有 12 个的取值在文本里**。对照本库现状：

| | 数量 |
|---|--:|
| 文档明文写了取值 | 12 |
| 代码手写了名字（`OBJTYPE_MAP` + 形状表） | 31 |
| 两边都有 | 6 |
| **代码猜的（无文档依据）** | **25** |
| **既无文档、代码也没写 → 连选择器都没有** | **21** |

已知至少一处猜错：代码把 `BusDef` **一个名字同时给了三张表**——
Bus Net Definition / Bus Terminal Definition / Vector Instance Definition，
文档从没说过它们同属一个 objType。

其余 40 个对象的取值只能对着 Table 18-1 的图确认（49 个热区，可逐个锚点解析）。

## 五、解析与装配规则

1. **根有 7 个，终止条件是"父为空"**，不是"到达 `Generic Object`"。
   写死后者会让另外 5 棵单节点树报错或死循环。
2. **"表标题 → 运行时名"要显式存在**且可核对（第四节给了一半）。
3. **子覆盖父，每条属性记 `定义处`**。
4. **`include` 解析不到表 → 构建期失败。** 不许写成
   `map.get(父, [])` 那种"查不到就当空"：文档里每个族都有属性表，
   空只可能是"我们没做"，静默跳过会产出**看起来正常的错答案**。
5. **别用表头行判断列数**（三张表头只有 3 格）。
6. **匹配 `include` 要大小写不敏感**（`include` 64 · `Includes` 4 · `includes` 1），
   且要容忍 `include s Generic Object Attributes` 这种多一个 `s` 的笔误。
7. **属性名不都是小写开头**：`DBUPerUU`、`IOBox` 是合法的属性名，
   正则不能要求 `^[a-z]`。
8. **名字格里的 `<br>` 有两种含义**，只能靠语义分辨：
   * **折行**——`modifiedButNot<br>Saved` 是**一个**属性 `modifiedButNotSaved`
   * **一行两名**——`startConn<br>endConn` 是**两个**属性（共享一条描述）
   转文本会把 `<br>` 变空格，于是折行的那种会被"名字只能是小写字母数字"的规则
   误杀（现行代码就丢了 `modifiedButNotSaved`）。

## 六、实现要点：每个坑的由来

规则不是凭空定的，每条都对应一个真实踩过的坑（重构前的代码在这里摔过）：

| 坑 | 后果 | 现在的做法 |
|---|---|---|
| 用**噪声词表**丢"不是属性名的行" | 表里有 `name`、`value`，被词表连带吃掉（`name` 只剩硬编码那份，`value` 直接没有） | 不用词表。表头行、`include` 行各按**位置与句式**认，其余表里有什么就是什么 |
| 名字正则写成 `^[a-z]…` | `DBUPerUU`（Cellview）、`IOBox`（prBoundary）被拒 | 允许大写开头：`^[A-Za-z][A-Za-z0-9_]*$` |
| `<br>` 转文本变成空格 | `modifiedButNotSaved` 被当非法名丢掉 | 名字格按 `<br>` 分段，再按大小写交界判"折行/两名"（规则 8） |
| 按**节**打标签 | 6 个节里有 17 张表，`net` 把 5 张表混成 36 行；`prop` 自己那 7 条被打到 `group` | 一律按**表**建对象，节只作为 `section` 字段记下来 |
| 手写 `GENERIC_ATTRS` 里塞中文自撰描述 | 比官方英文长，按"取更长者胜"把**原文覆写**了 | 描述一律取自原文；合并按位置（子覆盖父），不按长度 |
| 祖先族没收录时 `map.get(父, [])` | 静默当空 → `stdVia` 应有 35 条只给出 **3** 条，看着还像正常结果 | 构建期校验（规则 4），父认不出直接失败 |
| 覆盖率靠手抄 | 52 个对象只抄了 24 个继承条目、31 个名字 | 全章 76 个对象**全部**解析出来；运行时名也只取原文自报的那 16 个 |

## 七、载荷与版本

索引载荷 = `{"version": 2, "objects": {id: {…}}}`（见 `_PAYLOAD_VERSION`）。
**v2 起，这套容器与 `database/core/objects.py` 的共用对象模型对齐**——校验、选择器解析、
继承合并都在那份共享件里，本模块只剩解析器、别名表与行工厂。

**这是一次不兼容变更**：旧载荷是"全局按名去重 + `expanded` 展开表"。用户机器上留着旧
索引时，读出来只是个形状不对的 dict，后面的代码会在某个 `KeyError` 上莫名其妙地炸——
所以 `store.Store` 加了 `version`：**版本不符即当作损坏**，有 `VIRTUOSO_DOC_DIR` 就自动重建，
没有就明确报"索引不可用"。

## 八、还没定的

1. **11 张技术文件表**（Layer / Display / Color / Stipple / Line Style / Two-Layer /
   Technology File / Via Spec / Via Def(std) / Via Def(custom) / SiteDef）
   归本库还是归 techdb？倾向 **techdb**——与 `sktechfile/appA.html` 是同一个技术库
   （本章那节的入口原文即 `techFileID = techGetTechFile(libFileID); techFileID~>??`）。
   现在它们照章解析进来、并带 `section: "Technology File Attributes"`，**将来要挪只需按
   `section` 过滤，不用重新解析**。
2. 4 个 widthSpacing 族（`Generic widthSpacingPattern` 等）是 `Generic Object` 的子、
   没有子，`skdfref/wsp.html` 里也**只有函数没有属性表**。算"没有子对象的族"还是算对象？
   倾向后者（`dbCreateWidthSpacingPattern` 返回的确实是 dbObject）。不影响解析，只影响呈现。
3. 另外 40 个对象的运行时名原文没写（第四节）。现在的办法是**表标题当主入口**＋
   一张明确标注的**兼容别名**小表（`_ALIASES`，只有 9 条，且只收指向唯一对象的——
   `busDef` 对应三张表、`viaHeader` 对应两张，都不收，免得"猜一个"变成静默错答案）。

---

**测试**：`tests/knowledge_virtuoso/database/db/`——检索用 `core/fixtures/search.json`
（手写的对象载荷与期望），解析用 `core/fixtures/html/` 的官方 doc 片段（该目录自带 README
说明片段出处），另有一组自造 HTML 钉住规则 2/6/7/8 那几处脆技巧。
