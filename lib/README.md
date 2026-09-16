# Virtuoso 知识资产

本目录包含 Virtuoso 官方知识的解析与查询代码、JSON 索引，以及对外提供查询的 MCP stdio 入口。它是独立知识库项目的可复用资产，不包含使用方项目的业务逻辑。

服务不连接 Virtuoso、不执行 SKILL，也不依赖 Bridge。项目安装、开发维护及详细使用说明见 [项目 README](../README.md)。

## 目录结构

省略 Python 包初始化文件：

```text
lib/
├── README.md
├── server.py                      # MCP 服务入口
├── functions/
│   ├── core/catalog.py            # SKILL 函数解析、查询与恢复
│   └── data/
│       ├── index.json             # 官方函数索引
│       └── mapping.md             # 字段映射与解析边界
└── database/
    ├── db/
    │   ├── core/catalog.py        # 基本数据库对象属性
    │   └── data/index.json
    ├── techdb/
    │   ├── core/catalog.py        # 技术库对象属性
    │   └── data/index.json
    └── cdfdb/
        ├── core/catalog.py        # CDF 对象属性
        └── data/index.json
```

- `core/` 保存解析、查询实现，`data/` 保存生成的知识索引。
- db、techdb、cdfdb 使用各自独立的模块和数据。
- `server.py` 将自身目录加入 Python 模块搜索路径，导入 `functions` 和 `database`。
- 索引默认路径由各 `catalog.py` 的位置确定，不依赖客户端的工作目录。搬移时应保留完整内部结构。

函数字段说明见 [functions/data/mapping.md](functions/data/mapping.md)。

## 作为 MCP 服务使用

### 运行条件

启动服务的 Python 环境需安装 `mcp`；当前项目声明的依赖版本为 `mcp==1.9.4`，Python 要求 3.10+。依赖不会因复制资产而自动安装。

已有有效索引时，无需官方 HTML 或正在运行的 Virtuoso。只有函数索引需要从 doc 恢复、或维护者显式重建索引时，才需要官方文档。

### 本项目接入

从包含 `lib/` 的项目根目录启动客户端，使用项目根的 `.mcp.json`：

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

手动启动协议入口时，从项目根执行 `python -B lib/server.py`；若当前目录就是 `lib/`，执行 `python -B server.py`。该入口不是交互式查询终端，stdin/stdout 用于 MCP 通信。

### 外部项目引用

其他项目无需复制本目录，在自己的 MCP 配置中引用服务入口即可：

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

上述路径是当前部署示例，迁移后需更新使用方配置；代码本身不绑定该路径。`command` 必须使用已安装依赖的解释器，也可指向专用虚拟环境的 Python。

本目录在依赖已安装的前提下可以整体搬移；根 README、CLAUDE.md 和 requirements.txt 不是服务运行时读取的代码依赖。

## 查询工具

服务标识为 `virtuoso`，提供以下五个工具。参数示例是 MCP 输入，不是 SKILL 调用。

| 工具 | 作用 | 参数示例 |
|---|---|---|
| `skill_language_search_components` | 按完整名称、前缀或名称拆词搜索函数 | `{"prefix":"db","keywords":"create rect","offset":0,"limit":30}` |
| `skill_language_search_doc` | 查询函数签名和文档 | `{"func_name":"dbCreateRect","detail":"full"}` |
| `db_search_attr` | 查询基本数据库对象属性 | `{"objType":"rect","keyword":"bBox"}` |
| `techdb_search_attr` | 查询技术库对象属性 | `{"className":"viaDefs","keyword":"name"}` |
| `cdfdb_search_attr` | 查询 CDF 对象属性 | `{"className":"cdfParamId","keyword":"value"}` |

函数详情支持 `signature`、`brief`（默认）、`full`。需要正文说明、示例、参考及解析状态时使用 `full`。函数搜索的 `offset` 默认 0，`limit` 默认 30、范围 1–500；按结果中的下一页提示翻页。

## 数据加载与恢复

- **函数索引**：健康内存直接查询；内存未加载或基本检查失败时读取 JSON；JSON 缺失、损坏、空记录或不兼容时，尝试从官方 doc 重建 JSON，再发布内存。
- **官方文档路径**：函数自动恢复使用服务进程继承的 `SKILL_DOC_DIR`；Python 接口显式传入 `doc_root` 时优先使用该参数。恢复需要文档可读、索引目录可写。
- **数据库属性索引**：仅从各自 JSON 加载；缺失或损坏时报错，不自动从 doc 重建。显式重建命令见项目 README。
- **更新生效**：内存不自动热更新。修改代码或重建索引后，应重启使用方的相关 MCP 服务进程。

多个客户端通常各自启动 stdio 进程：共享磁盘资产，但不共享内存。当前锁只保护单个进程；维护重建应避免多个进程同时写入同一索引。

## 使用边界

- 索引是官方文档的提取结果，不是完整无损镜像，也不保证覆盖全部函数。
- 保留共享声明和字段解析状态；空字段不一定表示官方明确没有该内容。遇到缺失信息，应按返回的来源回查原文。
- 查询提供调用参考，不证明函数在某个 Virtuoso 版本、许可证或上下文中实际可用。
- 维护时修改解析代码并生成索引，不将直接手改 JSON 作为日常维护方式。
- 共享厂商文档及派生索引应遵守相应许可。
