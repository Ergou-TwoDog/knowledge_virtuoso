# IC618 官方函数索引字段映射

结构仍为 v2：`schema_version`、`corpus`、`functions`。兼容有效旧 v1 平面索引读取，不自动迁移。查询按健康内存 → JSON → doc 恢复；仅 JSON 缺失、损坏、空记录或不兼容时，允许从显式 `doc_root` 或 MCP 进程环境 `VIRTUOSO_DOC_DIR` 重建并原子写回对应 JSON。默认索引位于平台数据目录（`VIRTUOSO_DATA_DIR` 可覆盖）下的 `functions/index.json`，显式来源按规范绝对路径区分（不解析符号链接别名）。

加载时校验根、版本、非空函数记录及查询消费字段基本类型，局部构造主/关键词/前缀三索引；写入成功后才发布内存与统计。RLock 保证检查、恢复、发布和一致读取；doc 目录无效、空解析、读取或写入失败不发布半成品，保留实际 JSON/doc 错因，恢复日志只写 stderr。健康判断为 ready、字典类型、主索引非空和三字典长度快照（O(1)，前缀可为空），不保证发现等量或嵌套损坏。不热更新、不因零匹配而重建；缺签名的旧记录不补造签名，也不另读 HTML。

| 字段 | 来源及含义 |
|---|---|
| name / functions 的 key | 官方 topic 名称；逗号共享条目按成员拆分；一个 marker 含多个可调用 h3 时按真实标题拆分 |
| kind / file / docset | 条目类型，当前恒为 `function`，不承载区分信息；file 为相对 doc 根的源文件路径（与 `source.file` 相同，两处重复）；docset 为该路径的首段目录，即 `docset == file.split("/")[0]`（实测 7667/7667，可由 file 完全推出，不携带额外信息） |
| signature | 声明区 dl/pre/code 的主声明，不取示例区调用 |
| signatures | 同一选定 topic 的多个有效声明，去重；不宣称合并所有同名文档语义 |
| signature_note / derivation_basis | 共享声明说明及原文依据。assoc、assq 使用 assv 共享声明但不伪造自身签名；28 个 c…r 名称取自官方 possible combinations 段落，保留族声明，不输出伪造的逐成员声明 |
| description | Description 正文及表格文本，保留换行、重复章节 |
| arguments / argument_groups | 表格参数和层级，保留原兼容字段。两者参数名集合一致（实测 7665/7667），argument_groups 的嵌套 groups 恒空，6799 个组中 6790 个组名就是 Arguments，仅 4 条条目出现自定义组名——多数条目里它与 arguments 重复，因此查询仅在分组非默认时才输出 |
| returns | 表格返回值；Errors 独立分节，不混作返回值 |
| arguments_text / returns_text / errors_text | 正文章节回查文本，用于结构化失败时的 fallback：`err`、`error` 的 returns_text 即官方原文 “Never returns a value.”（此前此处误记为 errors_text 的例子）。arguments_text/returns_text 多数条目非空（6802/7064 条），但内容与 arguments/returns 表格重叠，仅在表格为空时才作为正文补充返回。errors_text 取自独立的 Errors 分节；实测 25 个入库文档集**均无该分节**（全 doc 根下的 Errors 标题都落在 dracula、spectre、assembler 等未入库文档集），故该字段一直为空——是源文档没有，不是解析失败或漏抓 |
| example | Examples 文本，保留换行，避免注释与下一行调用相连；不保留精确排版 |
| references | Reference/Related Topics/See Also 的文本和原始 href。相对链接以 source.file 所在目录解析 |
| source | file、topic、marker_text、anchor、anchors。marker_text 保留原官方标记，即使与真实标题不一致；anchor 必须实际存在。anchors 是该 topic 内全部元素 `name`/`id` 属性的去重清单（保序），主体是官方文档工具为每段生成的数字编号（如 `"1217188"`），不含说明文本；anchor 从中选取——函数名在清单内就取函数名，否则取首项，用于拼接 `<doc 根>/<source.file>#<source.anchor>` 回查。实测 7667 条全部带该字段，单条 4～746 个，与函数用法无关，查询输出不再携带 |
| sources | 同名补充来源定位；主正文优先 active，其他来源仅追踪定位，不合并全部正文 |
| field_status | present、text_fallback、documented_none、not_documented、unparsed；signature 另有 shared_declaration。明确 None. 不等于缺文档或解析失败 |
| status | 现有 deprecated 文本启发式，不能视作产品支持认证 |
| prefix / tokens | 函数名拆词生成，用于精确名、领域前缀、拆词搜索；非描述检索 |

HTML 以 UTF-8 容错读取；原文个别非 UTF-8 字节可能丢弃。字体、颜色、图片和完整排版不保留。遇到 not_documented/unparsed 或自然语言约束，应回到 `<实际 IC618 doc 根目录>/<source.file>#<source.anchor>`（doc 根目录取显式 `doc_root` 或服务进程的 `VIRTUOSO_DOC_DIR`），不要根据空列表猜测无参数或无返回。

范围为代码 `_SKILL_DOC_DIRS` 白名单，本次增加 ocnxl、aelref；不把其他目录中的配置项、C++ 或示例函数视为官方可调用函数。目录外候选只是待人工核查样本，未收录且不代表总数。构建统计可在成功构建后通过 `coverage_report()` 或 CLI `--report` 查看；历史对比报告已清理，不随运行文件交付。
