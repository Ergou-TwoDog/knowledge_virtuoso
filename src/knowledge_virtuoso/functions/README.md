# 函数库设计

本文件随包发布（`knowledge_virtuoso/functions/README.md`），是 **`functions/` 这一层的唯一
设计说明**：分层怎么划、记录长什么样、索引怎么装配、渲染主干怎么取舍。

**范围**：只讲 `functions/` 包内。MCP 接口与构建入口（`server.py`、`cli.py`）不属于本层，
不在这里讲——它们只做接线，接口约定见 README「五个查询工具」。维护对象是包内代码；
索引由解析器生成，**不手工修补 JSON**。

文中标"实测"的数字都来自本机 7667 个官方函数的全量跑（索引 2,220,376 字节，
`schema_version=3`）。**改了代码就该重测**——这些数字是当时的观测，不是承诺。

## 1. 分层：按"变化的原因"分

| 层 | 放什么 | 变化的原因 |
|---|---|---|
| `sources/<来源>/` | 一个来源的全部特异内容：怎么拿到记录（`catalog.py`）、渲染上有什么不同（`render.py`）、身份与顺序（`__init__.py`） | 该来源的获取方式或输出约定变了 |
| `core/` | 与来源无关的技术件：记录契约（`contract.py`）、信封读写（`envelope.py`）、渲染主干（`render.py`） | 记录格式或输出主干变了 |
| `index.py`、`registry.py` | 跨来源的两件事：**装配**（发现 → 合并 → 查询）与**发现规则** | 来源增减、合并语义变了 |

依赖只有一条向下，无横向、无回指：

```
index.py ─→ registry.py ─→ sources/<来源>/ ─→ core/{contract,envelope,render}.py
```

`sources/` 之间**互不认识**；`core/` 不认识任何具体来源（"官方""自定义"这些字样不出现在
`core/` 里，连语料元数据与报错称呼都由来源自己传）。

三个属性库（`database/db`、`techdb`、`cdfdb`）**暂不分来源**，仍是各自的
`core/catalog.py` + `render.py`；它们不支持自定义索引。

### 1.1 来源接口

**加一个来源 = 在 `sources/` 下加一棵树**，`core/`、`index.py`、`registry.py` 一行都不用改
（登记这一步由 `registry.py` 扫描 `sources/` 完成）。

产出方要不要加树是另一回事：**外部的索引产生器读 `core/SPEC.md`**（那是对外的产出规范，
与本文件分开：本文件讲本层内部设计，SPEC.md 讲"你该产出什么"）。

```python
# sources/<来源>/__init__.py
NAME     = "custom"      # 身份
LABEL    = "自定义"       # 警告与报错文案里的称呼（core 与 envelope 都用它，不写死）
REQUIRED = False         # 基准来源 True：不可用时**报错**并尝试从原始材料重建；其余只跳过并警告
ORDER    = 20            # 合并优先级，**大者覆盖小者**
CORPUS   = None          # 写自己索引时的信封元数据；不写索引的来源为 None
def index_paths() -> tuple[str, ...]        # 该来源的索引文件（可多个）
def read(path) -> dict[str, dict]           # 读一份索引（是否要求信封形态由来源自己定）
def rebuild(doc_root) -> tuple[dict, dict] | None   # 从原始材料重建；没有这种能力就 None
def owns(entry) -> bool                     # 这条记录是否属于本来源

# sources/<来源>/render.py
PROFILE  # 本来源的渲染差异（见 §5.8）
```

另有一个**可选**扩展点，不在上面这 10 项里、缺了照常工作：`print_report(entries, report)`
——构建报表的口径（前缀/动词分布）。开发入口的 `--report` 只对 `registry.BASE` 做
"有就调"，没有就原样打报告字典，因此它不必认识任何具体来源。

缺任何一项 → 该树**不加载**（警告并跳过）：宁可不认，也不要一个半残的来源在跑。
`python -m knowledge_virtuoso.functions --sources` 列出发现结果（顺序、角色、索引路径、
语料），用来核对"自动发现"没有漏掉谁。

**`index_paths()` 的路径一律规范化后再用**：经 `_canonical_index_path`（`abspath` +
`normcase`）做**词法**规范化——去重与"这一批源是否换过"都按这个字符串比较，所以
`x/../a.json` 与 `a.json` 是同一份，而**符号链接别名故意保持为不同来源**（不 stat 磁盘、
不热重载）。规范化只为比较，**不是**为了接受相对路径。

custom 来源从 `VIRTUOSO_CUSTOM_INDEX` 取路径（`os.pathsep` 分隔多项；每项是索引文件，
或一个目录——目录收其下全部 `*.json`，非递归、按文件名排序，因此一个目录等于多个来源；
后者覆盖前者，遮蔽写 stderr 警告）。**相对路径按进程工作目录解析，并会打一条 stderr
警告**（附解析后的绝对路径）——`abspath` 不会失败，只会静默指到别处，而工作目录由启动方
决定，所以这条要出声；实际使用建议一律写绝对路径。

### 1.2 三条硬规矩

1. **来源之间不许互相 import。** 需要共享的东西属于 `core/`；跨来源的判断（比如"同一份
   文件不当两个来源"）属装配层 `index.py`，不塞进任何一棵树。
2. **顺序不看目录名。** 合并优先级由 `ORDER` 声明——改目录名不该改变"谁覆盖谁"。
3. **发现失败要响。** 坏树（导入失败/接口不全）跳过时打 stderr 警告，别让它静默消失；
   这也是为什么要有 `--sources`。

### 1.3 四条内容原则

| # | 原则 | 落在哪 / 依据 |
|---|---|---|
| 1 | **索引如实**：内容 ≡ 官方 doc 的节结构；变体与笔误只做归一；不做价值取舍、不做跨节合并 | §2 契约、§3 边界。索引可审计——有争议时能分清是"索引不忠实"还是"输出策略不合适" |
| 2 | **只存不可导出的**：可由别的字段推出的一律不落盘 | §2.1 的"不落盘的字段" |
| 3 | **取舍在渲染层**：哪个节进哪个 `detail` 档由渲染主干（`core/render.py`）的策略表决定，改它零重建 | §5.1。重建一次约 87 秒，而输出策略要反复迭代 |
| 4 | **表示与内容分离**：紧凑 JSON + LF + gzip，语义不变 | §4.3。实测 34.5 MB → 23.85 MB（去缩进）→ 约 2 MB（gzip） |

## 2. 记录契约（v3）

信封：`schema_version`（=3）、`corpus`、`functions`。`corpus` 由**写索引的来源**提供
（官方的 `CORPUS` 是 `{"product": "Cadence IC618", "scope": "official-skill-callables"}`）。

### 2.1 一条记录

| 字段 | 含义 |
|---|---|
| `type` | 记录种类，当前恒为 `function`（结构锚点） |
| `decl` | 声明列表，`[{text, shared_from}]`。`text` 为声明原文（保留原换行）；`shared_from` 非 null 表示该声明取自该共享主题，**不是本函数单独文档化的签名**（如 assoc/assq 取自 assv；全库实测 30 个） |
| `where` | 主来源定位：`file`、`topic`、`marker_text`（保留原官方标记，可能与真实标题不一致）、`anchor`（必须实际存在，用于拼 `<doc 根>/<file>#<anchor>` 回查） |
| `also_at` | 同名补充来源的定位列表（v2 的 `sources[1:]`） |
| `sections` | 见 §2.4。**稀疏**：官方 doc 有哪些节就记哪些 |
| `status` | `active` / `deprecated`（全库实测 10 个）；deprecated 为文本启发式，不能视作产品认证 |
| `field_status` | 16 个规范节名 + `decl`（共 17 键）的解析状态 |

**不落盘的字段**（加载时按函数名重算、或可由其他字段推出，故不存）：`prefix`、`tokens`
（v2 存了，现由函数名重算，7667/7667 一致）；`docset`（= `where.file` 首段目录）；
顶层 `file`（与 `where.file` 同值）；`source.anchors`（官方文档工具生成的页内数字锚点，
单条最多 746 个，与函数用法无关，回查只需单数 `anchor`）；`kind`（存为 `type`）；
`signature`+`signatures`（合并为 `decl`）；`argument_groups[]` 内的参数对象副本
（成员集合与 `lists[].items` 逐一相同）。

### 2.2 `field_status`

恒定覆盖 16 个规范节名 + `decl`。取值：`present`、`text_fallback`、`documented_none`、
`not_documented`、`unparsed`（`decl` 另有 `shared_declaration`）。它记录**解析过程的事实**
（不可由内容导出），是"这一节官网上没有"与"有但解析失败"可分的依据，因此保留。
渲染时不逐条列出 `not_documented`/`documented_none`（那是"官网上没有"，不是异常）。

### 2.3 sections 的 16 个规范节名

标题先归一（大小写、单复数、结尾冒号句点），再映射到规范键；**变体写法全部合并**
（括号内为实测出现次数）：

| 规范键 | 原文标题变体 |
|---|---|
| `description` | description |
| `arguments` | argument、arguments；含 `<br>` 合并标题（见 §3） |
| `returns` | value returned(7165)、values returned(272)、return value(17)、return values(6) |
| `example` | example、examples、example 1/2/3/4/5、example for integrators、`example: …`、`example to …`、`examples of …`、exampleexample（前缀规则覆盖）；全库 6185 个函数有此节 |
| `reference` | reference、references、related topic、related topics、see also；910 个函数有 |
| `related_functions` | related function、related functions；82 个 |
| `prerequisites` | prerequisite、prerequisites；45 个 |
| `additional_information` | additional information（含 `additional information (advanced nodes only)`）；38 个 |
| `interactive_function` | interactive function；21 个 |
| `associated_options` | associated option、associated options；20 个 |
| `option_descriptions` | option description、option descriptions；20 个 |
| `purpose` / `format` / `definition` / `overview` | 同名（本语料各 1～4 例） |
| `errors` | error、errors、error conditions；2 个 |

**已实测的官方标题笔误**作为字面量单独处理，且**不做模糊匹配**——宽松到"标题含 return"
会把 `Example 1 With Returned Value` 这类示例标题误判成返回值小节。当前收录：
`value returned\`、`value returne`、`value returnedz`、`value returned4`、`values return`、
`.value returned`、`value returnedd`。

**节内容形态**：`arguments` 为结构化树（§2.4）；`returns` 为 `{items:[{value,desc}]}`；
`reference` 为 `{text, links:[{text,href}]}`；其余节为 `{text}`，含表格时另给
`items:[{name,desc}]`。多行文本保留换行。

### 2.4 arguments 的嵌套结构（ROD 子参数列表）

ROD 函数的参数分两层：根参数，加上若干"子参数列表"（如 `?subRectArray l_subrectArgs`
的值里可用的参数）。原文把父子关系放在**标题**里——根参数节标题是 `<br><br>` 合并标题
（`Arguments<br><br>Master Path Arguments`），每个子列表是同级的独立 `<h4>`，标题形如
`Subrectangle Arguments (l_subrectArgs)`。

```jsonc
"arguments": {
  "root": { "title": "Master Path Arguments", "items": [ {name, desc, values} ] },
  "lists": [ { "title": "Subrectangle Arguments", "list_type": "l_subrectArgs",
               "parent": { "arg": "?subRectArray l_subrectArgs...",
                           "type": "l_subRectArgs", "match": "case_insensitive" },
               "items": [ {name, desc, values} ] } ]
}
```

- `list_type` 取自标题括号内的 token；`parent` 按该 token 与根参数的类型 token 匹配，
  **忽略大小写**（原文自身存在 `l_subrectArgs` vs `l_subRectArgs`、`l_encSubpathArgs` vs
  `l_encSubPathArgs` 的不一致，`match` 字段标明是 `exact` 还是 `case_insensitive`）；
  命中 0/多处时为 `null`。
- 空列表节（如 `ROD Connectivity Arguments for Polygons`）如实保留，`parent` 为 null。
- `values` 是紧随该参数的**允许取值表**（行首为单个 `'symbol` 字面量，如 `?selectMode`
  后的 `'single/'browse/…`）。带第二个 token 的行（如 `'name t_name`）是属性列表字段，
  不归入取值。
- `...` 不能当"列表参数"标记：本语料仅 16 处，且混用 ROD 列表与 `defmethod(g_exp1 ...)`
  这类变参。

### 2.5 来源扩展位，以及契约现在的松紧（实测）

自定义来源的记录比官方多三处扩展位：`origin`、`origin_meta`、`lint`。契约**不校验**它们
（只按名重算 `prefix`/`tokens`，其余原样透传）。

实测当前契约的边界：

| 输入 | 结果 |
|---|---|
| 缺 `where.file`（`where={}` 或 `file=""`） | **通过**——校验按**类型**、不按存在 |
| `decl` 不是 list、`arguments.items[].desc` 不是字符串 | 拒绝，报错点名路径（`f.sections.arguments.root.items.desc must be str`） |
| `returns.items[]` 缺 `desc` | 拒绝（`…returns.items.desc must be str`）。这处曾**漏检**——能加载，但一渲染就 `KeyError`；契约按"渲染会直接取的键"补齐了 |
| 多带未知键（含 `origin`/`origin_meta`/`lint`） | **通过**——未知键一律放行 |
| 非 v3 信封（`schema_version` 不符） | 拒绝；官方来源另兼容更早的**扁平记录**（`require_envelope=False`），自定义来源强制信封 |

也就是说"同一种格式"目前是**同一种形状**，不是严格 schema。要收紧（`where.file` 非空、
`origin` 与 `origin_meta` 成对）是**行为变化**，得单独定；真加了，落点是
`sources/<来源>/` 里的来源级校验，不是 `core/`。

## 3. 官方来源的解析边界

这一章的每一条都只影响 `sources/official/`。

- **`<br>` 合并标题**：按拆开后的后半部分判定——后半是已识别节名（如
  `Arguments<br>Values Returned`）则视为**两个节**，参数表归 arguments、节尾部非参数表归
  returns；后半不是节名（如 `Arguments<br><br>Master Path Arguments`）则为**节内子范围**，
  记为 `arguments.root.title`。
- **未识别的 h4** 作为所属节的正文子标题保留在该节 `text` 内，不单列成节、也不折进邻节
  语义（v3 落地时实测：5.4% 的 topic 含此类自由子标题）。
- **裸 `<tr>` 续排的表**：老式排版里 `</table>` 之后仍继续出现属于同一张表的 `<tr>`
  （实测 `hiSetCursor` 的光标常量表：前 37 行在 `<table>` 内，其后 55 行以裸
  `<tr><td><p>` 续排）。解析时把同一父节点下连续 ≥3 行、每行 ≥2 个单元格的裸 `<tr>`
  连同行间空白文本节点收进合成 `<table>`，再按常规表格读取；少于 3 行不动，避免把版式行
  当表格。
- **首列被占位的表行**：项目符号图片或 `&nbsp;` 占住首列时内容整体右移一格
  （`['', 'gdmStateCI: File is managed…']`）。这类行按**内容**判定：名称行（单个标识符、
  冒号紧跟标识符、恰好两词且第二词非小写开头、`常量 / 值` 四种形状，且首词不是
  `For`/`When`/`The`/`Note`/`See` 这类普通英文词）照常建条目；其余按说明并入上一条目的
  `desc`——pcreCompile 的"名字一行、说明列下一行"即属此类。这两种排版此前会让整行内容
  只剩纯文本，没有条目。
- **允许取值表**：紧随单行参数表的、行首为 `'symbol` 字面量的表 → 作为该参数的 `values`。
  实测 23 个函数的参数名里混入过这类字面量（如 `digitalHostMode` 的 `'local`/`'remote`），
  其中 22 个是合法的允许取值，不能按"以 `'` 开头就不是参数"一刀切。
- `field_status` 是唯一"非从原文抄来"的字段。HTML 以 UTF-8 容错读取；字体、颜色、图片和
  完整排版不保留。遇到 `not_documented`/`unparsed` 或自然语言约束，应回到
  `<实际 doc 根>/<where.file>#<where.anchor>`，不要根据空列表猜测无参数或无返回。
- 收录范围由代码里的 docset 白名单（`sources/official/catalog.py` 的 `_SKILL_DOC_DIRS`）
  决定，不把其他目录中的配置项、C++ 或示例函数视为官方可调用函数。构建统计用模块入口的
  `--report`（`python -m knowledge_virtuoso.functions --doc-root <doc> --report`）。

**两种老式排版的收益（v3 落地时实测）**：全库仅 51 个函数内容变化，新增 217 条条目**逐字
可追溯原文 `arguments.text`**、0 条编造，旧条目文本无丢失；未展开（正文/条目展平 ≥1.20）由
54 个函数/40,812 字降到 50 个/33,687 字，余下主要是纯散文块——那些**不做条目化**，
硬切会造出 `For` / `Note:` 这类假参数名。

## 4. 装配与加载（跨来源）

### 4.1 发现

`registry.py` 扫描 `sources/` 下的**常规包**（有 `__init__.py` 的目录），逐棵检查接口是否
齐全，按 `ORDER` 排序。非包目录（如未来的纯文档目录）不会被误认；坏树跳过并警告（§1.2）。
**必须有且只有一个基准来源**（`REQUIRED=True`），否则直接报错——没有基准就无索引可查。

### 4.2 合并

- **基准来源恒为第一，且必须可用**：它的索引缺失/损坏/版本不符时，先尝试从 `doc_root`
  （或进程环境里的 `VIRTUOSO_DOC_DIR`）重建并原子写回，仍失败才报错（`IndexLoadError`）。
- **可选来源逐个读**：坏源（缺失、损坏、非信封、契约校验失败）只跳过该源并 stderr 警告，
  不拖垮基准与其余来源。
- **同名覆盖**：可选来源覆盖基准或更早的可选来源；遮蔽写 stderr 警告——二次开发的定位即
  扩展/打补丁，但"掩盖了官方文档"这件事要留痕。
- **同一份文件不当两个来源**：装配时按规范化路径去重（比如环境变量把官方索引也写进来了）。
  这条判断在装配层，不在任何来源树里（§1.2 第 1 条）。
- 未配置任何可选来源时，加载行为与"只用官方索引"逐字一致。

索引只在函数库有多来源；三个属性库不支持自定义索引。

### 4.3 存储形式

紧凑 JSON（无缩进空白）经 **gzip** 压缩落盘（`mtime=0`，同样内容产出同样字节，构建可复现），
落盘约 2 MB。加载时按 gzip 魔数 `1f 8b` 识别并解压；未压缩 JSON 仍兼容。因此**不能用编辑器
直接查看或 grep**，排障用 `gzip -dc <索引> | head`。三个属性库索引体积很小（合计约 100 KB），
仍是明文缩进 JSON。

实测：v2 磁盘 37.23 MB → v3 **2.12 MB（−94%）**；解压 25 ms、JSON 解析 244 ms——冷加载反而
更快，因为读的 I/O 从 25 MB 降到 2 MB。

### 4.4 恢复顺序

查询按**健康内存 → 有效 JSON → 从 doc 构建非空索引、原子写盘、发布内存**；全部失败则报告
实际原因（含索引路径与修复命令），不返回空结果、不发布半成品。默认索引位于平台数据目录
（`VIRTUOSO_DATA_DIR` 可覆盖）下的 `functions/index.json`；**索引不随包分发**。健康检查只查
就绪标志、类型、非空主索引与长度快照，不检测等量篡改或嵌套损坏；索引不进包、改后需重启服务。

## 5. 渲染主干（`core/render.py`）的取舍

### 5.1 五档：哪个节进哪一档

`core/render.py` 的策略表决定节与档的对应（**改它零重建**，索引照收全部节）。渲染层只做
"记录 → 文本"：不 import `mcp`、不读索引、不 import 任何来源、不做 I/O：

| 节 | `digest` | `skel` | `signature` | `brief`（默认） | `full` |
|---|---|---|---|---|---|
| `decl` | 有界（≤320 字，截断标注） | ✅（完整，不截断） | ✅ | ✅ | ✅ |
| `description`（缺 `description` 时用 `definition` 顶） | 仅首句 | | ✅ | ✅ | ✅ |
| `arguments`（root + lists 嵌套渲染 + values） | | 仅「关键字 类型」+ 取值/默认原文 | | ✅ | ✅ |
| `arguments`/`returns` 的**条目之外正文**（消去已渲染条目后的残段） | | | | ✅（截断 600 字并标注） | ✅（全文） |
| `returns` | 仅取值名 | 仅取值名 | | ✅ | ✅ |
| `prerequisites` / `interactive_function` / `associated_options` | | | | ✅ | ✅ |
| `option_descriptions` | | | | 仅指针 | ✅ |
| 参数表**校验行**（签名 `?参数` 与参数表名字对账） | | ✅ | | ✅ | ✅ |
| 签名有 `?参数` 而官方未给参数说明时的说明行 | | | | ✅ | ✅ |
| `example` / `additional_information` / `related_functions` / `reference` / `format` / `purpose` / `overview` / `errors` | | | | | ✅ |
| `status: deprecated` / 共享声明提示 | ✅（标记） | ✅ | ✅ | ✅ | ✅ |
| 来源标记（如自定义函数的名字标记 + 前提行） | ✅（名字标记） | ✅ | ✅ | ✅ | ✅ |
| `field_status` 异常项（中文措辞） | | | | | ✅ |
| `省略:` 指针行 | ✅ | ✅ | | 有省略时 | |

### 5.2 档位依据与体量（实测）

- `digest` 面向"**挑函数**"：横向比较候选，长度与文档体量脱钩——硬上限 900 字，
  全库 **max 793、中位 255**，总 2.06 M。
- `skel` 面向"**写调用**"：签名 + 参数关键字/类型 + 取值/默认原文，不含量词解释。总 2.24 M，
  **max 9,477**（ROD 族：签名不截断、默认值行多）。
- `brief` 放"缺了就写错或写不出调用"的节（前置条件、选项字典、交互式提示）。总 6.04 M，
  max 26,128；>8,000 字的 **15 个**。
- `full` 放澄清语义与导航类。总 8.14 M，max 51,228（`absAbstract`）。
- 比例：`skel` 为 `brief` 的 37%、`digest` 为 34%。**`skel` 不是有界档**，它是按比例的。

### 5.3 输出形式约定（便于程序化切分）

单行项用行内前缀（`函数:`、`签名:`、`描述:`、`来源:`、`解析状态:`、`省略:`），多行块用独占
一行的节标题（`参数:`、`返回:`、`示例:`）——块内条目再缩进一层。两行正则够用：块标题
`^[^ \t].*:$`，块内条目首行 `^ +.+? — `（其后缩进更深的行属于上一条目）。
`主参数组 […]`／`子参数 […]（属于 …）` 标识分组，不与参数条目同级。

搜索页的每一行附的就是同一份 `digest`（`render_search_page` → `digest_of`），所以检索结果
与 `detail="digest"` 看到的是同一种摘要；`digest`/`skel` 都可直接作为 `detail` 用。

### 5.4 省略指针

统一格式 `省略: <省了什么> → detail="X"`（机器可识别前缀 `省略: `）。**任何档位只要省略了
内容，都必须有这一行**，省略的内容一律能在指明的档位里逐字取回。实测全库 24 个函数的
`brief` 带指针。两处现有指针：选项字典
`省略: 选项说明 76 条共 45,951 字 → detail="full" 或 sections=["option_descriptions"]`、
参数块预算 `省略: 参数说明续文 N 条共 X 字 → detail="full"（参数名、允许取值与 Default 已保留）`。

### 5.5 "取值/默认值"的判据只有一个

`\b[Dd]efaults?\b|\b[Vv]alid [Vv]alues?\b|默认|取值`。brief 的参数块预算与 skel 的片段选取
**共用这一个判据**，保证"brief 留下的"与"skel 保留的"不会各说各话。三条实测教训：

1. **大小写与写法都要认**：官方混用 `Default:`、`The default value is 0.`、`By default,`、
   `Defaults to`；只匹大写 `Default` 会让 674 个参数（391 个函数）的默认值在 skel 里消失
   （`abeLayerGrow` 的 `?north`、`abeElapsedTime` 的 `?reset`）。
2. **必须有词边界**：否则 `formDefaultAction`、`g_defaultValue` 这类标识符里的 "Default"
   会被当成事实，凭空保留整行脱节碎片。
3. **首行片段从句子开头截取**（上限 160 字）——`The default value is 0.` 而不是
   `default value is 0.`。

### 5.6 参数块篇幅预算（仅 brief）

参数块超过 12,000 字时，保留每个参数的首行与含 `Default`／`Valid Values`／`取值` 的行，
其余说明续文移入 `full`，块尾显式标注（见 §5.4），**参数名、允许取值与 Default 一条不丢**。
实测只影响 4 个函数（`rodCreatePath` 35,266→**26,128**、`rodCreateRect` 28,913→**18,399**、
`hiCreateAppForm` 16,593→**6,367**、`hiCreateReportField` 15,366→**6,858**）；参数密集但无
长散文的（如 `hnlInitMap`）不触发。

**为什么标注而不静默截断**：续行里约 82% 不是取值/默认值，而是约束类文字
（`The value of x_displayOrder must be an integer…`、`Note: This argument only applies to
type-in fields.`、`Callback parameter list: (o_session r_form r_field)`）——正是"缺了就写错"
那一类，必须让"说明被移到 full 了"这件事显式可见。

### 5.7 其他取舍

- 描述超长在 brief 截断并**标注字符数**，不静默省略。
- 来源写作 `文件[#锚点]`，锚点与函数名相同时不重复。
- 参考链接去锚点（页内 `#787126` 与跨页 `…#PCRE_CASELESS` 都去）并同名去重；跨页链接以
  **方括号**标注所在文件（`strcmp [stringfunc.html]`）——用圆括号会被读成"函数调用"，且与
  同一行里的裸名字形式不一致。正文若只是同一批链接名的罗列，则与链接合并。
- `解析状态` 只列 `text_fallback`/`unparsed`/`shared_declaration` 三种真异常，用中文措辞
  （如 `示例节官方原文未能可靠提取`），不暴露内部字段名与枚举值；已由正文块标题写明状态的节
  不重复列。
- `skel` 里签名**不截断**（实测有 2 个函数签名超 320 字，截断会让签名里的 `?参数` 无处可查）；
  且参数表的 `Default`/`Valid values` 一条不丢（实测 531 个参数的这类事实**只出现在说明首行**，
  所以 skel 从首行里从事实词处截取原文片段，续行整行保留）。两个新档位都只做筛选与空白重排：
  签名去掉空白后与原文逐字相同。
- techdb 的 `rw` 列在该库恒为 `?`，无信息量时省略。
- 参数表校验行、签名有参数而官方未给参数说明、正文残段这些分支的**触发数**（实测）：
  校验行 74 个函数、参数说明缺失 14 个、参数块预算 4 个、选项字典指针 20 个。

### 5.8 来源差异住在来源里

渲染主干收一个 `Profile`（`digest_marks` + `status_line`），由 `registry.profile_for(entry)`
按记录选出来源的那一份。当前两处差异全在 `sources/custom/render.py`：digest 的
`（自定义）` 标记、头部的 `状态: 自定义函数（二次开发），需先 load("…") 才能调用`
（`load()` 取自 `origin_meta.custom.load`）。官方来源的 `PROFILE` 是空配置——它显式声明
"不额外加东西"，好让两边走同一个接缝。

搜索页每行摘要也按记录现取 profile（合并视图里两类条目会同时出现）。

## 6. 版本与兼容性

- `schema_version` = **3**；`decl`/`sections`/`where`/`also_at` 键名、由数组改为
  `{root, lists}` 的 `arguments`、扩展后的 `field_status` 键集，均为**不兼容变化**；
  v2 索引在加载时报错并提示 `knowledge-virtuoso-build functions` 重建。
- **格式**变了会自动判为不兼容并触发重建；**内容**改进不会——已有索引不会自动重建，
  升级后需显式重建一次。
- 包内模块路径的变化（如 `functions/<来源>/` → `functions/sources/<来源>/`）不影响索引
  格式，但会让按旧路径导入的代码失效——包外的调用方要一起改，提交说明里要写明。

## 7. 已知的松处与待办

- `where.file` 可以是空字符串（契约按类型校验）→ 记录可以没有真实来源位置，渲染出的
  `来源:` 行会是空的。
- 未知键一律放行、`origin`/`origin_meta` 从不校验 → 一个来源可以声称 `origin="custom"`
  却不给 `load()`，渲染出一行没有前提的"状态: 自定义函数（二次开发）"。
- `corpus` 只在**写**索引时用到；不写索引的来源（如自定义）`CORPUS` 为 `None`，没有校验
  它是否与自己的记录相符。
- `error` 一类"返回值是散文"的节由 `returns.text` 承载；官方标题笔误 7 例以字面量处理，
  若上游修正可逐条删除。
- **重建路径（`build_entries`）没有直接测试**：只有真跑一次 `knowledge-virtuoso-build
  functions`，或重建到临时文件与在用索引**逐字节比**，才碰得到它（命令见
  `tests/README.md`「覆盖不到什么」）。搬移时 `_NAME_RE`/`_PREFIX_RE` 随契约去了
  `core/contract.py`，引用却留在 `catalog.py`——golden 全绿、查询照常（索引还在），
  而重建与 `--report` 直接 `NameError`，只有真跑一次才暴露。

## 8. 决策留痕（为什么是现在这样）

渲染层的这些取舍不是一次拍出来的：先有一轮针对 101 个函数 × 3 档的审计，随后改用全库实测
（7667 个函数 × 2 档 + 101 个函数逐字回归）。结论留档，便于后续改动不重复踩：

| 项 | 结论与处置 |
|---|---|
| brief 无上界 | `absAbstract` brief 曾 50,958 字（≈full），全在 `option_descriptions`（45,951 字）→ 该节移到 full，brief 给一行指针；`associated_options`（选项名+一行说明）仍留 brief |
| 签名与参数表名字不一致 | 74 个函数（`?cvId`↔`?cdId`、`?beginExt`↔`?beginnExt`、`?recreateAll`↔`?g_recreateAll`）→ 参数块首行输出**校验行**，含疑笔误配对与仅一方有的名字 |
| `解析状态` 措辞 | 曾输出原始 dict（`{"example": "unparsed"}`，134 个函数）→ 改中文措辞、不暴露字段名与枚举值 |
| 参考链接 | 曾泄漏页内数字锚点并重复两遍（`hiCreateTreeTable` 的相关块 2,263 字/14 行）→ 去锚点、同名去重、与正文名字罗列合并，降到 761 字/1 行 |
| 参数文档缺失时静默 | 14 个函数签名有参数而 `arguments: not_documented` → 输出 `参数:（官方未提供参数说明；签名含 N 个 ?参数，见来源原文）` |
| 重复长段落是否折叠 | **不折叠**：`rodCreatePath` 的 4 个 `?prop` 分属根参数表与 3 个子参数列表，`absAbstract` 的 76 条选项说明无重名、无重复长描述——重复来自官方原文，折叠会丢掉"属于哪个子列表"的信息 |
| skel 丢"写在首行句子里的默认值" | **真缺陷**（674 个参数/391 个函数），根因是判据区分大小写、无词边界；已按 §5.5 修正。同时修掉"`formDefaultAction` 被当成事实"的误留，以及 digest 无条件声称省略完整签名 |
| "事实缺失 0 条"的自证 | 复核指出那是**用实现自己的正则验自己**（循环论证）→ 换用与实现不同的判据重验：参数块事实出现次数 brief 5,011 / skel 5,044，**0 个函数 skel 少于 brief** |
| 节标题写法 | 保持"单行项行内前缀、多行块独占一行"，并用 §5.3 的两行正则把切分规则写明 |
| 省 token 方案（分档而不是压缩） | 采纳 `digest`＋`skel`＋统一的 `省略:` 指针＋检索行带摘要。诊断复算确认：brief 的字节不在"散文"，而在**每参数首行**（`rodCreatePath` 首行 17,524 字里 15,802 是描述文字，占 brief 63%）——所以不该压 brief，而是另开档位。**不采纳**"条目行只留第一句"（会剪掉 `Note:`/`must be`/`ignored unless` 这类约束，与"宁可长、不可缺"相反） |
| 诚实性验收（v3 落地时） | 抽样 20 个函数（含 ROD 的 `lists`、`abs*` 的选项节、合并标题、只有 `definition` 的 `pstddev`、`geHiDragFig` 的编号示例）：`sections` 的键与原文识别出的节**零不一致**，各节文本与原文**逐字一致** |
