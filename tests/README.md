# 测试：`tests/knowledge_virtuoso/` 与 `src/knowledge_virtuoso/` 同构

```bash
uv run python -B tests/run_tests.py                    # 全部（自动发现镜像树下所有 test_*.py）
uv run python -B tests/run_tests.py functions/core     # 只跑镜像路径里含这段的
uv run python -B tests/run_tests.py --update           # 重录 golden
uv run python -B tests/tools/capture_fixtures.py       # 重新采集 fixture（需本机索引）
uv run python -B tests/tools/capture_official_html.py  # 重切函数库解析器的 HTML 片段（需本机 doc）
uv run python -B tests/tools/capture_attrs_html.py     # 重切四个属性库解析器的 HTML 片段（同上）
uv run python -B tests/knowledge_virtuoso/test_server.py   # 真起一次 MCP（启动 Claude 前先跑这个）
```

每个 `test_*.py` 也能**单独直跑**（如
`uv run python -B tests/knowledge_virtuoso/functions/core/test_contract.py`）。
不需要 IC618 doc、不需要索引、不需要网络：fixture 就是被测层的输入。
不引第三方依赖，只用标准库；文本一律 UTF-8 + LF 落盘（`.gitattributes` 里
`* text=auto eol=lf`——行尾被 checkout 改掉会让 golden 全红）。

## 结构：测试文件放在它测的模块的同路径下

```
tests/
├── README.md · common.py · run_tests.py     # 骨架（≈ conftest.py 那一类；不对应任何 src 模块）
├── tools/                                    # 夹具生成器：**不是测试**（见该目录 README）
└── knowledge_virtuoso/                    # 镜像 src/knowledge_virtuoso
    ├── test_server.py                       # 镜像 server.py：真起一次 MCP 走协议
    ├── functions/
    │   ├── test_index.py · test_registry.py · test_main.py
    │   ├── core/          test_contract.py   test_envelope.py   test_render.py
    │   │                  cases/                                 # 该层自己的数据
    │   └── sources/
    │       ├── official/  test_catalog.py   test_render.py   fixtures/ golden/
    │       │              fixtures/html/{topic,page}/            # 官方 doc 的 HTML 片段
    │       └── custom/    test_catalog.py   test_render.py   fixtures/ golden/
    └── database/
        ├── test_index.py                    # 顶层联合（database/index.py）
        ├── core/          test_objects.py · test_assembly.py · test_query.py
        │                  test_render.py · test_store.py · test_registry.py   # 共享件
        ├── db/            test_index.py  test_render.py  cases/  fixtures/search.json
        │   └── core/      test_parse.py  test_decorate.py
        │                  # test_parse    ↔ core/parse.py     fixtures/raw/   自造小片段
        │                  # test_decorate ↔ core/decorate.py  fixtures/html/  官方 doc 片段
        └── cdfdb/         同 db（techdb / dd 同）
```

**测试树与 src 树一一对应**（四个属性库都这样）：`tests/.../database/<库>/` 与
`src/.../database/<库>/` **同名同层**——`core/test_parse.py` 测 `core/parse.py`、
`core/test_decorate.py` 测 `core/decorate.py`、`test_index.py` 测 `index.py`、
`test_render.py` 测 `__init__.py` 里的 `RenderSpec`。看一眼文件名就知道"改哪测哪"。
这条不只是习惯：`test_registry` 有一条断言钉着**落点**（①② 必须在自己的 `core/` 下、
声明必须在库根的 `index.py`、查询入口必须来自共用件），揉回一个文件就会红。

`cases/` = **一进一出同目录同 stem**（`x.json` 输入、`x.txt` 期望输出，靠扩展名分角色）；
`fixtures/` + `golden/` = 一个输入对应**多份**期望输出（五档渲染）或期望值不是文本（断言）。
两种并存，选哪种只看"一进几出"。

三条规矩：

1. **夹具与期望值跟着被测对象走**（放在那个 `test_*.py` 旁边），每个模块自成一格，
   改了谁就只动谁的目录。**一进一出就放同一个目录、同一个 stem**（`cases/x.json` +
   `cases/x.txt`）——输入挨着期望输出，review 时一眼能看全；只有"一进多出"或"期望值不是
   文本"才退回 `fixtures/` + `golden/`（多出来的那一半按 `<name>.<档>.txt` 命名）。
2. **镜像目录里绝不放 `__init__.py`**。镜像顶层目录名与真包同名，一旦成了常规包就会在
   `sys.path` 上**抢先**真包（实测：只要没有 `__init__.py`，真包是常规包、
   仍然优先命中）。测试模块因此按**文件路径**载入，不按包名 import。
3. **记录型 fixture 的文件名就是记录名**（`golden/` 也按它取名；HTML 片段则同名 `.json`
   放旁边）：`tests/tools/capture_fixtures.py` 按 stem 回索引重录、测试按 stem 找输出，都靠这条。
   两处 `test_render` 各有一条断言钉着它——`custom` 那份曾叫 `synthetic.json` 而记录名是
   `syntheticUniqueFunc`，就是这么断掉的。

## 两种检查，各管一件事

| | 写法 | 测什么 | 用在哪 |
|---|---|---|---|
| **golden 比对** | `report.check(用例, got, golden 路径, update)` | 输出**变没变** | 渲染（`render_entry` 五档、四个属性库的表格） |
| **断言** | `report.expect(用例, 实际, 期望)` / `report.truthy(用例, 条件, 说明)` | 行为**对不对** | 契约、信封、装配、发现、解析——"对错"能直接判的 |
| **跳过** | `report.skip(用例, 原因)` | 环境不具备、**没能真跑** | 需要索引/doc 的检查（如 `test_server` 的查询） |

`Report.summary()` 把三类分开报（`N 份 golden 一致` / `N 条断言通过` / `跳过 N 次`），`run_tests.py`
结尾会把跳过项的原由逐条列出来——免得把"没验到"读成"验过了"。

## 各模块锁什么（当前 18 个）

| 镜像路径 | 类型 | 锁什么 |
|---|---|---|
| `test_server.py` | 断言 10（后四条可能跳过） | `server.py` 的接线：真起子进程走 MCP 协议、**恰好三个工具**（两个函数库 + 一个属性）、`search_attr` 的参数恰好是 `lib`/`object`/`keyword`、八种调用都不报错、**首行是对象头或跨库节首**（`lib="db" object="rect"` → `对象 Rectangle`；`lib="dd" object="cellFile"` → `对象 cellFile`；不给 `lib` → `── db ──`；渲染用例是直接把对象喂进去的，接线忘了传照样全绿，只有真调用能验）；没索引时查询记 SKIP |
| `functions/core/test_contract.py` | 断言 28 | 记录的接受/拒绝（**拒绝消息按完整字符串断言**）、分词、派生键被重算 |
| `functions/core/test_envelope.py` | 断言 13 | 信封往返、gzip 与明文、版本/形态拒绝、写入可复现、路径规范化 |
| `functions/core/test_render.py` | golden 8 | 未命中、搜索零命中（有无相近建议）、搜索页正文 |
| `functions/test_index.py` | 断言 25 | 装配计划（同一文件不当两个来源）、合并与遮蔽、坏源跳过、健康检查、查询/搜索/建议、构建落盘 |
| `functions/test_main.py` | 断言 31 | 开发入口：**查询输出与 MCP 逐字一致**（含来源标记与 `load()` 行）、未命中退出码、`--sources`/构建的旗标分派、`--export`、报告转交来源（含"搬移丢名字"的名字级兜底） |
| `functions/test_registry.py` | 断言 16 | 发现到谁、按 `ORDER` 升序、恰好一个基准、接口齐全、渲染配置分派 |
| `functions/sources/official/test_catalog.py` | 断言 83 | **官方解析器**：11 份 doc 片段（见下）× 每份与线上记录逐字段比对 + 每族一条专项断言（标记切分、共享声明、合并标题、笔误标题、首列占位、裸 `<tr>` 续排、取值表、ROD 子参数表与编号步骤…） |
| `functions/sources/official/test_render.py` | golden 135 + 断言 27 | 27 条官方记录 × 五档（外加"fixture 文件名 == 记录名"） |
| `functions/sources/custom/test_render.py` | golden 5 + 断言 1 | `（自定义）` 标记 + `load()` 前提行——"只因来源不同"的那几行 |
| `functions/sources/custom/test_catalog.py` | 断言 15 | `VIRTUOSO_CUSTOM_INDEX` 解析（多项/目录/去重/不存在的路径照收）、相对路径出声、进程内缓存、`owns` |
| `database/db｜techdb｜cdfdb｜dd/test_render.py` | golden 4/5/4/4 | 四个属性库的表格渲染（列宽、截断、`rw` 列两支、`cardinality` 列一支） |
| `database/core/test_store.py` | 断言 20 | 属性库共用的索引存取：读盘/进程内缓存、坏索引从 doc 重建并原子写回、**索引是别人家的（`lib` 对不上）也不当好的用**、缺 doc 与缺文档分别报什么错、载荷包装、关键词过滤与排序 |
| `database/core/test_objects.py` | 断言 27 | 属性库共用的**载荷模型**：三层键集（顶层三键、对象层七键、记录层 `ATTR_KEYS`）与构建期不变量（含「空属性表合法」「对象 id 可带空格」「记录里多一个没定义的键」「`lib` 与它所在的库不符」）、**记录构造**（没写的补 `null`、写错键名当场炸）、选择器解析次序（**含空格与下划线一视同仁**）、继承合并（**含无父塌缩成自身**）、名字→声明它的对象 |
| `database/core/test_assembly.py` | 断言 10 | 属性库共用的**装配**（`core/assembly.py` 的 `Library`）：载荷打上 `version`/`lib` 且**校验覆盖最终形状**（顶层与库名对不上时，在本库的校验之前就炸）、本库的 `check` 会被调用、**不提供查询入口**（入口归查询那一层）、CLI 打"落点 + lib/版本 + 对象数 + 记录数"外加 `summary` |
| `database/core/test_query.py` | 断言 20 | 属性库共用的**查询**（`core/query.py`）：机制——行 = 记录 + `definedIn`/`classes`（后两个不进索引）、给了选择器就只查那一个对象（含继承链、子覆盖父）／认不出给空表、**两种跨对象口径各钉一遍**（`POOL` 按名收一遍先到先占 / `EACH` 每对象一行 + 按（名字，所属对象）排序）、口径写错当场炸；入口——`Query(source)` 绑出 `search(object, keyword)`/`describe(object)`，来自共用件、别名与口径取 `source` 那两份、载荷只取 `objects` |
| `database/core/test_render.py` | 断言 17 | 属性库共用的表格渲染：整列都是 `None` 就不占列（**键缺失与 `None` 同等看待**）、截断（最后一列分隔线用该列自己的 `sep`）、列表拼接、提示文案与标题的 `subject`/`note`；**对象头**（没给对象就不印、给了就只加一行、原文没给的项整项略去、超长截到 80 字、解析到了但筛完没匹配**也印**） |
| `database/core/test_registry.py` | 断言 34 | 属性库发现：四个库都在、顺序稳定、接口齐全（**含 `parse`/`decorate`——"每个库必须切成三层"是个契约**）、**落点**（①② 在自己的 `core/` 下、**声明在库根的 `index.py`**、**查询入口来自共用件**）、**四个库的入口是同一个函数对象**、`DOC` 讲的是共用参数名 `object`、各库 `render` 前四参 `rows/object/keyword/obj`、坏树被判据挡下 |
| `database/test_index.py` | 断言 11 | **顶层联合**（`database/index.py`）：单库输出与各库自己的 `render` **逐字相同**、跨库只印有结果的库且节首 `── <库名> ──`、都没结果时的合并提示、库名不认识要抛错并列出可选值、工具描述里拼进了各库的 `DOC` |
| `database/db/core/test_parse.py` | 断言 2 | **① 如实层**（`core/parse.py`）：`fixtures/raw/` 的自造片段 → `parse()` 的**整体输出**（标题、h3 归属、表前正文、格子、`<br>` 分段） |
| `database/db/core/test_decorate.py` | 断言 17 | **② 归一**（`core/decorate.py`）：`fixtures/html/` 4 份官方片段回放（逐条比 `parent` + 自身属性记录 `name/modify/type/desc`；切片边界、表内/表前两种父写法都在这露头）+ 自造 HTML 钉住 `include` 三种拼法与笔误、`<br>` 的两义、大写开头的名字、曾被噪声词吃掉的 `name`/`value` + **记录按 `ATTR_KEYS` 建、原文的 `modify` 与推出来的 `rw` 并存、`_rw_from_modify` 的三态** + 构建期校验（键集不齐、父认不出、成环都要抛） |
| `database/db/test_index.py` | 断言 15 | **③ 声明**（`index.py` 的 `LIB`）：选择器解析（表标题／运行时名／忽略大小写空格／兼容别名／认不出）、继承合并（子覆盖父 + `definedIn`、纯转发 0 条→7 条）、本库的别名表非空、跨对象口径 `POOL` |
| `database/techdb｜cdfdb｜dd/core/test_parse.py` | 断言 2/2/2 | **① 如实层**（`core/parse.py`）：`fixtures/raw/` 的自造片段 → `parse()` 的**整体输出**（techdb 是每个 h3 小节 + Description + Attributes 格子；cdfdb 是每个 h4 小节的正文与表格；dd 是该小节里有哪几张表、每张表的格子） |
| `database/techdb｜cdfdb｜dd/core/test_decorate.py` | 断言 16/16/13 | **② 归一**（`core/decorate.py`）：`fixtures/html/` 的片段回放——**同形、逐条比该对象的全部属性记录**（techdb 比 `name/desc`，cdfdb 另比 `source`，dd 比"六个对象各自的记录名"）+ 各库的自造 HTML 脆技巧（techdb 的类段语法与续行、cdfdb 的手写白名单与空首锚点 h4 与实参补录、dd 的表头签名挑表、对象全集取自最全的关系行、**物化**——每条记录落到它适用的每个对象下、以及"适用对象不在全集里要炸"）。**② 把话说全**：各有一条断言钉"记录按 `ATTR_KEYS` 建、推出来的与原文的并存"，并把**推法逐档钉住**（techdb 的 `_type_from_desc`、cdfdb 的 `_type_from_name_desc`/`_rw_from_desc`、dd 的 `cardinality` 只有关系才有） |
| `database/techdb｜cdfdb｜dd/test_index.py` | 断言 18/15/16 | **③ 声明**（`index.py` 的 `LIB`）：检索（选择器／别名／跨类各出一行／**跨对象按名去重**）、本库自己那两句（`aliases`、`cross`）、构建期校验（**顶层三键 / `lib` 与库名 / 两层键集** / 空类 / 重名 / 类名不是标识符 / 基数不像 `1:n` / 同名既是属性又是关系） |

合计 **165 份 golden + 517 条断言**（四个属性库的索引都在时是 **522**——多出来的 5 条是
`test_server` 里那些需要真索引才跑的回显断言）。其中 **`test_server` 的几条是环境相关的**：它真起服务走
stdio，属性库索引不可用时那几次调用记 SKIP、对应的回显断言也跟着跳过，所以计数随本机有没有
索引而变（上面这个数取自"四个属性库索引都不可用"的情形）。

另有 `tests/knowledge_virtuoso/test_server.py`（镜像 `server.py`）：把服务当**子进程**起起来、
走真实 MCP 协议、列工具并逐个调用。它补的正是渲染回归测不到的那一段——`server.py` 的接线。
两种跑法都行：`run_tests.py` 会带上它（静默、结果变断言），**启动 Claude 之前也建议单独跑
一遍**（`uv run python -B tests/knowledge_virtuoso/test_server.py`，打每个调用的明细）。
没索引时查询按 **SKIP** 处理：`report.skip()` 只计数、不算过也不算错，汇总里会写"跳过 N 次"。

## fixture 从哪来

- 四个属性库的 `database/<库>/core/fixtures/html/`：**官方 doc 的 HTML 片段**（属性解析器的
  输入）+ 同名 `.json`（期望值 = 线上索引里对应的那部分），由 `tests/tools/capture_attrs_html.py` 切出。
- **四个属性库的 `database/<库>/core/fixtures/raw/`（② 之前那半）**：**自造**的小片段
  （几百字节）+ 同名 `.json`（期望值 = `core/parse.py` 的 `parse()` 输出，**录下来的**）。
  这一层**没有线上对照**——索引里只有 ② 归一后的形状——所以它比别处更像"变更探测器"：
  改动解析器时它只说"raw 变了"，对不对得人来判。因此**只用自造片段**、不拿 44 KB 的官方片段
  再存一份；官方片段那半由 `fixtures/html/` 覆盖（它比的是 `extract_all`，即 ① 之后接 ②）。
  `dd` 也有这一层（它现在同样有 ①／② 之分）。
- `functions/sources/official/fixtures/html/`：**官方 doc 的 HTML 片段**（解析器的输入）+
  同名 `.json`（期望值 = 线上索引里的记录），由 `tests/tools/capture_official_html.py` 切出。
- `functions/sources/official/fixtures/`：从本机索引录的**真实记录**（`index.query_function`）。
  27 个名字各挂一条已记录的边界：ROD 的参数预算与子参数 `lists`、`hiSetCursor` 的
  `text_fallback` 正文、`absAbstract` 4.6 万字的选项字典、`assoc` 的共享声明、`pstddev`
  只有 `definition`、`abeLayerGrow` 的默认值片段……
- `functions/sources/custom/fixtures/syntheticUniqueFunc.json`：**手写**的 v3 信封（官方没有同名函数）。
- 四个属性库：`search_*_attr()` 返回的行，放在各自的 `cases/<用例>.json`。`techdb` 的
  `cases/rw_shown.json` 例外——该库索引里 `rw` 恒为 `?`，"显示 rw 列"那一支走不到，所以是
  手写行（文件里标了 `"synthetic": true`）。

## golden 的性质：变更探测器，不是正确性判据

它只证明**输出没变**，不证明输出本来就对。**没有输出变化就不要 `--update`**，
否则等于把回归网剪掉。搬移类改动（行为必须逐字不变）除了跑本套，还要**让改动前的代码
重放同一套 golden**：

```bash
# 任一旧版本都行；用 importlib 从路径载入旧模块，逐条调用它的入口，与 golden 比
git show <旧版本>:src/knowledge_virtuoso/server.py > /tmp/server_head.py
```

它证"没变"，**不证"搬对了"**——新增的接缝（如 `render_search_page`）旧代码根本产不出对应输出。

## 覆盖不到什么

- **`server.py` 的接线**（哪个工具调哪个渲染函数、参数怎么传）：由 `test_server.py` 真起一次
  子进程来验——它**在**测试网里（改名进镜像就是为这个），改了服务入口或 MCP 接口就会被它
  挡一下。它验的是"起得来、三个工具都在、八种调用都不报错"，**不比对输出内容**（那是 golden
  的事）。
- **`sources/official/catalog.py` 的解析器**（936 行 HTML 解析）：由
  `sources/official/test_catalog.py` 用**官方 doc 的最小片段**覆盖（族的清单见下）。每份
  片段**单独**喂解析器，产出与线上索引里那条记录**逐字段相同**——夹具切得不全、或解析口径
  变了，这里就红。**长尾仍罩不住**（笔误标题只取到一两个实例、同名合并只有片段里那一条），
  所以真机改动后仍要跑一次全量比对：

  ```bash
  # 重建到临时文件，与在用的索引逐字节比（同样内容产出同样字节，能这么比）
  uv run python -B -m knowledge_virtuoso.functions --doc-root <doc> --export-json ./_check.json
  sha256sum ./_check.json "$VIRTUOSO_DATA_DIR/functions/index.json"; rm ./_check.json
  ```

  这条比对是**必须**的：搬移时 `_NAME_RE`/`_PREFIX_RE` 曾随契约去了 `core/contract.py` 而
  引用留在原地，`build_entries` 与 `--report` 因此 NameError——golden 全绿、查询照常
  （索引还在），只有真跑一次重建才看得见。片段夹具能挡住这一类（它对每份片段都真的跑
  `build_entries`/`_extract_full_from_topic`），但挡不住"只在别的排版族里出错"——那只有
  逐字节比对能查出来。
- **四个属性库的解析器**（`extract_all = decorate ∘ parse`：attrib.html / appA.html /
  chap21.html / chap3.html）：由四库的 `core/test_decorate.py` 用**官方 doc 的片段**覆盖
  （每库 1–4 份，各自 `fixtures/html/`；片段 = 解析器会看成一段的那块 HTML，期望值取自线上
  索引），另用 `fixtures/raw/` 的自造片段单独钉 **① 如实层**（`parse()` 的输出形状）。db 现在
  是**按标题**解析（h4 = 一个对象），所以片段要从 `<h4` 起切。**长尾仍罩不住**：db 的 76 个
  对象只取了 4 份、techdb 11 个类只取了 2 个（白名单过滤这一支真文件里走不到，只能自造 HTML 钉）。
  改了解析器仍要跑一次全量比对：`knowledge-virtuoso-build <库名>
  --output ./_check.json`，与平台数据目录里那份逐字节比，比完删掉。
- `tests/tools/` 三个采集脚本只在需要重采夹具时手动跑，不在 `run_tests.py` 里。

### 片段夹具覆盖的格式族（`fixtures/html/`）

片段由 `tests/tools/capture_official_html.py` 从本机官方 doc 切出，出处与切法写在该目录的
`README.md` 里；每份 `.html` 旁边是同名 `.json`（线上索引里的记录，即期望值）。

| 片段 | 覆盖的族 |
|---|---|
| `topic/hiSetCursor.html` | 裸 `<tr>` 续排的大表（`</table>` 之后仍续排；全库独一份，94 条） |
| `topic/rodCreatePath.html` | 节内子范围标题（`Arguments<br><br>Master Path Arguments`）、超长声明、4 个子参数列表按类型名连回根参数、返回表里的编号步骤要跳过 |
| `topic/error.html` | 合并标题后半是**独立节**（`Arguments<br>Values Returned`）、返回节只有散文 → `text_fallback` |
| `topic/evalstring.html` | 允许取值表（`'symbol` 行收成参数的 `values`） |
| `topic/pcreCompile.html` | 首列被占位的续排行按名称行收条目 |
| `topic/gdmstatus.html` | 首列被占位 + 名称与说明同格（真参数不能被丢） |
| `topic/absAbstract.html` | 节里明写 None → `documented_none`；2 万字的选项字典 |
| `topic/awvCreateBus.html` | 只有 `definition`、没有 `description` |
| `topic/asiMapInstanceName.html` | 官方笔误标题 `value returned\` 也要认成返回值节 |
| `page/ccpGetAutoRename.html` | 标记协议 + 一个标记含多个函数标题（按 `<h3>` 切分） |
| `page/caaar.html` | 名字在散文里列出（一个 topic 展开 28 个名字）+ 共享声明取同 topic 的 `<dl>` |

四个属性库的片段同理（`tools/capture_attrs_html.py` 切，出处写在各库 `fixtures/html/README.md`），
每份是"该库解析器会看成一段"的那块 HTML：

| 片段 | 覆盖的族 |
|---|---|
| `db/…/section_cellview.html` | 节短语 → 下一个 `<h3` 的整节（62 条属性）；`rw` 由 Modify 列判 |
| `db/…/section_inst.html` | 另一节（33 条）；同名属性跨节合并归属 |
| `db/…/shape_pathSeg.html` | 形状标题**取最后一次出现**（11 条；真文件里每个形状标题出现 2 次） |
| `db/…/shape_rect_note_only.html` | 该节原文只写"include Generic Shape Attributes"、没有属性表 → 归属名字集合为空（矩形属性全部来自 Generic 层与继承链） |
| `techdb/…/class_viaDefs.html` | `techID~>` 的 `<h3>` 段：Description/Attributes 两个 h4 小节、名称行与续行 |
| `techdb/…/class_layers.html` | 另一个类段（10 条） |
| `cdfdb/…/class_cdfDataId.html` | `<h4><a>字段名</a></h4>` 字段区 + `Displaying Parameters` 表 |
| `cdfdb/…/class_cdfParamId.html` | 另一个类的字段区 + 手写补录属性（`SUPPLEMENT_PARAM_ATTRS`） |

**片段末尾要带"下一个标题的开头"当边界记号**：三个解析器都靠"到下一个标题为止"收尾
（db 找 `<h3`、cdfdb 用 `(?=<h4|<h3|…)` 前瞻），片段若正好切在边界上，这个标记就不在片段
里了，于是退化成兜底截断——db 只取前 15000 字符（62 条属性会只剩 19 条）、cdfdb 的显示表
整张取不到。`tools/capture_attrs_html.py` 的 `with_boundary()` 就是补这个。

## 体积与许可

`tests/` 约 2.4 MB：golden 与各处 `fixtures/html/` 都含 Cadence 官方文档的原文摘录。
函数库片段合计约 406 KB（两个大份 `rodCreatePath` 155 KB、`absAbstract` 130 KB——它们的内容
本身就是被测的排版族，不能再删）；四个属性库片段合计约 169 KB（`section_cellview` 44 KB
最大）。golden 单个最大 `absAbstract.full.txt` 51 KB。

**已决定**：只放**最小片段**（每族一份，够解析即可），不放整章；出处、切法与体积记在
`fixtures/html/README.md`。若要进一步缩小暴露，改 `tools/capture_official_html.py` 的
`TEST_TARGETS`（减族）后重跑，测试会自己报出缺了哪些夹具。
