# knowledge_virtuoso

独立开发、维护的 Virtuoso 官方知识库，通过 MCP stdio 提供 SKILL 函数文档与 db、techdb、cdfdb 属性查询。以标准 Python 包发布，外部项目可用 `uvx` 免克隆引用。本服务不连接 Virtuoso，不执行 SKILL，不依赖 Bridge、VMware 或自建函数库。

公开仓库：<https://github.com/Ergou-TwoDog/knowledge_virtuoso>

## 安装与运行

### 作为 uvx 工具（外部使用方）

需要本机已安装 uv。无需克隆仓库，在使用方的 MCP 配置中一行引用：

```json
{
  "mcpServers": {
    "virtuoso": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Ergou-TwoDog/knowledge_virtuoso", "knowledge-virtuoso"]
    }
  }
}
```

`uvx` 会从 git 解析、构建并运行 `knowledge-virtuoso` 入口，依赖（`mcp==1.9.4`）自动装入隔离环境；可加 `@v0.2.2` 固定版本。本项目不修改使用方配置。

**首次使用前必须让服务找到官方 doc，否则每次查询都会失败。** 索引不随包分发，只落在平台数据目录；服务在启动和建立连接时都不读索引，所以**「连接成功、工具列表正常」并不代表可查询**——索引缺失要等第一次查询才暴露。二选一：

```bash
# ① 在启动 MCP 客户端的环境里设置；只在进程启动时读取，改后须重启客户端
export VIRTUOSO_DOC_DIR='/path/to/IC618/doc'        # bash / Git Bash
# PowerShell 用：$env:VIRTUOSO_DOC_DIR = 'D:\path\to\IC618\doc'
# （PowerShell 的 set 是 Set-Variable 的别名，set VAR=... 不设置环境变量）

# ② 或预生成索引（functions / db / techdb / cdfdb）
uvx --from git+https://github.com/Ergou-TwoDog/knowledge_virtuoso knowledge-virtuoso-build functions
```

两者都没有时，查询会**报错**并给出索引路径与修复命令，不会返回空结果。若改写进 MCP 配置的 `env`，`"${VIRTUOSO_DOC_DIR:-}"` 只是**转发**启动环境的值，环境里没有就等同未设置；要写字面路径，只能放在使用方自己的私有配置里。重建与恢复细节见「索引恢复与官方文档」。

### 本项目开发

从仓库根用 uv 管理环境；首次 `uv run` 自动创建 `.venv/` 并安装依赖：

```bash
uv sync                     # 显式同步环境（可选，uv run 会自动同步）
uv run knowledge-virtuoso   # 启动 MCP 服务（stdio）
```

## 目录结构

```text
knowledge_virtuoso/
├── README.md
├── CLAUDE.md
├── pyproject.toml      # 构建与依赖声明；首次 uv 运行生成 uv.lock
├── .gitignore
├── tests/              # 测试网：与 src 同构的镜像树 + 真实 MCP 冒烟（见 tests/README.md）
│   ├── run_tests.py    # 跑全部；--update 重录 golden
│   ├── tools/          # 夹具生成器（不是测试；见 tests/tools/README.md）
│   └── knowledge_virtuoso/     # 镜像 src（含 test_server.py：真起一次服务走 MCP 协议）
└── src/
    └── knowledge_virtuoso/          # 唯一顶层包
        ├── __init__.py  __main__.py
        ├── server.py                # MCP 服务入口（main()）；只做接线
        ├── _paths.py                # 索引目录定位与原子写
        ├── cli.py                   # knowledge-virtuoso-build
        ├── functions/               # 函数库：跨来源层 + 与来源无关的技术件 + 来源树
        │   ├── index.py             #   跨来源：装配编排（发现并合并各来源）与查询/搜索/建议
        │   ├── registry.py          #   跨来源：扫描 sources/ 发现来源 + 按记录选来源的渲染配置
        │   ├── __main__.py          #   开发入口（--sources 看发现到哪些来源）
        │   ├── README.md            #   本层设计：分层、记录契约、解析边界、渲染取舍（随包）
        │   ├── core/                #   与来源无关：记录契约、信封读写、渲染主干
        │   │   ├── contract.py      #     记录契约与校验
        │   │   ├── envelope.py      #     v3 信封的读/写
        │   │   └── render.py        #     渲染主干（五档、策略表、省略指针）
        │   └── sources/             #   来源树：**加一棵树即加一个来源，别处不用改**
        │       ├── official/        #     官方：解析 IC618 doc、索引重建、覆盖率报告
        │       │   ├── __init__.py  #       来源接口（NAME/LABEL/REQUIRED/ORDER/CORPUS/…）
        │       │   ├── catalog.py
        │       │   └── render.py    #       本渲染差异（官方无额外标记）
        │       └── custom/          #     二次开发：读外部产出的 v3 信封
        │           ├── __init__.py
        │           ├── catalog.py
        │           └── render.py    #       本渲染差异（（自定义）标记 + load() 前提行）
        └── database/
            ├── index.py                 # 一个查询工具、四个库（按 lib 路由、留空跨库）
            ├── core/                    # 与"是哪个库"无关的机制
            │   ├── objects.py           #   载荷模型：三层键集、构建期校验、记录构造、选择器、继承合并
            │   ├── assembly.py          #   装配：一份声明 → 载荷包装 + 索引存取 + CLI
            │   ├── query.py             #   查询：机制（选择器 → 记录池 → 行）+ 入口 Query(LIB)
            │   ├── render.py            #   渲染机制（各库只声明一份 RenderSpec）
            │   ├── store.py             #   索引存取（读 JSON / 坏了从 doc 重建 / 缓存 / 锁）
            │   └── registry.py          #   属性库发现（扫 database/ 自动发现）
            ├── db/                      # 基本数据库对象属性
            │   ├── __init__.py          #   库接口（REQUIRED_ATTRS）+ 一份 RenderSpec
            │   ├── index.py             #   ③ 声明：LIB = Library(库名/版本/来源文档/别名/口径/本库校验)
            │   └── core/parse.py        #   ① 如实（不解释格子）
            │       decorate.py          #   ② 归一（+ 本库的推法）
            ├── techdb/                  # 技术库对象属性（同上：__init__ / index / core 两个）
            ├── cdfdb/                   # CDF 对象属性（同上）
            └── dd/                      # 数据管理对象属性与关系（同上）

`db/core/README.md` 与 `dd/core/README.md` 记该库的原文事实与设计取舍；四个库的对照表见
`database/core/README.md`。
```

函数库**按来源分树**：每个来源一棵 `sources/<来源>/`（该来源的索引本事 + 渲染差异），来源树之间**互不认识**；与来源无关的放 `core/`；跨来源的只有两件事——`registry.py` 负责**扫描 `sources/` 自动发现**（顺序由各来源自己的 `ORDER` 决定，不看目录名），`index.py` 负责把它们装配成一张索引并在这上面查询。**加一个来源 = 在 `sources/` 下加一棵树**，`core/`、`registry.py`、`index.py`、`server.py` 都不用改。四个属性库（db/techdb/cdfdb/dd）**互相独立**：每个库把"怎么读原文"按**三层**放在自己的目录下（① 如实的解析器 ② 归一成统一载荷 ③ 查询与装配），渲染只声明一份 `RenderSpec`。上层由 `database/core/registry.py` **扫描 `database/` 自动发现**（各库在自己的 `__init__.py` 里声明 `NAME`/`SELECTOR`/`DOC` 与几个函数）——**加一个属性库 = 在 `database/` 下加一棵树**，`server.py`、`cli.py` 一行不用改。它们的索引存取（读 JSON、坏了从官方 doc 重建、缓存与锁）收敛在 `database/core/store.py` 一份里——那是**去重**，不是来源抽象。渲染层只做"记录/行 → 文本"，不 import `mcp`、不 import 来源、不读索引、不做 I/O。`server.py` 只做接线：校验参数 → 查 catalog → 交给对应渲染层；所以改输出不必碰 MCP 接口，改工具契约（名字、参数、docstring）也不必碰渲染层。**包内不含索引**——索引写到平台数据目录（见下），因此 wheel 体积小、可反复 `uvx` 冷启动。

维护对象为包内解析器、工具与索引；不直接手改生成 JSON。**索引字段、解析边界、设计原则与工具层取舍都在随包发布的 [src/knowledge_virtuoso/functions/README.md](src/knowledge_virtuoso/functions/README.md)**（设计文档不单独放在仓库里）。原文地址按实际 IC618 doc 根目录拼接 `source.file` 与 `source.anchor`，相对参考链接以 source.file 所在目录解析。

### 开发验证

根据改动范围验证 CLI、查询和恢复逻辑。**改解析或渲染后跑 `uv run python -B tests/run_tests.py`**（golden 逐字节比对 + 断言，不需要 IC618 doc 或索引）；搬移类改动（行为必须逐字不变）还要拿另一份代码重放同一套 golden 做双向验证。golden 是**变更探测器，不是正确性判据**——它只说明输出没变；**没有输出变化就不要 `--update`**，否则等于把回归网剪掉。修改服务入口或 MCP 接口时，通过实际 stdio 客户端完成初始化、工具列表和相关工具调用（渲染回归不覆盖 `server.py` 的接线）；修改路径定位时，同时验证项目内启动与外部工作目录启动，并核对构建产物（wheel/sdist）内容。接口调整需核对参数与返回的兼容性。

使用 `uv run python -B` 避免生成字节码缓存；测试索引恢复时用临时输出目录（如把 `VIRTUOSO_DATA_DIR` 指向临时目录），不删除或覆盖正式索引模拟故障。验证结束后清理临时材料，不默认保留测试脚本或报告。

## MCP 接入

### 本项目

本仓库自测用的 MCP 配置是**本地文件、不随仓库分发**的：`.mcp.json` 已列入 `.gitignore`，克隆后需自行创建（`<仓库绝对路径>` 替换为本仓库实际位置）：

```json
{
  "mcpServers": {
    "virtuoso": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "<仓库绝对路径>", "knowledge-virtuoso"],
      "env": {
        "PYTHONDONTWRITEBYTECODE": "1",
        "VIRTUOSO_DOC_DIR": "${VIRTUOSO_DOC_DIR:-}",
        "VIRTUOSO_DATA_DIR": "${VIRTUOSO_DATA_DIR:-}",
        "VIRTUOSO_CUSTOM_INDEX": "${VIRTUOSO_CUSTOM_INDEX:-}"
      }
    }
  }
}
```

项目根 `.mcp.json` 由 Claude Code 按**路径**加载，与是否被 git 跟踪无关，所以忽略它不影响本机生效（仍会经过项目级配置的信任确认）。手动协议入口为 `uv run knowledge-virtuoso` 或 `python -m knowledge_virtuoso`。这不是交互式查询终端，stdin/stdout 专用于 MCP。加载配置或重启客户端后使用；Claude Code 中完整工具名通常带 `mcp__virtuoso__` 前缀。

### 外部项目引用

见「作为 uvx 工具」；无需克隆或复制资产。若要指向本地克隆而非 git 源，可用 `uvx --from <本地路径> knowledge-virtuoso`。移除使用方的 virtuoso 配置并重新加载客户端即可停止接入。

## 三个查询工具

以下是 MCP 参数，不是 SKILL 代码，也不要求安装同名 slash skill。

| 工具 | 参数 | 示例 |
|---|---|---|
| `skill_language_search_components` | `prefix=""`, `keywords=""`, `offset=0`, `limit=30` | `{"prefix":"db","keywords":"create rect"}` |
| `skill_language_search_doc` | 必填 `func_name`, `detail="brief"`, `sections=null` | `{"func_name":"dbCreateRect","detail":"full"}` |
| `search_attr` | `lib=""`, `object=""`, `keyword=""` | `{"lib":"db","object":"rect","keyword":"bBox"}` |

`search_attr` 一个工具覆盖**四个属性库**：`lib` 取 `db`（设计库）／`techdb`（技术库）／`cdfdb`（CDF）／`dd`（数据管理）之一，**留空就四个都搜**（四库的对象名实测两两不重，所以跨库搜不会歧义——`object="rect"` 只可能命中 `db`）。`object` 是四库**共用**的选择器参数名，但各库认的写法不同（表标题／运行时名／兼容别名 vs 类名 vs 数据管理对象），工具描述里按库分段讲清。

返回：给了 `lib` 就是那个库的输出（命中时会先回显"问的是谁"，见下）；留空则每库一节、节首一行 `── <库名> ──`，**只印有结果的库**。

函数搜索至少提供 prefix/keywords 一个非空条件，结果行默认**附带一行摘要**（`with_digest=false` 只要名字与来源，每行省约 100–200 字）。，主要匹配名称及拆词，不是自然语言语义搜索。关键词按**驼峰自动拆词**，且对无边界写法兜底——`createRect`、`create rect`、`createrect`、完整名 `dbCreateRect` 都能命中，不必手动拆分；offset 非负，limit 为 1–500，按返回的 next offset 翻页。查询单函数（`skill_language_search_doc`）与搜索（`skill_language_search_components`）未命中时都会给出相近名建议（搜索建议限同前缀内）。

详情粒度（五档）：**`digest`** 一行摘要（名字 + 有界签名 + 描述首句 + 返回 + 来源，硬上限 900 字，全库实测 max 798），用于在候选之间**挑函数**；**`skel`** 调用骨架（完整签名 + 校验行 + 每个参数的「关键字 类型」+ 取值/默认**原文**+ 返回 + 来源），用于**写调用**——`rodCreatePath` 从 brief 的 25,082 字降到 6,006 字，全库 skel 合计为 brief 的 35%；`signature` 只给主声明及必要说明（弃用、共享声明归属）；`brief` 另加描述、来源、参数（含 ROD 子参数列表的嵌套渲染与该参数的允许取值）与返回值，以及"缺了就写错或写不出调用"的节——前置条件、交互式提示、关联选项；`full` 再加选项说明、示例、补充说明、相关函数、参考链接、回调模板、其他声明与解析状态。**任何档位只要省略了内容，都会输出一行 `省略: <省了什么> → detail="X"`**（机器可识别），省略的内容一律能在指明的档位里逐字取回；`digest`/`skel` 里重排的只有签名的换行（去掉空白后与原文逐字相同），其余内容都是原文。**选项说明属"选项字典"**（`abs*` 家族单函数可达 4.8 万字），进 brief 会让 brief 无上界，故只在 full 给，brief 以一行指针代替（`选项说明:（N 条，X 字；detail="full" 取）`）。描述超长会明确标注截断字符数，不静默省略；来源写作 `文件[#锚点]`，锚点与函数名相同时不重复。**哪些节进哪一档由 `functions/core/render.py` 的策略表决定，改它不需要重建索引**（索引如实收录官方 doc 的全部节）。参考链接去掉锚点（页内 `#787126` 与跨页 `…#PCRE_CASELESS` 都去）并同名去重，跨页链接以方括号标注所在文件（`strcmp [stringfunc.html]`，不用圆括号以免被读成函数调用）；techdb 的 `rw` 列在该库恒为 `?`，无信息量时省略。

参数表的**校验行**：渲染器同时握着 `decl` 与参数表，名字对不上时输出一行（74 个函数），例如 `校验: 签名 43 个 ?参数 / 参数表 40 个 ?参数；?cvId 在参数表写作 ?cdId（疑官方笔误，以原文为准）`，并列出"签名有而参数表未列／参数表有而签名未见"的名字——照参数表写却对不上签名时能立刻看出来。签名含 `?参数` 而官方未给参数说明的 14 个函数，输出 `参数:（官方未提供参数说明；签名含 N 个 ?参数，见来源原文）`，以免被读成"不吃参数"。

参数与返回值除结构化条目外，还会输出**条目之外的正文**（brief 档同样给，截断 600 字并标注）：老式排版把表格单元格散排成 `<p>`、或整节就是散文时，只有正文承载这些内容。块标题会把状态说清楚——`参数正文（条目之外，原文散文，非结构化条目）`，或 `返回正文（官方原文未结构化，以下照录原文）`（`unparsed` 时写"未能可靠提取"）；已渲染过的条目文本不与正文重复，残段不足 40 字则不输出。

**参数块的篇幅预算**（仅 brief 档）：参数块超过 12,000 字时，保留每个参数的**首行**与含 `Default`／`Valid Values`／`取值` 的行，其余说明续文移入 `full`，并在块尾标注 `（已把 N 个参数的说明续文移到 detail="full"，共 X 字；参数名、允许取值与 Default 均完整保留）`。`full` 档不受影响。实测只影响 4 个函数（`rodCreatePath`、`rodCreateRect`、`hiCreateAppForm`、`hiCreateReportField`）；参数密集但没有长散文的（如 `hnlInitMap`）不触发。

`解析状态` 只报需要留意的异常——`text_fallback`、`unparsed`、`shared_declaration`——且用中文措辞、不暴露内部字段名与枚举值（如 `解析状态: 示例节官方原文未能可靠提取`）；参数/返回值正文块的标题已写明状态的节不重复列。`not_documented`/`documented_none`（"官网上没有"而非异常）不逐条列出，需要时回查索引的 `field_status`。不能根据空数组猜测没有参数或返回值。

**二次开发函数（custom）**：索引可另加载与本库同构的 custom 索引（见「索引恢复与官方文档 → 自定义（二次开发）索引」）。这类条目渲染时标为 `自定义`——`digest` 与搜索摘要的名字带 `（自定义）`，`signature`/`brief`/`full`/`skel` 各档另多一行 `状态: 自定义函数（二次开发），需先 load("src/…") 才能调用`（`load()` 前提取自记录的 `origin_meta.custom.load`）。官方条目没有该行。

输出形式约定（便于程序化切分）：单行项用行内前缀（`函数:`、`签名:`、`描述:`、`来源:`、`解析状态:`），多行块用独占一行的节标题（`参数:`、`返回:`、`示例:`）——块内条目再缩进一层，`主参数组 […]`／`子参数 […]（属于 …）` 标识分组，不与参数条目同级。用两行正则即可切分：块标题 = `^[^ \t].*:$`（行首无空格且以冒号结尾），块内条目首行 = `^ +.+? — `（行首有空格、含 ` — `），其后缩进更深的行属于上一条目。

属性工具的 `object` / `keyword` 留空分别表示"该库全部对象""该对象全部属性"。**db 与 techdb、cdfdb、dd 的数据模型不能混用**——`lib` 就是用来分开它们的；跨库搜索只在"对象名"这一层合并，行与列仍各按各库的格式出（所以是**每库一节**，不是拼成一张表）。

**对象头**：选择器解析到时，输出第一行回显"这次问的是谁"——`{"lib":"db","object":"rect"}` 会先印 `对象 Rectangle  title=Rectangle Attributes  section=…`，这样用别名（`rect`）或运行时名（`cellview`）提问时也看得出解析成了什么；命中但筛完没结果时同样印这一行（"认出来了但没有匹配"与"压根没认出来"因此分得开）。跨库时库名由节首那行给。

不经 MCP 查询单个函数：

```bash
uv run python -m knowledge_virtuoso.functions dbCreateRect           # 默认 brief 档
uv run python -m knowledge_virtuoso.functions dbCreateRect -d skel   # 五档同 MCP
uv run python -m knowledge_virtuoso.functions --sources              # 列出发现到的来源
```

输出与 MCP 的 `skill_language_search_doc` **逐字一致**（同一个渲染入口，含 `（自定义）`
标记与 `load()` 前提行）——排障时看到的形状就是 LLM 看到的形状。从官方 doc 重建/导出见
`--doc-root … --report | --export | --export-json`。

## 索引恢复与官方文档

**索引不随仓库或包分发**，写到平台数据目录：

| 平台 | 默认目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\knowledge-virtuoso\` |
| macOS | `~/Library/Application Support/knowledge-virtuoso/` |
| Linux | `$XDG_DATA_HOME/knowledge-virtuoso/`（未设则 `~/.local/share/knowledge-virtuoso/`） |

可用环境变量 `VIRTUOSO_DATA_DIR`（绝对路径）覆盖。五个库各占一份 `<目录>/<库>/index.json`（`functions`、`db`、`techdb`、`cdfdb`、`dd`）。索引目录在进程启动时读取，改后需重启服务。

函数库索引是**紧凑 JSON 经 gzip 压缩**的（约 2 MB，加载时自动解压），因此不能直接查看或 grep，排障用 `gzip -dc <索引> | head`；四个属性库索引仍是明文 JSON。

索引**格式**变了会自动判为不兼容并触发重建；但**内容**改进不会——0.1.7 补上了老式排版的两类表结构（裸 `<tr>` 续排的表、首列被占位的表行），格式仍是 v3，因此**已有的旧 v3 索引不会自动重建**。升级到 0.1.7 后需跑一次 `knowledge-virtuoso-build functions`（或删除该索引让服务按惰性重建），才能用上改进后的内容。

四个属性库各带一份**载荷格式版本**与一个**类型区分字段**（都写进索引 JSON 顶层：`version` 与 `lib`）：版本或 `lib` 对不上就当损坏——有 `VIRTUOSO_DOC_DIR` 就自动重建，没有就明确报"索引不可用"（报错里带实际值与所需值）。四个库现在都是 **v5**（顶层 `version`/`lib`/`objects` 三键；对象层七键 + 记录层九键 `ATTR_KEYS`；`rw`/`type` 这类呈现值由 ② 算好落盘）；**把某一份索引拷到别的库的目录下会被当场拒绝**（`lib` 与目录名对不上），**旧形状的索引会被自动识别并重建，都不需要手动删**。

0.2.0 没有改索引格式：改的是**包内模块路径**（函数库按来源分树、渲染层从 `server.py` 抽出）与一处契约校验（`returns` 条目必须带 `desc`）。**升级不需要重建索引**；但若你有脚本按旧模块路径导入（如 `knowledge_virtuoso.functions.core.catalog`），要一并改。

0.2.1 修掉 0.2.0 引入的一处残缺，**不改索引格式、不需要重建索引**：

- **重建路径恢复**：0.2.0 那次搬移把两个模块级正则（`_NAME_RE`、`_PREFIX_RE`）留在了 `core/contract.py` 而引用留在 `sources/official/catalog.py`，于是**从官方 doc 重建索引的那条路**（`knowledge-virtuoso-build functions`，以及索引丢失时的惰性重建）会 `NameError`；查询不受影响（索引还在就照常读）。修完实测重建产物与在用索引**逐字节相同**。
- **开发入口与 MCP 逐字一致**：`python -m knowledge_virtuoso.functions <函数>` 的输出现在就是 `skill_language_search_doc` 的输出（含 `（自定义）` 标记与 `load()` 前提行），并支持 `-d/--detail` 五档与 `-s/--sections`。此前它自己拼了一套简化输出，排障看到的形状与 LLM 看到的不同。
- 三个属性库的索引存取（读 JSON、坏了从官方 doc 重建、缓存与锁）从三份逐字复制收敛为 `database/core/store.py` 一份——**去重**，属性库仍不分来源。

**若你停在 `v0.2.0`**：不需要重建索引就照常可用；一旦要重建（索引丢失/损坏，或想用新解析产物），请升到 0.2.1。

0.2.2 属性库重构：上层统一 + 新增 `dd` 库，**索引格式不兼容**：

- **四个属性库各存各的、互不认识**；上层由 `database/core/registry.py` 扫描 `database/` **自动发现**，`server.py` 按发现的库生成 MCP 工具（工具名 = `<库名>_search_attr`，第一个参数名 = 该库自己的选择器：`objType`/`className`/`object`）。
- **db/techdb/cdfdb 的载荷容器统一到 `database/core/objects.py` 的对象模型**（`{version, objects: {id: {id, title, parent, attrs}}}`）：校验、选择器解析、继承合并都收在那份共享件里，各库只剩**解析器 + 别名表 + 行工厂 + 一份列声明**（表格渲染也收在 `database/core/render.py`——四份渲染器的差别全在列上）。「有没有继承」不用旗子标——没有继承的库 `parent` 恒为 `null`，合并自动塌缩成自身。四库对照见 `src/knowledge_virtuoso/database/core/README.md`。**渲染输出一行未变**（golden 零变化）。
- **dd 不在这套容器里**：它原文是转置的（一条记录列适用对象），套进来要物化 3.4×——那与「忠实还原」相悖。
- **加一个属性库 = 在 `database/` 下加一棵树**，`server.py`、`cli.py` 一行不用改。
- **新增第 6 个工具 `dd_search_attr`**：数据管理对象（`lib`/`cell`/`view`/`libFile`/`cellFile`/`viewFile`）的属性与关系。**原文没有类型也没有说明**（dd 节 `<img>` 为 0，印刷版承载这两张表的正文 1728/1729 页里绘图指令也为 0——原文那张类型图例所指的图并不存在），所以输出只有 name/kind/基数/适用对象——不是解析漏了。
- **techdb 改为每个类各存自己的属性**：此前是"全局按属性名去重"，24 个跨类同名属性只留第一个类的说明与类型，实测 **8 处类型与该类原文不符**（`snapPatternDefs~>layer` 显示 `l_objId`，而该类原文推出来是 `l_string`——这在渲染里看得见）。**跨类查询现在每个类各出一行**，不再合并。类说明改用原文的 `Description`，不再用手写的 11 条中文。
- **cdfdb 同样改为逐类存储**（两个类零重名，输出不变）。`parseAsNumber` 从"手写补录"回到字段区（原文那个 h4 的首个锚点是空的，旧正则匹配不到）；`name`/`description` 仍是补录，但标出来源，且 `description` 的说明**如实留空**（原文没给）。
- **不兼容**：db/techdb/cdfdb 的载荷格式都变成 v2，旧索引会被自动识别并重建（设了 `VIRTUOSO_DOC_DIR`）或明确报"索引不可用"（没设）。升级后跑一次 `knowledge-virtuoso-build <库>` 即可，或设好 `VIRTUOSO_DOC_DIR` 让服务惰性重建。

0.2.3 属性库三层收口：源码切成 ①如实 / ②归一 / ③声明，装配与查询收进 `core/`，四个库共用一个查询入口——**索引格式 v3 → v5（要重建）、MCP 接口不兼容**。以下五段是这五步的经过：

**属性库分层：①解析器 / ②装饰器 / ③统一渲染器，db/techdb/cdfdb 的索引冻结为 v3**（索引格式不兼容）

- **三库的索引格式定稿为 v3**：对象字典的公共键固定七个（`id · title · runtime · section · desc · parent · attrs`，原文没给的写 `null`），构建期校验键集。定键的判据是「**能完整保留下、且能加深 LLM 理解与区分每条数据**」的字段，不是「今天的代码读不读它」。
- **索引只存原文事实**：techdb 的 `type`（由该类说明推）与 cdfdb 的 `rw`/`type` 不再入库，改在查询时现算（db 一直是这个规矩——它存原文的 `modify`，`rw` 是查询时收成两值的）。正因为索引里再没有推出来的值，`null` 只能表示"原文没给"，所以七键可以放心用 `null` 补齐。
- **描述不再截断**：原来 cdfdb 拿**未截断**的正文判 `rw`、却只存**截断后**的 `desc`，于是索引里的 `rw=ro` 并不是它自己存的那条事实的函数（`paramType` 的 "This field is not editable." 在**第 275 字**）。现在 `desc` 存全，截断是渲染列的事。
- **每个库切成三层**：① `parse(doc)` 如实还原原文结构（有哪些标题/小节、每节后面是哪张表、表里有哪些格子，**不解释格子**）、② `decorate(raw)` 归一成七键载荷、③ 各库声明一份 `RenderSpec`、由 `database/core/render.py` 的 `render_attrs()` 渲染。四个 `render.py` 文件删除；`extract_all = decorate ∘ parse` 保持不变。
- **输出多了一行"对象头"**：选择器解析到时，最前面回显"这次问的是谁"——`objType="rect"` 现在看得见解析成了 `Rectangle`（此前只有"匹配 25 个属性"，认没认出来无从判断）；techdb 的类说明（原文的 `Description` 小节）此前**存进索引却从没显示过**，现在也印在这一行里。**选择器命中但筛完没结果时同样印**——「认出来了但没有匹配」与「压根没认出来」这才分得开。跨对象查询与未命中不印。
- **不兼容**：db/techdb/cdfdb 的索引格式从 v2 变 v3，旧索引会被自动识别并重建（设了 `VIRTUOSO_DOC_DIR`）或明确报"索引不可用"（没设，报错里带实际版本与所需版本）。**dd 当时不动、仍是 v2**——随后一轮也并了进来（见下一段）。
- **渲染的表格部分一行未变**：13 份渲染 golden 逐字节不变，另 4 份（带选择器的）**只多了那行对象头**；三库重建产物与在用索引 sha256 相同，重复重建也一致。

**四个属性工具合并成一个 `search_attr`**（MCP 接口不兼容，索引不用重建）

- **`db_search_attr` / `techdb_search_attr` / `cdfdb_search_attr` / `dd_search_attr` 四个工具没了**，换成一个 `search_attr(lib, object, keyword)`：`lib` 选库（`db`/`techdb`/`cdfdb`/`dd`），**留空搜全部四个**；`object` 是四库共用的选择器参数名（各库原先那个名字——`objType`/`className` 退成库内部的词汇，仍用于解析与报错文案）。
- **使用方要改的是提示词与脚本里的工具名与参数**：`{"objType":"rect","keyword":"bBox"}` → `{"lib":"db","object":"rect","keyword":"bBox"}`。
- **索引一份没动**：仍是四份文件（各自版本 v3/v2、各自惰性重建、一个坏了不牵连另一个），联合只发生在进程内（`database/index.py`，位置与角色对着 `functions/index.py`）。**不用重建索引**。
- **单库调用的输出与原来逐字相同**（合并工具不该改变任何人已经看到的文本）；跨库调用另立格式：每库一节、节首 `── <库名> ──`、只印有结果的库。
- 工具描述由 `database/index.py` 现场拼（总说明 + 各库自己的 `DOC`），所以**加一个属性库仍然只加一棵树**，描述里自动多一段。

**dd 并入统一容器**（它的索引格式 v2 → v3）

- **dd 的载荷摊成与另三库同形的七键容器**：原文那条"一条记录 + 后面列适用对象"的**转置**表，在 ②（`core/decorate.py`）里摊到它适用的**每个对象**下。于是联合查询、渲染的对象头、`validate_objects` 的校验对四个库**一视同仁**，不必为一个库开特例。
- **代价是副本**：22 条记录 → 6 个对象共 **74 条**（3.36×，几 KB）。`objectTypes` 每条都留着——它是原文的原话，"索引只存事实"靠它才成立；行里那列「适用对象」也照旧。
- **dd 现在也有对象头**：`lib="dd", object="cellFile"` 的第一行是 `对象 cellFile`（它的对象记录里除 `id` 全是空的——原文只给了这六个名字）。
- **跨对象（不给 `object`）按名去重**，与 db 同口径——它的表有「适用对象」列，逐对象分行只会印出重复行。
- **不兼容**：dd 的索引格式从 v2 变 v3，旧索引会被自动识别并重建（设了 `VIRTUOSO_DOC_DIR`）或明确报"索引不可用"。**其余三个库的索引没动。**

**记录层也定键集、查询收进共用件**（四个库的索引格式 v3 → v4）

- **记录层有了一套公共键**（`ATTR_KEYS`：`name · kind · type · rw · desc · modify · source · cardinality · objectTypes`），与对象层那七键一样在**构建期校验**、缺则 `null`、顺序即落盘字节。此前只统一到"对象"这一层，盒子统一了、盒子里那一条条记录仍各是各的形状。
- **推出来的值改在 ② 算好落盘**：db 的 `rw`（由原文的 `modify` 收成两值）、techdb 的 `type`（由该类自己的说明推）、cdfdb 的 `rw`/`type`（散文与名字里推）。**原文那一侧照旧原样留着**（`modify`、`source`、`objectTypes`），两类并列写进同一条记录，所以"原文怎么写的"与"我们怎么呈现的"都还在索引里。**代价是改推法必须重建**——推法从此冻结在盘上（各库 `core/test_decorate.py` 逐档钉住推法）。
- **查询逻辑收进 `database/core/query.py`**（四库共用一份）：库根的 `index.py` 只剩装配（校验/版本/索引存取/CLI）与**两句政策**——`_ALIASES`（别名表）、`_CROSS`（跨对象口径）。口径仍是各库的事实（db/dd 按名去重、techdb/cdfdb 每对象一行），但它现在是一句**声明**而不是各写一遍的代码。行 = 记录 + `definedIn`/`classes` 两个查询上下文字段。
- **dd 的选择器改用共用件**：原先它自己抄了一份简化版 `_resolve`，现在走四库共用的解析，因此**多认一种写法**（带空格/下划线的 `lib_file` 之类也能命中）——只放宽，不改任何已经认得的写法。
- **顺带修掉描述里的参数名**：合并成一个工具之后，各库 `DOC` 里仍写着 `objType:`/`className:`，而工具的真参数只有 `lib`/`object`/`keyword`——照着描述填会因 schema 不符失败。现在四库统一写 `object:`。
- **不兼容**：四个库的索引格式从 v3 变 v4，旧索引会被自动识别并重建（设了 `VIRTUOSO_DOC_DIR`）或明确报"索引不可用"（报错里带实际版本与所需版本）。升级后跑一次 `knowledge-virtuoso-build <库>`，或设好 `VIRTUOSO_DOC_DIR` 让服务惰性重建。
- **渲染输出一行未变**：165 份 golden 逐字节不变（改的只有喂给渲染器的用例输入——旧的两个占位值 `?`/`""` 换成 `null`），四库重建与再次重建逐字节一致。

**装配收进共用件、每个库只剩一份声明**（索引格式 v4 → v5）

- **索引顶层多一个 `lib`（类型区分字段）**，与 `version` 一起让索引"自证身份"：装载时拿它与库名/目录名核对，**对不上就当损坏**——把 `dd` 的索引拷到 `db` 的目录下会被当场拒绝（`索引里的 lib='dd' 与它所在的库 'db' 不符（放错目录了？）`），而不是拿它当好的用、给出看着正常的结果。**只打在顶层**：800 多条记录逐条带一个同样的常量，换不到别的东西。
- **装配收进 `database/core/assembly.py` 的 `Library`、查询入口收进 `core/query.py` 的 `Query`**：库根的 `index.py` 从"四十来行实现"缩成**一份声明**——库名、载荷版本、来源文档、①② 两层、别名表、跨对象口径、本库自己的构建期校验。`payload`（打版本与 `lib` + 校验）、`build`/`load`（索引存取）、`main`（库里自带的小 CLI）由 `Library` 出；`search`/`describe` 由 `Query(LIB)` 现绑——**装配归装配、查询归查询**。加一个属性库现在只需写 ① ② 两棵树 + 一份声明。
- **查询本来就只有一个实现**：四个库的 `search.__func__` 是**同一个函数对象**（绑定不同而已），差别只在绑进去的别名表、跨对象口径与哪份索引。所以不需要"每个库一个 search"——而把别名/口径塞进索引来"省一个绑定"也不值得（别名是**使用者的词汇**，不是原文事实）。
- **库不再有自己的选择器参数名**：`SELECTOR` 这个接口项取消，四库共用一个 `object`（与工具的参数名一致）；各库"额外认哪些写法"退成 `LIB.aliases` 一张表。`registry` 的守卫因此换成更强的一条：**查询入口必须来自共用件**——自己写一个 `search` 会被发现时警告并跳过（以前查的是"声明的选择器名在不在签名里"，那是"每库一套参数名"时代的守卫）。
- **顺带把没命中时的提示统一**：此前 db 写 `objType='…'`、另三家写 `类='…'`/`对象='…'`，而工具的参数名是 `object`——现在四处都写 `object='…'`。**4 份 golden 因此各改一行**（`cases/miss.txt`）。
- **不兼容**：四个库的索引格式从 v4 变 v5，旧索引会被自动识别并重建（设了 `VIRTUOSO_DOC_DIR`）或明确报"索引不可用"。**MCP 接口不变**：工具、参数、其余 161 份 golden 一字未动。
- 新增 `database/core/test_assembly.py`（装配：载荷三键与 `lib`、校验顺序、CLI）与 `core/test_query.py` 里的 `Query` 那几条（入口来自共用件、签名、别名/口径取声明）；`core/test_registry.py` 从 37 条降到 34 条——**掉的是四个库各查一遍"选择器名在不在自己签名里"**，那正是这一版取消掉的东西，现在由"入口来自共用件"+ "四个库共用同一个函数对象"管住。

**五库统一惰性重建**：查询时加载对应 JSON；缺失、损坏或空记录时，若进程环境设了 `VIRTUOSO_DOC_DIR`（真实 IC618 doc 根），自动从官方 doc 重建、原子写回索引目录并返回结果；未设则报出含索引路径与修复提示的错误（提示运行 `knowledge-virtuoso-build`）。首次全量函数重建可能较慢，重建日志写 stderr。

函数库另有内存层：**健康内存 → 有效 JSON → 官方 doc 构建非空索引、原子写盘、发布内存**；全部失败则报告实际原因。读取、解析或写入失败不发布半成品。函数内存健康检查只检查 ready、字典类型、非空主索引与长度快照，不检测等量篡改或嵌套损坏；正常内存不自动热更新，零匹配不触发重建。

设置 VIRTUOSO_DOC_DIR（Git Bash 示例）：

```bash
export VIRTUOSO_DOC_DIR='/path/to/IC618/doc'
```

doc 根需直接包含 `sklangref/`、`skdfref/`、`sktechfile/`、`skartistref/` 等目录。随后从此环境启动 MCP 客户端；修改另一终端的环境不会改变已有进程。doc 必须可读，索引目录必须可写。属性库各自读取对应 HTML（见「显式重建」），缺失字段不猜测。

每个 stdio 客户端通常启动独立进程，共享磁盘索引但不共享内存。单进程内用 RLock 保护加载与重建；没有跨进程写入协调，并发首查可能同时触发同一索引重建。维护重建建议停止相关服务、避免并行写入；更新后重启所有相关服务。本项目不提供网络服务或跨进程锁。

### 自定义（二次开发）索引

**产出方要读的是 [src/knowledge_virtuoso/functions/core/SPEC.md](src/knowledge_virtuoso/functions/core/SPEC.md)**——信封与记录的逐字段要求、自查命令、最小可运行样例都在那里（随包发布）。下面只讲使用方怎么接。

MCP 工具除官方索引外，还可**同时加载多个与本库同构的 custom 索引**，用环境变量 `VIRTUOSO_CUSTOM_INDEX` 配置（`os.pathsep` 分隔多项；每项是索引文件，或含若干 `*.json` 的目录）。custom 索引须是**同样的 v3 envelope**（`{schema_version:3, corpus, functions:{<名>:<记录>}}`），由二次开发工具（如 `skill_dev_kit`）自行产出，本项目**不产出、不修改**它。变量在进程启动时读取，改后需重启服务。

例（`skill_dev_kit` 产出并把 MCP 指向它）：`python tools/gen_records.py src/ --json --out records.json`（省略 `--out` 则信封打到 stdout），再将 `VIRTUOSO_CUSTOM_INDEX` 设为 `records.json`（或它所在目录）。

加载与合并规则：官方索引恒为基准；custom 逐源读取，**坏源（缺失、损坏、非 v3 envelope、记录不合法）跳过并在 stderr 警告，不影响官方查询**；同名时**custom 覆盖官方**（二次开发的定位即扩展／打补丁），遮蔽写 stderr 警告。custom 记录比官方多三处扩展位 `origin`／`origin_meta`／`lint`，渲染时据此标注（见「三个查询工具」）；官方条目无这些键、行为不变。**未设该变量时，加载与渲染与只用官方索引时逐字一致。** 自定义索引只在**函数库**（`skill_language_*`）生效，四个属性库不读它。

## 显式重建

不依赖查询触发，用 `knowledge-virtuoso-build` 预生成索引（默认写入平台数据目录）：

```bash
knowledge-virtuoso-build functions
knowledge-virtuoso-build db
knowledge-virtuoso-build techdb
knowledge-virtuoso-build cdfdb
knowledge-virtuoso-build dd
```

本项目开发时用 `uv run knowledge-virtuoso-build <库>`；包已安装时可直接调用脚本名。`functions` 取 `VIRTUOSO_DOC_DIR` 或 `--doc` 作为 doc 根；属性库 `--doc` 取对应 HTML（默认 `skdfref/attrib.html`、`sktechfile/appA.html`、`skartistref/chap21.html`）。`--output` 可覆盖写入位置。重建结束后重启服务。

## 边界与排查

- 这是文档知识，不是当前 Virtuoso 会话的对象，也不验证许可证、上下文或真实调用结果。写 SKILL 前仍须查询函数签名/对象属性，写后仍须在 Virtuoso 真实执行验证。
- 索引不是全部官方文档的无损镜像，不保证全覆盖。共享声明不代表每个成员有独立签名；遇到字段缺失或正文约束，应按返回的来源回查原文。db/CDF 输出可能截短描述。
- 服务找不到入口：检查客户端 cwd 与 args；找不到 uv：确认 uv 已安装且在客户端 PATH 中（否则 `command` 用 uv 绝对路径）；索引缺失且无 `VIRTUOSO_DOC_DIR`：设置该变量或运行 `knowledge-virtuoso-build`；写入失败：检查 `VIRTUOSO_DATA_DIR`/平台目录的权限与空间；更新后仍旧：重启服务。
- 官方 doc 及派生索引为只读参考；共享厂商文档及派生索引应遵守相关许可。
