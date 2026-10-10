# 索引 v3 设计：忠实还原 + 工具层取舍

本文件是函数索引从 v2 演进到 v3 的设计方案。v3 的目标不是"更小的索引"，而是
**索引如实还原官方 doc 的节结构，取舍全部上移到 MCP 工具层**。当前 v2 的实际字段
语义见 [mapping.md](../src/knowledge_virtuoso/functions/data/mapping.md)；本文件描述
尚未实现的目标状态，实现完成后字段语义应并入 mapping.md。

## 1. 设计原则

| # | 原则 | 依据 |
|---|---|---|
| 1 | **索引如实**：内容 ≡ 官方 doc 的节结构；变体与笔误只做归一；不做价值取舍、不做跨节合并 | 索引可审计；取舍有争议时能分清是索引不忠实还是输出策略不合适 |
| 2 | **只存不可导出的**：可导出的一律不落盘 | 逐项实测：`tokens`/`prefix` 由函数名重算（7667/7667）、`docset` = `file` 首段（7667/7667）、`kind` 恒定、`source.anchors` 与函数用法无关 |
| 3 | **取舍在工具层**：哪个节进哪个 `detail` 档由 `server.py` 的策略表决定，改它零重建 | 重建一次约 86 秒；输出策略需要反复迭代 |
| 4 | **表示与内容分离**：紧凑 JSON + LF + gzip，语义不变 | 实测 34.5 MB → 23.85 MB（去缩进）→ 约 2 MB（gzip） |

## 2. 索引 schema v3

```jsonc
{
  "schema_version": 3,
  "corpus": { "product": "Cadence IC618", "scope": "official-skill-callables" },
  "functions": {
    "<可调用名>": {
      "type": "function",                    // 结构锚点（今日恒定）
      "decl": [                              // 全部声明；共享声明自带归属
        { "text": "…", "shared_from": null } // shared_from 非 null 表示取自该 topic 的共享声明
      ],
      "where": {                             // 主来源，回查指针
        "file": "…", "topic": "…", "marker_text": "…", "anchor": "…"
      },
      "also_at": [],                         // 补充来源（v2 的 sources[1:]）
      "sections": { /* 见 2.1，稀疏：doc 出现哪些节就记哪些 */ },
      "status": "active",                    // active / deprecated（文本启发式，非产品认证）
      "field_status": { /* 见 2.3，恒定 16 键 */ }
    }
  }
}
```

### 2.1 sections 的 16 个规范节名

| 规范键 | 覆盖的原文标题变体（实测） |
|---|---|
| `description` | description |
| `arguments` | argument、arguments；另含 ROD 的 `<br>` 合并标题（见 3.2） |
| `returns` | value returned(7165)、values returned(272)、return value(17)、return values(6)＋7 个笔误字面量 |
| `example` | example(5562)、examples(517)、example 1/2/3/4/5、example for integrators、`example: xxx`、`example to xxx`、`examples of xxx`、`exampleexample` |
| `reference` | reference(839)、related topics(45)、references(11)、related topic(3) |
| `related_functions` | related functions(42)、related function(39) |
| `prerequisites` | prerequisites(44)、prerequisite(1) |
| `additional_information` | additional information(35)、additional information (advanced nodes only)(3) |
| `interactive_function` | interactive function(21) |
| `associated_options` | associated options(19)、associated option(1) |
| `option_descriptions` | option descriptions(19)、option description(1) |
| `purpose` / `format` / `definition` / `overview` | 各 4/4/3/1 |
| `errors` | error、errors、error conditions（本语料 0 例，保留以兼容其它 docset） |

**归一原则**：单复数、大小写、编号、`: ` 后缀都归一到同一规范键；已实测的笔误
（`value returned\`、`value returne`、`value returnedz`、`value returned4`、
`values return`、`.value returned`、`value returnedd`）另列字面量表处理，不做模糊匹配——
按"含 return"宽松判定会把 `Example 1 With Returned Value` 这类示例标题误判。

**节内容的形态**：有表格结构的（`arguments`、`returns`、`option_descriptions`）记
`items`；其余记 `text`；`reference` 记 `text` + `links`。

### 2.2 arguments 的嵌套结构（ROD 子参数列表）

ROD 函数的参数分两层：根参数 + 若干"子参数列表"。原文的表达方式是——根参数节标题用
`<br><br>` 合并（`Arguments<br><br>Master Path Arguments`），每个子参数列表是同级的
独立 `<h4>`，标题形如 `Subrectangle Arguments (l_subrectArgs)`，父子关系**只体现在
标题括号内的 token**（那是父参数的类型名）。

```jsonc
"arguments": {
  "root": { "title": "Master Path Arguments", "items": [ /* 参数项 */ ] },
  "lists": [
    { "title": "Subrectangle Arguments",
      "list_type": "l_subrectArgs",           // 标题括号里的 token
      "parent": { "arg": "?subrectArgs l_subrectArgs",
                  "type": "l_subRectArgs",    // 原文实际写法
                  "match": "case_insensitive" },  // 命中 0/多 → null + "ambiguous"
      "items": [ /* 参数项 */ ] },
    { "title": "ROD Connectivity Arguments for Polygons",
      "list_type": null, "parent": null, "items": [] }   // 空节也如实保留
  ]
}
```

- 参数项：`{ "name": "…", "desc": "…", "values": null }`；`values` 用于紧随单行参数表的
  允许取值表（如 `?selectMode` 后的 `'single/'browse/…`）。
- 实测：ROD 共 8 个真分组、1 个空分组（`for Polygons`）、层级只有一层（嵌套 `groups` 恒空）。
- 父参数匹配必须**忽略大小写**（原文自身有 `l_subrectArgs` vs `l_subRectArgs`、
  `l_encSubpathArgs` vs `l_encSubPathArgs` 两处不一致）。`...` 不能当"列表参数"标记：
  全库仅 16 处，且混用了 ROD 列表与 `defmethod(g_exp1 ...)` 这类变参。

### 2.3 field_status

恒定覆盖 16 个规范节名 + `decl`（共 17 键），取值 `present` / `text_fallback` /
`documented_none` / `not_documented` / `unparsed`（`decl` 另有 `shared_declaration`）。
它记录的是**解析过程的事实**（不可由内容导出），因此保留；它也是"这一节官网上没有"
与"有但解析失败"可分的依据。

### 2.4 不进的字段

| 不存 | 理由（实测） |
|---|---|
| `kind`（存为 `type`） | 7667/7667 恒为 function，保留仅作结构锚点 |
| `docset` | 7667/7667 == `file` 首段目录 |
| `tokens`、`prefix` | 7667/7667 == 由函数名重算；检索能力保留在代码里 |
| 顶层 `file` | 与 `where.file` 同值 |
| `source.anchors` | 官方文档工具生成的页内数字锚点（单条最多 746 个），与函数用法无关 |
| `sources[0]` | 与 `where` 重复（7621/7667 逐字相同） |
| `signature` + `signatures` | 合并为 `decl`（7652/7667 两者内容相同） |
| `argument_groups[]` 内的参数对象副本 | 成员集合与 `args[].group` 同名项逐一相同；改由 `lists[].items` 承担 |

## 3. 解析规则

### 3.1 节识别
标题归一后按规范节名表匹配；`example` 用前缀规则（覆盖编号/带描述等全部写法）。

### 3.2 `<br>` 合并标题
同一标题内用 `<br>` 折行塞两个标签。按拆开后的后半部分判定：

| 原始标题 | 后半 | 语义 |
|---|---|---|
| `Arguments<br><br>Master Path Arguments` | 不是节名 | **节 + 节内子范围** → 记为 `arguments.root.title` |
| `Arguments<br>Values Returned` | 是节名（returns） | **两个节** → 参数表归 arguments，尾部非参数表归 returns，不生成"Values Returned"参数组 |

### 3.3 未识别的 h4
作为**所属节的正文子标题**保留在该节 `text` 内，不单列成节，也不折进邻节语义。
实测有 411 个 topic（5.4%）含此类自由子标题（如 `how the system follows to create subrectangles`）。

### 3.4 允许取值表
紧随单行参数表的、行首为 `'symbol` 字面量的表 → 作为该参数的 `values`。
实测 23 个函数的参数名里混入了这类字面量（如 `digitalHostMode` 的 `'local`/`'remote`），
其中 22 个是合法的允许取值，不能按"以 `'` 开头就不是参数"一刀切。

## 4. 存储形式（已实现）

| 项 | 做法 | 实测 |
|---|---|---|
| 缩进 | 紧凑分隔符 `(",", ":")` | 25.03 → 18.27 MB |
| 压缩 | gzip（`mtime=0`，同样内容产出同样字节）| → **2.12 MB** |
| 读取 | 按 gzip 魔数 `1f 8b` 识别并解压；未压缩 JSON 仍兼容 | 解压 25 ms、JSON 解析 244 ms |

整体：v2 磁盘 37.23 MB → v3 **2.12 MB（−94%）**。冷加载耗时反而下降，因为读取的
I/O 从 25 MB 降到 2 MB。

代价：索引变为二进制后不能再用编辑器直接查看或 grep，排障需 `gzip -dc` 解压查看；
`db`/`techdb`/`cdfdb` 三个属性库索引体积极小（合计约 100 KB），仍保持明文缩进 JSON。

## 5. MCP 工具层（已实现）

工具名与参数不变（5 个工具，`detail` 三档语义不变），另加可选开关 `sections=[...]`：
可显式索取 `prerequisites`、`interactive_function`、`associated_options`、
`option_descriptions`、`example`、`additional_information`、`related_functions`、
`format`、`purpose`、`overview`、`reference` 中的任意节，把该节拉进本次返回；未识别的
节名被忽略。`description`/`arguments`/`returns` 由 `detail` 控制，不接受显式索取。

### 5.1 输出选择策略表

| 节 | `signature` | `brief`（默认） | `full` |
|---|---|---|---|
| `decl` | ✅ | ✅ | ✅ |
| `description`（缺 `description` 时用 `definition` 顶） | | ✅ | ✅ |
| `arguments`（root + lists 嵌套渲染 + values） | | ✅ | ✅ |
| `returns` | | ✅ | ✅ |
| `prerequisites` | | ✅ | ✅ |
| `interactive_function` | | ✅（一行提示） | ✅ |
| `associated_options` + `option_descriptions` | | ✅ | ✅ |
| `example` | | | ✅ |
| `format` / `purpose` / `overview` | | | ✅ |
| `additional_information` | | | ✅ |
| `related_functions` / `reference` | | | ✅ |
| `status: deprecated` 提示 | ✅ | ✅ | ✅ |
| `field_status` 异常项 | | | ✅ |

档位依据（实测）：`brief` 放"缺了就写错或写不出调用"的节——`prerequisites` 44 例
（含"只在 method 体内调用否则返回值未定义"这类硬约束）、选项字典 38 例（`abs*` 系列
函数**参数列表为空**，选项表是参数信息的唯一载体）、`interactive_function` 21 例；
`full` 放澄清语义与导航类。

### 5.2 输出格式

每段都带节名，杜绝"选项表被当成返回值"这类错位阅读；ROD 子参数嵌在父参数下缩进输出：

```
函数: rodCreatePath
签名: rodCreatePath( … ) => R_rodObj / nil
描述: …
参数:
  ?name S_name — …
  ?subrectArgs l_subrectArgs — A list containing one or more lists …
    子参数:
      ?layer txl_layer — …
返回:
  R_rodObj — …
来源: rodskillref/chap1.html#rodCreatePath
```

`full` 追加带节名的段落：`示例:`、`前置条件:`、`术语补充:`、`回调模板:`、
`相关函数:`、`参考链接:`、`解析状态:`。

## 6. 兼容性

- `schema_version` → 3；键名重构（`decl`/`sections`/`where`/`also_at`）、`arguments`
  由数组变为 `{root, lists}`、`field_status` 键集扩展，均为**不兼容变化**；
- 加载器与工具层必须同版本发布；旧 v2 索引按既有策略视为不兼容并触发重建；
- README「详情粒度」段与 mapping.md 字段表需同步重写。

## 7. 验收标准（已按此验收，结果见下）

1. **忠实性抽样**：20 个函数逐字对照原文，必含 ROD 的 `lists`、`abs*` 的选项节、
   合并标题的 `hiCreateTreeTable`、只有 `definition` 的 3 例；
2. **指标**：`returns` 的 `not_documented` 由 619 降至约 192；`example` 缺失由 1,522
   降至约 1,470；选项节由"折进 returns"变为独立节（38 处）；
3. **变化集合断言**：重建后只有含额外小节 / 编号示例 / 选项表 / `lists` 的函数发生变化；
4. **输出侧**：三个 `detail` 档 + 命中/未命中/弃用/共享声明四个分支走真实 MCP stdio；
5. **体积**：记录紧凑与 gzip 后大小。

## 8. 落地顺序（四步均已完成）

| 步 | 内容 | 状态 |
|---|---|---|
| 1 | 解析器：标签表扩到 16 类 + `<br>` 合并标题规则 | ✅ `ad2c18b`（返回值标签）＋ 后续提交 |
| 2 | 解析器：`arguments.{root,lists,parent,values}` + `field_status` 规范名 + `sections` 收录 | ✅ `76ba499`、`efd0f86` |
| 3 | 存储：紧凑 + gzip | ✅ `0663a53` |
| 4 | 工具层：策略表 + 嵌套渲染 + 节名标注 + `sections` 开关 | ✅ 验收结果见下 |

## 9. 验收结果（实测）

- **忠实性抽样 20 个函数**（含 ROD 的 `lists`、`abs*` 的选项节、`hiCreateTreeTable` 的合并
  标题、只有 `definition` 的 `pstddev`、`geHiDragFig` 的编号示例）：索引 `sections` 的键与
  原文识别出的节**零不一致**；各节文本与原文**逐字一致**（0 处差异）。
- `field_status` 每条恒定 17 键（16 节 + `decl`），无缺键。
- 真实 MCP stdio：三个 `detail` 档 + 命中/未命中/弃用/共享声明四个分支 + `sections` 开关
  （含未识别节名被忽略）全部通过。
- 体积：v2 磁盘 37.23 MB → v3 **2.12 MB**。
- 已知遗留：`error` 一类"返回值是散文"的节由 `returns.text`（返回正文）承载；
  官方标题笔误 7 例以字面量处理，若上游修正可逐条删除。
