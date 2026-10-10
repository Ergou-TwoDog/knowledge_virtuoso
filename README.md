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

`uvx` 会从 git 解析、构建并运行 `knowledge-virtuoso` 入口，依赖（`mcp==1.9.4`）自动装入隔离环境；可加 `@v0.1.5` 固定版本。本项目不修改使用方配置。

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
├── docs/
│   └── index-v3-design.md         # 索引 v3 设计（忠实还原 + 工具层取舍）
└── src/
    └── knowledge_virtuoso/          # 唯一顶层包
        ├── __init__.py  __main__.py
        ├── server.py                # MCP 服务入口（main()）
        ├── _paths.py                # 索引目录定位与原子写
        ├── cli.py                   # knowledge-virtuoso-build
        ├── functions/
        │   ├── core/catalog.py      # SKILL 函数解析、查询与恢复
        │   └── data/mapping.md      # 字段映射与解析边界（随包）
        └── database/
            ├── db/core/catalog.py       # 基本数据库对象属性
            ├── techdb/core/catalog.py   # 技术库对象属性
            └── cdfdb/core/catalog.py    # CDF 对象属性
```

`core/` 存解析与查询实现；db、techdb、cdfdb 各自独立、互不导入。**包内不含索引**——索引写到平台数据目录（见下），因此 wheel 体积小、可反复 `uvx` 冷启动。

维护对象为包内解析器、工具与索引；不直接手改生成 JSON。字段与解析边界见 [src/knowledge_virtuoso/functions/data/mapping.md](src/knowledge_virtuoso/functions/data/mapping.md)。原文地址按实际 IC618 doc 根目录拼接 `source.file` 与 `source.anchor`，相对参考链接以 source.file 所在目录解析。

### 开发验证

根据改动范围验证 CLI、查询和恢复逻辑。修改服务入口或 MCP 接口时，通过实际 stdio 客户端完成初始化、工具列表和相关工具调用；修改路径定位时，同时验证项目内启动与外部工作目录启动，并核对构建产物（wheel/sdist）内容。接口调整需核对参数与返回的兼容性。

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
        "VIRTUOSO_DATA_DIR": "${VIRTUOSO_DATA_DIR:-}"
      }
    }
  }
}
```

项目根 `.mcp.json` 由 Claude Code 按**路径**加载，与是否被 git 跟踪无关，所以忽略它不影响本机生效（仍会经过项目级配置的信任确认）。手动协议入口为 `uv run knowledge-virtuoso` 或 `python -m knowledge_virtuoso`。这不是交互式查询终端，stdin/stdout 专用于 MCP。加载配置或重启客户端后使用；Claude Code 中完整工具名通常带 `mcp__virtuoso__` 前缀。

### 外部项目引用

见「作为 uvx 工具」；无需克隆或复制资产。若要指向本地克隆而非 git 源，可用 `uvx --from <本地路径> knowledge-virtuoso`。移除使用方的 virtuoso 配置并重新加载客户端即可停止接入。

## 五个查询工具

以下是 MCP 参数，不是 SKILL 代码，也不要求安装同名 slash skill。

| 工具 | 参数 | 示例 |
|---|---|---|
| `skill_language_search_components` | `prefix=""`, `keywords=""`, `offset=0`, `limit=30` | `{"prefix":"db","keywords":"create rect"}` |
| `skill_language_search_doc` | 必填 `func_name`, `detail="brief"` | `{"func_name":"dbCreateRect","detail":"full"}` |
| `db_search_attr` | `objType=""`, `keyword=""` | `{"objType":"rect","keyword":"bBox"}` |
| `techdb_search_attr` | `className=""`, `keyword=""` | `{"className":"viaDefs","keyword":"name"}` |
| `cdfdb_search_attr` | `className=""`, `keyword=""` | `{"className":"cdfParamId","keyword":"value"}` |

函数搜索至少提供 prefix/keywords 一个非空条件，主要匹配名称及拆词，不是自然语言语义搜索。关键词按**驼峰自动拆词**，且对无边界写法兜底——`createRect`、`create rect`、`createrect`、完整名 `dbCreateRect` 都能命中，不必手动拆分；offset 非负，limit 为 1–500，按返回的 next offset 翻页。查询单函数（`skill_language_search_doc`）与搜索（`skill_language_search_components`）未命中时都会给出相近名建议（搜索建议限同前缀内）。

详情粒度：`signature` 只给主声明及必要说明（弃用、共享声明归属）；`brief` 另加描述、来源、参数（含 ROD 子参数列表的嵌套渲染与该参数的允许取值）与返回值，以及"缺了就写错或写不出调用"的节——前置条件、交互式提示、关联选项/选项说明；`full` 再加示例、补充说明、相关函数、参考链接、回调模板、其他声明与解析状态。描述超长会明确标注截断字符数，不静默省略；来源写作 `文件[#锚点]`，锚点与函数名相同时不重复。**哪些节进哪一档由 `server.py` 的策略表决定，改它不需要重建索引**（索引如实收录官方 doc 的全部节）。内部锚点清单与重复来源不输出；techdb 的 `rw` 列在该库恒为 `?`，无信息量时省略。`text_fallback` 表示保留正文但未结构化，`unparsed` 表示未可靠提取；不能根据空数组猜测没有参数或返回值。

属性工具的对象类型/类名留空可跨类搜索，keyword 留空列出该类全部属性。db 与 techdb、cdfdb 的数据模型不能混用。

不经 MCP 查询单个函数：

```bash
uv run python -m knowledge_virtuoso.functions.core.catalog dbCreateRect
```

## 索引恢复与官方文档

**索引不随仓库或包分发**，写到平台数据目录：

| 平台 | 默认目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\knowledge-virtuoso\` |
| macOS | `~/Library/Application Support/knowledge-virtuoso/` |
| Linux | `$XDG_DATA_HOME/knowledge-virtuoso/`（未设则 `~/.local/share/knowledge-virtuoso/`） |

可用环境变量 `VIRTUOSO_DATA_DIR`（绝对路径）覆盖。四个库各占一份 `<目录>/<库>/index.json`（`functions`、`db`、`techdb`、`cdfdb`）。索引目录在进程启动时读取，改后需重启服务。

函数库索引是**紧凑 JSON 经 gzip 压缩**的（约 2 MB，加载时自动解压），因此不能直接查看或 grep，排障用 `gzip -dc <索引> | head`；三个属性库索引仍是明文 JSON。

**四库统一惰性重建**：查询时加载对应 JSON；缺失、损坏或空记录时，若进程环境设了 `VIRTUOSO_DOC_DIR`（真实 IC618 doc 根），自动从官方 doc 重建、原子写回索引目录并返回结果；未设则报出含索引路径与修复提示的错误（提示运行 `knowledge-virtuoso-build`）。首次全量函数重建可能较慢，重建日志写 stderr。

函数库另有内存层：**健康内存 → 有效 JSON → 官方 doc 构建非空索引、原子写盘、发布内存**；全部失败则报告实际原因。读取、解析或写入失败不发布半成品。函数内存健康检查只检查 ready、字典类型、非空主索引与长度快照，不检测等量篡改或嵌套损坏；正常内存不自动热更新，零匹配不触发重建。

设置 VIRTUOSO_DOC_DIR（Git Bash 示例）：

```bash
export VIRTUOSO_DOC_DIR='/path/to/IC618/doc'
```

doc 根需直接包含 `sklangref/`、`skdfref/`、`sktechfile/`、`skartistref/` 等目录。随后从此环境启动 MCP 客户端；修改另一终端的环境不会改变已有进程。doc 必须可读，索引目录必须可写。属性库各自读取对应 HTML（见「显式重建」），缺失字段不猜测。

每个 stdio 客户端通常启动独立进程，共享磁盘索引但不共享内存。单进程内用 RLock 保护加载与重建；没有跨进程写入协调，并发首查可能同时触发同一索引重建。维护重建建议停止相关服务、避免并行写入；更新后重启所有相关服务。本项目不提供网络服务或跨进程锁。

## 显式重建

不依赖查询触发，用 `knowledge-virtuoso-build` 预生成索引（默认写入平台数据目录）：

```bash
knowledge-virtuoso-build functions
knowledge-virtuoso-build db
knowledge-virtuoso-build techdb
knowledge-virtuoso-build cdfdb
```

本项目开发时用 `uv run knowledge-virtuoso-build <库>`；包已安装时可直接调用脚本名。`functions` 取 `VIRTUOSO_DOC_DIR` 或 `--doc` 作为 doc 根；属性库 `--doc` 取对应 HTML（默认 `skdfref/attrib.html`、`sktechfile/appA.html`、`skartistref/chap21.html`）。`--output` 可覆盖写入位置。重建结束后重启服务。

## 边界与排查

- 这是文档知识，不是当前 Virtuoso 会话的对象，也不验证许可证、上下文或真实调用结果。写 SKILL 前仍须查询函数签名/对象属性，写后仍须在 Virtuoso 真实执行验证。
- 索引不是全部官方文档的无损镜像，不保证全覆盖。共享声明不代表每个成员有独立签名；遇到字段缺失或正文约束，应按返回的来源回查原文。db/CDF 输出可能截短描述。
- 服务找不到入口：检查客户端 cwd 与 args；找不到 uv：确认 uv 已安装且在客户端 PATH 中（否则 `command` 用 uv 绝对路径）；索引缺失且无 `VIRTUOSO_DOC_DIR`：设置该变量或运行 `knowledge-virtuoso-build`；写入失败：检查 `VIRTUOSO_DATA_DIR`/平台目录的权限与空间；更新后仍旧：重启服务。
- 官方 doc 及派生索引为只读参考；共享厂商文档及派生索引应遵守相关许可。
