# IC618 官方函数索引：字段映射与设计（v3）

本文件随包发布（`knowledge_virtuoso/functions/data/mapping.md`），讲清三件事：
**索引里存什么**、**为什么这么存**、**MCP 工具层怎么取舍后交给 LLM**。
维护对象是包内解析器（`functions/core/catalog.py`）与服务入口（`server.py`）；
索引由解析器生成，不手工修补 JSON。

## 1. 设计原则

| # | 原则 | 依据 |
|---|---|---|
| 1 | **索引如实**：内容 ≡ 官方 doc 的节结构；变体与笔误只做归一；不做价值取舍、不做跨节合并 | 索引可审计；有争议时能分清是"索引不忠实"还是"输出策略不合适" |
| 2 | **只存不可导出的**：可导出的一律不落盘 | 逐项实测（见"不落盘的字段"） |
| 3 | **取舍在工具层**：哪个节进哪个 `detail` 档由 `server.py` 的策略表决定，改它零重建 | 重建一次约 87 秒，而输出策略要反复迭代 |
| 4 | **表示与内容分离**：紧凑 JSON + LF + gzip，语义不变 | 实测 34.5 MB → 23.85 MB（去缩进）→ 约 2 MB（gzip） |

## 2. 一条记录

结构为 v3：`schema_version`（=3）、`corpus`、`functions`。

| 字段 | 含义 |
|---|---|
| `type` | 记录种类，当前恒为 `function`（结构锚点） |
| `decl` | 声明列表，`[{text, shared_from}]`。`text` 为声明原文（保留原换行）；`shared_from` 非 null 表示该声明取自该共享主题，**不是本函数单独文档化的签名**（如 assoc/assq 取自 assv） |
| `where` | 主来源定位：`file`、`topic`、`marker_text`（保留原官方标记，可能与真实标题不一致）、`anchor`（必须实际存在，用于拼 `<doc 根>/<file>#<anchor>` 回查） |
| `also_at` | 同名补充来源的定位列表（v2 的 `sources[1:]`） |
| `sections` | 见下。**稀疏**：官方 doc 有哪些节就记哪些 |
| `status` | `active` / `deprecated`；deprecated 为文本启发式，不能视作产品认证 |
| `field_status` | 16 个规范节名 + `decl`（共 17 键）的解析状态 |

**不落盘的字段**（加载时按函数名重算或可由其他字段推出，故不存）：`prefix`、`tokens`
（v2 存了，现由函数名重算，7667/7667 一致）；`docset`（= `where.file` 首段目录）；
顶层 `file`（与 `where.file` 同值）；`source.anchors`（官方文档工具生成的页内数字锚点，
单条最多 746 个，与函数用法无关，回查只需单数 `anchor`）；`kind`（存为 `type`）；
`signature`+`signatures`（合并为 `decl`）；`argument_groups[]` 内的参数对象副本
（成员集合与 `lists[].items` 逐一相同）。

### 2.1 `field_status`

恒定覆盖 16 个规范节名 + `decl`。取值：`present`、`text_fallback`、`documented_none`、
`not_documented`、`unparsed`（`decl` 另有 `shared_declaration`）。它记录**解析过程的事实**
（不可由内容导出），是"这一节官网上没有"与"有但解析失败"可分的依据，因此保留。
工具层不逐条列出 `not_documented`/`documented_none`（那是"官网上没有"，不是异常）。

## 3. sections 的 16 个规范节名

标题先归一（大小写、单复数、结尾冒号句点），再映射到规范键；**变体写法全部合并**，
实测语料里的写法见括号内次数：

| 规范键 | 原文标题变体 |
|---|---|
| `description` | description |
| `arguments` | argument、arguments；含 `<br>` 合并标题（见下） |
| `returns` | value returned(7165)、values returned(272)、return value(17)、return values(6) |
| `example` | example、examples、example 1/2/3/4/5、example for integrators、`example: …`、`example to …`、`examples of …`、exampleexample（前缀规则覆盖） |
| `reference` | reference、references、related topic、related topics、see also |
| `related_functions` | related function、related functions |
| `prerequisites` | prerequisite、prerequisites |
| `additional_information` | additional information（含 `additional information (advanced nodes only)`） |
| `interactive_function` | interactive function |
| `associated_options` | associated option、associated options |
| `option_descriptions` | option description、option descriptions |
| `purpose` / `format` / `definition` / `overview` | 同名（本语料各 1～4 例） |
| `errors` | error、errors、error conditions（本语料 2 例） |

**已实测的官方标题笔误**作为字面量单独处理，且**不做模糊匹配**——宽松到"标题含 return"
会把 `Example 1 With Returned Value` 这类示例标题误判成返回值小节。当前收录：
`value returned\`、`value returne`、`value returnedz`、`value returned4`、`values return`、
`.value returned`、`value returnedd`。

**节内容形态**：`arguments` 为结构化树；`returns` 为 `{items:[{value,desc}]}`；
`reference` 为 `{text, links:[{text,href}]}`；其余节为 `{text}`，含表格时另给
`items:[{name,desc}]`。多行文本保留换行。

## 4. arguments 的嵌套结构（ROD 子参数列表）

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

## 5. 解析边界

- **`<br>` 合并标题**：按拆开后的后半部分判定——后半是已识别节名（如
  `Arguments<br>Values Returned`）则视为**两个节**，参数表归 arguments、节尾部非参数表归
  returns；后半不是节名（如 `Arguments<br><br>Master Path Arguments`）则为**节内子范围**，
  记为 `arguments.root.title`。
- **未识别的 h4** 作为所属节的正文子标题保留在该节 `text` 内，不单列成节、也不折进邻节
  语义（实测 5.4% 的 topic 含此类自由子标题）。
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
- 范围为代码 `_SKILL_DOC_DIRS` 白名单，不把其他目录中的配置项、C++ 或示例函数视为官方
  可调用函数。构建统计可用 `coverage_report()`，或模块 CLI 的 `--report`
  （`python -m knowledge_virtuoso.functions.core.catalog --doc-root <doc> --report`；
  注意 `knowledge-virtuoso-build` 没有该开关）。

**两种老式排版的收益（实测）**：全库仅 51 个函数内容变化，新增 217 条条目**逐字可追溯
原文 arguments.text**、0 条编造，旧条目文本无丢失；未展开（正文/条目展平 ≥1.20）由
54 个函数/40,812 字降到 50 个/33,687 字，余下主要是纯散文块——那些**不做条目化**，
硬切会造出 `For` / `Note:` 这类假参数名。

## 6. 存储形式与加载

紧凑 JSON（无缩进空白）经 **gzip** 压缩落盘（`mtime=0`，同样内容产出同样字节，构建可
复现），约 2 MB。加载时按 gzip 魔数 `1f 8b` 识别并解压；未压缩 JSON 仍兼容。因此
**不能用编辑器直接查看或 grep**，排障用 `gzip -dc <索引> | head`。
`db`/`techdb`/`cdfdb` 三个属性库索引体积很小（合计约 100 KB），仍是明文缩进 JSON。

实测：v2 磁盘 37.23 MB → v3 **2.12 MB（−94%）**；解压 25 ms、JSON 解析 244 ms——冷加载
反而更快，因为读的 I/O 从 25 MB 降到 2 MB。

查询按**健康内存 → JSON → doc 恢复**；仅 JSON 缺失、损坏、版本不符或空记录时，允许从显式
`doc_root` 或 MCP 进程环境 `VIRTUOSO_DOC_DIR` 重建并原子写回。默认索引位于平台数据目录
（`VIRTUOSO_DATA_DIR` 可覆盖）下的 `functions/index.json`；索引不随包分发。

## 7. 版本与兼容性

- `schema_version` = **3**；`decl`/`sections`/`where`/`also_at` 键名、由数组改为
  `{root, lists}` 的 `arguments`、扩展后的 `field_status` 键集，均为**不兼容变化**；
  v2 索引在加载时报错并提示 `knowledge-virtuoso-build functions` 重建。
- **格式**变了会自动判为不兼容并触发重建；**内容**改进不会——已有索引不会自动重建，
  升级后需显式重建一次。

## 8. 工具层的取舍（MCP 输出策略）

`server.py` 的策略表决定哪个节进哪个 `detail` 档（改它零重建，索引照收全部节）：

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
| `field_status` 异常项（中文措辞） | | | | | ✅ |
| `省略:` 指针行 | ✅ | ✅ | | 有省略时 | |

档位依据：`digest` 面向"**挑函数**"（横向比较候选，长度与文档体量脱钩：全库 max 798 字、
中位 260）；`skel` 面向"**写调用**"（签名 + 参数关键字/类型 + 取值/默认，不含量词解释）；
`brief` 放"缺了就写错或写不出调用"的节（前置条件 44 例、选项字典 38 例、交互式提示 21 例）；
`full` 放澄清语义与导航类。全库体量：digest 2.10 M、skel 2.10 M、brief 6.03 M
（digest 为 brief 的 34%、skel 为 37%）。**skel 不是有界档**：`digest` 有 900 字硬上限
（实测 max 793），`skel` 是**按比例**的——ROD 族因签名不截断、默认值行多，最大 9,477 字。

**输出形式约定**（便于程序化切分）：单行项用行内前缀（`函数:`、`签名:`、`描述:`、
`来源:`、`解析状态:`、`省略:`），多行块用独占一行的节标题（`参数:`、`返回:`、`示例:`）——
块内条目再缩进一层。两行正则够用：块标题 `^[^ \t].*:$`，块内条目首行 `^ +.+? — `
（其后缩进更深的行属于上一条目）。`主参数组 […]`／`子参数 […]（属于 …）` 标识分组，
不与参数条目同级。**检索**：`skill_language_search_components` 每行默认附一行 `digest`
（`with_digest=false` 只回名字与来源），`digest`/`skel` 都可直接作为 `detail` 传给
`skill_language_search_doc`。

**省略指针统一格式**：`省略: <省了什么> → detail="X"`（机器可识别的前缀 `省略: `）。现有
两处指针都改用它——选项字典 `省略: 选项说明 76 条共 45,951 字 → detail="full" 或
sections=["option_descriptions"]`、参数块预算 `省略: 参数说明续文 N 条共 X 字 →
detail="full"（参数名、允许取值与 Default 已保留）`。全库只有 24 个函数的 brief 因此改写。

**新档位的两条硬约束**（审计方验收标准）：`digest` 全库 max ≤900 字（实测 798）；
`skel` 里 `?kw` 集合 ⊇ 签名参数（签名在 skel 里**不截断**——实测有 2 个函数签名超 320 字，
截断会让签名里的 `?参数` 无处可查）、且参数表的 `Default`/`Valid values` 一条不丢
（实测 531 个参数的这类事实**只出现在说明首行**，所以 skel 从首行里从事实词处截取原文片段，
续行整行保留）。两个档位都只做筛选与空白重排：签名去掉空白后与原文逐字相同。

**"取值/默认值"的判据只有一个**：`\b[Dd]efaults?\b|\b[Vv]alid [Vv]alues?\b|默认|取值`。
三条实测教训——① **大小写与写法都要认**：官方混用 `Default:`、`The default value is 0.`、
`By default,`、`Defaults to`；只匹大写 `Default` 会让 674 个参数（391 个函数）的默认值在
skel 里消失（`abeLayerGrow` 的 `?north`、`abeElapsedTime` 的 `?reset`）；
② **必须有词边界**：否则 `formDefaultAction`、`g_defaultValue` 这类标识符里的 "Default"
会被当成事实，凭空保留整行脱节碎片；③ **首行片段从句子开头截取**（上限 160 字）——
`The default value is 0.` 而不是 `default value is 0.`。brief 的参数块预算与 skel 的
片段选取共用这一个判据，保证"brief 留下的"与"skel 保留的"不会各说各话。

**参数块篇幅预算**（仅 brief）：参数块超过 12,000 字时，保留每个参数的首行与含
`Default`／`Valid Values`／`取值` 的行，其余说明续文移入 `full`，块尾显式标注
`省略: 参数说明续文 26 条共 11,489 字 → detail="full"（参数名、允许取值与 Default 已保留）`。
实测只影响 4 个函数（`rodCreatePath` 35,266→**26,128**、`rodCreateRect`
28,913→**18,399**、`hiCreateAppForm` 16,593→**6,367**、`hiCreateReportField` 15,366→**6,858**）；
参数密集但无长散文的（如 `hnlInitMap`）不触发。

**为什么要标注而不静默截断**：续行里约 82% 不是取值/默认值，而是约束类文字
（`The value of x_displayOrder must be an integer…`、`Note: This argument only applies to
type-in fields.`、`Callback parameter list: (o_session r_form r_field)`）——正是"缺了就写错"
那一类，必须让消费方知道"说明被移到 full 了"。

**其他取舍**：描述超长在 brief 截断并标注字符数；来源写作 `文件[#锚点]`，锚点与函数名
相同时不重复；参考链接去锚点（页内 `#787126` 与跨页 `…#PCRE_CASELESS` 都去）并同名去重，
跨页链接以**方括号**标注所在文件（`strcmp [stringfunc.html]`）——用圆括号会被读成"函数调用"，
且与同一行里的裸名字形式不一致；正文若只是同一批链接名的罗列则与链接合并；`解析状态` 只列
`text_fallback`/`unparsed`/`shared_declaration` 三种真异常，用中文措辞（如
`示例节官方原文未能可靠提取`），已由正文块标题写明状态的节不重复列；techdb 的 `rw` 列在
该库恒为 `?`，无信息量时省略。

## 9. 渲染层审计与处置记录

外部消费方对 v0.1.7 做过一轮渲染层审计（101 个函数 × 3 档），其后的复核改用了全库实测
（7667 个函数 × 2 档 + 101 个函数逐字回归）。处置要点与理由留档如下，便于后续改动不
重复踩：

| 项 | 结论与处置 |
|---|---|
| brief 无上界 | `absAbstract` brief 曾 50,958 字（≈full），全在 `option_descriptions`（45,951 字）→ 该节移到 full，brief 给一行指针；`associated_options`（选项名+一行说明）仍留 brief。全库 brief>8K 由 20 个降到 17 个，再经参数块预算降到 **15 个**（4 个被裁剪的函数里 2 个落到 8K 以下） |
| 签名与参数表名字不一致 | 74 个函数（`?cvId`↔`?cdId`、`?beginExt`↔`?beginnExt`、`?recreateAll`↔`?g_recreateAll`）→ 参数块首行输出**校验行**，含疑笔误配对与仅一方有的名字 |
| `解析状态` 措辞 | 曾输出原始 dict（`{"example": "unparsed"}`，134 个函数）→ 改中文措辞、不暴露字段名与枚举值 |
| 参考链接 | 曾泄漏页内数字锚点并重复两遍（`hiCreateTreeTable` 的相关块 2,263 字/14 行）→ 去锚点、同名去重、与正文名字罗列合并，降到 761 字/1 行；跨页链接进一步由 `strcmp(stringfunc.html)` 改为 `strcmp [stringfunc.html]`——圆括号形式像函数调用，且与同行的裸名字不一致（156 个函数/267 处，仅 `full` 档的 `相关:` 行） |
| 参数文档缺失时静默 | 14 个函数签名有参数而 `arguments: not_documented` → 输出 `参数:（官方未提供参数说明；签名含 N 个 ?参数，见来源原文）` |
| 重复长段落是否折叠 | **不折叠**：`rodCreatePath` 的 4 个 `?prop` 分属根参数表与 3 个子参数列表，`absAbstract` 的 76 条选项说明无重名、无重复长描述——重复来自官方原文，折叠会丢掉"属于哪个子列表"的信息 |
| 第三轮：skel 丢"写在首行句子里的默认值" | **真缺陷**（`abeLayerGrow ?north` 的 `The default value is 0.`、`abeElapsedTime ?reset` 的 `By default, …` 等 674 个参数/391 个函数）。根因是判据 `Default\|Valid [Vv]alues` **区分大小写、无词边界**；已改为大小写不敏感 + `\b` + 句子开头截取（见 §8）。同时修复"`formDefaultAction` 被当成事实"的误留，以及 digest 无条件声称省略完整签名。复核方还指出我们 §10 的"事实缺失 0 条"是**用实现自己的正则验自己**（循环论证）——已换用与实现不同的判据重验：参数块事实出现次数 brief 5,011 / skel 5,044，**0 个函数 skel 少于 brief** |
| 节标题两种写法 | 保持"单行项行内前缀、多行块独占一行"，并用上文两行正则把切分规则写明 |
| 省 token 方案（消费方提案：分档而不是压缩） | 采纳 **`digest`＋`skel`＋统一的 `省略:` 指针＋检索行带摘要**。诊断复算后确认：brief 的字节不在"散文"，而在**每参数首行**（`rodCreatePath` 首行 17,524 字里 15,802 是描述文字，占 brief 63%）——所以不该压 brief，而是另开档位。**不采纳**"条目行只留第一句"（会剪掉 `Note:`/`must be`/`ignored unless` 这类约束，与"宁可长、不可缺"相反）。回归：`signature`/`full` 全库逐字未变，`brief` 只有 24 个函数的指针行改写（0 处非指针变化） |

## 10. 验收记录（v3 落地时）

- **忠实性抽样 20 个函数**（含 ROD 的 `lists`、`abs*` 的选项节、`hiCreateTable` 式的合并
  标题、只有 `definition` 的 `pstddev`、`geHiDragFig` 的编号示例）：索引 `sections` 的键与
  原文识别出的节**零不一致**；各节文本与原文**逐字一致**（0 处差异）。
- `field_status` 每条恒定 17 键，无缺键。
- 真实 MCP stdio 跑通三个 `detail` 档 + 命中/未命中/弃用/共享声明四个分支 + `sections`
  开关（含未识别节名被忽略）。
- 体积：v2 磁盘 37.23 MB → v3 2.12 MB。
- 已知遗留：`error` 一类"返回值是散文"的节由 `returns.text` 承载；官方标题笔误 7 例以
  字面量处理，若上游修正可逐条删除。
