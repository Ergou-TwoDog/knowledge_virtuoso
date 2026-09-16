# knowledge_virtuoso

独立开发、维护的 Virtuoso 官方知识库，通过 MCP stdio 向本项目及外部项目提供 SKILL 函数文档与 db、techdb、cdfdb 属性查询。外部项目直接引用共享入口，无需复制资产。本服务不连接 Virtuoso，不执行 SKILL，不依赖 Bridge、VMware 或自建函数库。

## 独立开发

所有命令均从本项目根目录执行。Python 要求 3.10+；源项目已验证 Python 3.14.3、mcp 1.9.4，最低 Python 版本未单独验证。启动服务的解释器必须已安装依赖；本项目不自动创建虚拟环境或安装依赖。需要安装时由维护者自行执行：

```bash
python -m pip install -r requirements.txt
```

可自行选择已有虚拟环境的解释器；MCP 的 `command` 必须指向实际安装 mcp 的 Python。

```text
knowledge_virtuoso/
├── README.md
├── CLAUDE.md
├── requirements.txt
├── .gitignore
├── .mcp.json
└── lib/
    ├── server.py
    ├── functions/
    │   ├── __init__.py
    │   ├── core/__init__.py
    │   ├── core/catalog.py
    │   └── data/
    │       ├── index.json
    │       └── mapping.md
    └── database/
        ├── __init__.py
        ├── db/       # __init__.py、core/__init__.py、core/catalog.py、data/index.json
        ├── techdb/   # 同上
        └── cdfdb/    # 同上
```

`lib/` 是资产容器，不是安装包，无需根或 lib 的 `__init__.py`。`core/` 存实现，`data/` 存正式索引；三个属性库保持独立。server 将自身目录加入 `sys.path`，内部使用 `functions` / `database` 包；在 Python 中直接导入这些包时，也须先将 lib 放入模块搜索路径。四个默认索引均按 catalog 自身位置定位，不依赖 cwd。lib 不从根 README、CLAUDE 或 requirements 加载运行代码。

资产目录说明见 [lib/README.md](lib/README.md)。

维护对象为 lib 中解析器、工具和索引；不直接手改生成 JSON 作为日常维护方式。字段与解析边界见 [lib/functions/data/mapping.md](lib/functions/data/mapping.md)。原文地址按实际 IC618 doc 根目录拼接 `source.file` 与 `source.anchor`，相对参考链接以 source.file 所在目录解析。

### 开发验证

根据改动范围验证 CLI、查询和恢复逻辑。修改服务入口或 MCP 接口时，通过实际 stdio 客户端完成初始化、工具列表和相关工具调用；修改路径定位时，同时验证项目内启动和外部工作目录启动。接口调整需核对参数与返回的兼容性。

使用 `python -B` 避免生成字节码缓存；测试索引恢复时使用本项目内的临时输出，不删除或覆盖正式索引模拟故障。验证结束后清理临时材料，不默认保留测试脚本或报告。单纯迁移或重构应核对索引内容未变；数据更新则应检查新增、减少和解析状态的变化。

## MCP 接入

### 本项目

根 `.mcp.json` 已提供以下配置，要求客户端从本项目根启动：

```json
{
  "mcpServers": {
    "virtuoso": {
      "type": "stdio",
      "command": "python",
      "args": ["lib/server.py"]
    }
  }
}
```

手动协议入口为 `python -B lib/server.py`。这不是交互式查询终端，stdin/stdout 专用于 MCP。加载配置或重启客户端后使用；Claude Code 中完整工具名通常带 `mcp__virtuoso__` 前缀。

### 外部项目引用共享资产

在使用方配置中自行合并以下服务项，不覆盖其他服务。此处仅提供示例，本项目不会修改使用方配置或 settings：

```json
{
  "mcpServers": {
    "virtuoso": {
      "type": "stdio",
      "command": "python",
      "args": ["D:/my_projects/knowledge_virtuoso/lib/server.py"]
    }
  }
}
```

绝对入口可从不同 cwd 启动；若安装位置变化，使用方需更新路径。代码本身不硬编码此绝对路径。移除使用方的 virtuoso 配置并重新加载客户端即可停止接入。旧副本保留，外部项目不会自动切换；建议以新独立项目作为后续维护中心。

## 五个查询工具

以下是 MCP 参数，不是 SKILL 代码，也不要求安装同名 slash skill。

| 工具 | 参数 | 示例 |
|---|---|---|
| `skill_language_search_components` | `prefix=""`, `keywords=""`, `offset=0`, `limit=30` | `{"prefix":"db","keywords":"create rect"}` |
| `skill_language_search_doc` | 必填 `func_name`, `detail="brief"` | `{"func_name":"dbCreateRect","detail":"full"}` |
| `db_search_attr` | `objType=""`, `keyword=""` | `{"objType":"rect","keyword":"bBox"}` |
| `techdb_search_attr` | `className=""`, `keyword=""` | `{"className":"viaDefs","keyword":"name"}` |
| `cdfdb_search_attr` | `className=""`, `keyword=""` | `{"className":"cdfParamId","keyword":"value"}` |

函数搜索至少提供 prefix/keywords 一个非空条件，主要匹配名称及拆词，不是自然语言语义搜索。支持完整函数名；offset 非负，limit 为 1–500，按返回的 next offset 翻页。

详情粒度：`signature` 返回主声明及必要说明/弃用提示；`brief` 加简短描述、来源定位、参数和返回值；`full` 另含可用的多声明、正文参数/返回说明、参数分组、示例、参考链接及异常字段状态。`text_fallback` 表示保留正文但未结构化，`unparsed` 表示未可靠提取；不能根据空数组猜测没有参数或返回值。

属性工具的对象类型/类名留空可跨类搜索，keyword 留空列出该类全部属性。db 与 techdb、cdfdb 的数据模型不能混用。

不经 MCP 查询单个函数：

```bash
python -B lib/functions/core/catalog.py dbCreateRect
```

## 索引恢复与官方文档

有效的四份 JSON 可独立查询，不需要原始 HTML 或安装 Virtuoso。首次函数查询加载整个索引到进程内存，只将查询结果返回给模型。

函数恢复链为 **健康内存 → 有效 JSON → 官方 doc 构建非空索引、原子写盘、发布内存**；全部失败则报告实际原因。JSON 缺失、损坏、空记录或版本不兼容时，查询可能触发写盘，默认位置为 `lib/functions/data/index.json`。显式索引路径写回显式位置。读取、解析或写入失败不发布半成品，日志写 stderr。

只有从 doc 恢复或显式构建时才需要官方 HTML。将 SKILL_DOC_DIR 设置为直接包含 sklangref/、skdfref/ 等目录的真实 doc 根，并让服务进程继承。Git Bash 示例：

```bash
export SKILL_DOC_DIR='/path/to/IC618/doc'
```

随后从此环境启动 MCP 客户端。修改另一终端的环境不会改变已有进程。Python 构建接口的显式 doc_root 优先。doc 必须可读，目标索引目录必须可写；全量恢复可能较慢。

函数内存健康检查只检查 ready、字典类型、非空主索引与长度快照，不检测等量篡改或嵌套损坏。正常内存不自动热更新；零匹配不触发重建，旧平铺 JSON 缺签名不从 HTML 补造。

**三级恢复只适用于函数库。** db、techdb、cdfdb 查询只读各自 JSON；缺失或损坏时报错，不自动从 doc 重建。

每个 stdio 客户端通常启动独立进程，共享磁盘资产但不共享内存。RLock 仅保护单进程；没有跨进程写入协调。维护重建应停止相关服务、避免并行写入；更新后重启所有相关服务。本项目不提供网络服务或跨进程锁。

## 显式重建

以下命令会更新正式索引，需维护者明确执行；文档路径请替换为实际位置。验证时应使用新项目内临时输出，禁止破坏正式 JSON。

```bash
python -B lib/functions/core/catalog.py --doc-root "/path/to/IC618/doc" --export-json lib/functions/data/index.json --report
python -B lib/database/db/core/catalog.py --doc "/path/to/IC618/doc/skdfref/attrib.html" --output lib/database/db/data/index.json
python -B lib/database/techdb/core/catalog.py --doc "/path/to/IC618/doc/sktechfile/appA.html" --output lib/database/techdb/data/index.json
python -B lib/database/cdfdb/core/catalog.py --doc "/path/to/IC618/doc/skartistref/chap21.html" --output lib/database/cdfdb/data/index.json
```

函数构建可设置 SKILL_DOC_DIR 后省略 --doc-root。重建结束后重启服务。

## 边界与排查

- 这是文档知识，不是当前 Virtuoso 会话的对象，也不验证许可证、上下文或真实调用结果。写 SKILL 前仍须查询函数签名/对象属性，写后仍须在 Virtuoso 真实执行验证。
- 索引不是全部官方文档的无损镜像，不保证全覆盖。共享声明不代表每个成员有独立签名；遇到字段缺失或正文约束，应按返回的来源回查原文。db/CDF 输出可能截短描述。
- 服务找不到入口：检查客户端 cwd 与 args；找不到 mcp：检查 command 所用解释器；JSON/doc 都不可用：恢复索引或设置 SKILL_DOC_DIR，属性库须显式重建；写入失败：检查目标路径、权限、空间；更新后仍旧：重启服务。
- 源项目、旧副本及官方 doc 为只读参考，复制不搬删。共享厂商文档及派生索引应遵守相关许可。
