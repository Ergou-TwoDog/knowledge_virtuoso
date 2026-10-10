# IC618 官方函数索引字段映射（v3）

结构为 v3：`schema_version`（=3）、`corpus`、`functions`。设计动机与取舍策略见
[docs/index-v3-design.md](../../../../docs/index-v3-design.md)：**索引如实还原官方 doc 的
节结构，取舍上移到 MCP 工具层**。v2 索引不再兼容，加载时按版本不符报错并提示重建。

**存储形式**：紧凑 JSON（无缩进空白）经 **gzip** 压缩后落盘，约 2 MB；加载时按 gzip 魔数
`1f 8b` 识别并解压，未压缩的 JSON 仍可读。因此**不能用编辑器直接查看或 grep**，排障请用
`gzip -dc <索引> | head`。`db`/`techdb`/`cdfdb` 三个属性库索引体积很小，仍是明文 JSON。

查询按健康内存 → JSON → doc 恢复；仅 JSON 缺失、损坏、版本不符或空记录时，允许从显式
`doc_root` 或 MCP 进程环境 `VIRTUOSO_DOC_DIR` 重建并原子写回。默认索引位于平台数据目录
（`VIRTUOSO_DATA_DIR` 可覆盖）下的 `functions/index.json`。

## 一条记录

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
（v2 存了，现由函数名重算）；`docset`（= `where.file` 首段目录）；顶层 `file`（与
`where.file` 同值）；`source.anchors`（官方文档工具生成的页内数字锚点，与函数用法无关，
回查只需单数 `anchor`）；`kind`（存为 `type`）。

## sections 的 16 个规范节名

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

## arguments 的嵌套结构（ROD 子参数列表）

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

## 解析边界

- **`<br>` 合并标题**：按拆开后的后半部分判定——后半是已识别节名（如
  `Arguments<br>Values Returned`）则视为**两个节**，参数表归 arguments、节尾部非参数表归
  returns；后半不是节名（如 `Arguments<br><br>Master Path Arguments`）则为**节内子范围**，
  记为 `arguments.root.title`。
- **未识别的 h4** 作为所属节的正文子标题保留在该节 `text` 内，不单列成节、也不折进邻节
  语义（实测 5.4% 的 topic 含此类自由子标题）。
- `mapping.md` 只覆盖上述规范节；`field_status` 是唯一"非从原文抄来"的字段，它记录解析
  过程的事实，是"这一节官网上没有"与"有但解析失败"可分的依据。
- HTML 以 UTF-8 容错读取；字体、颜色、图片和完整排版不保留。遇到
  `not_documented`/`unparsed` 或自然语言约束，应回到
  `<实际 doc 根>/<where.file>#<where.anchor>`，不要根据空列表猜测无参数或无返回。
- 范围为代码 `_SKILL_DOC_DIRS` 白名单，不把其他目录中的配置项、C++ 或示例函数视为官方
  可调用函数。构建统计可用 `coverage_report()`，或模块 CLI 的 `--report`
  （`python -m knowledge_virtuoso.functions.core.catalog --doc-root <doc> --report`；
  注意 `knowledge-virtuoso-build` 没有该开关）。
