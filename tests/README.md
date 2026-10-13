# 测试：`tests/knowledge_virtuoso/` 与 `src/knowledge_virtuoso/` 同构

```bash
uv run python -B tests/run_tests.py                    # 全部（自动发现镜像树下所有 test_*.py）
uv run python -B tests/run_tests.py functions/core     # 只跑镜像路径里含这段的
uv run python -B tests/run_tests.py --update           # 重录 golden
uv run python -B tests/capture_fixtures.py             # 重新采集 fixture（需本机索引）
```

每个 `test_*.py` 也能**单独直跑**（如
`uv run python -B tests/knowledge_virtuoso/functions/core/test_contract.py`）。
不需要 IC618 doc、不需要索引、不需要网络：fixture 就是被测层的输入。
不引第三方依赖，只用标准库；文本一律 UTF-8 + LF 落盘（`.gitattributes` 里
`* text=auto eol=lf`——行尾被 checkout 改掉会让 golden 全红）。

## 结构：测试文件放在它测的模块的同路径下

```
tests/
├── README.md · common.py · run_tests.py · capture_fixtures.py     # 公共件（不对应任何 src 模块）
└── knowledge_virtuoso/                    # 镜像 src/knowledge_virtuoso
    ├── functions/
    │   ├── test_index.py · test_registry.py
    │   ├── core/          test_contract.py   test_envelope.py   test_render.py
    │   │                  fixtures/ golden/                      # 该层自己的数据
    │   └── sources/
    │       ├── official/  test_render.py   fixtures/ golden/
    │       └── custom/    test_catalog.py   test_render.py   fixtures/ golden/
    └── database/
        ├── db/            test_render.py   fixtures/ golden/
        ├── techdb/        同左
        └── cdfdb/         同左
```

两条规矩：

1. **fixture 与 golden 跟着被测对象走**（放在那个 `test_*.py` 旁边），每个模块自成一格，
   改了谁就只动谁的目录。
2. **镜像目录里绝不放 `__init__.py`**。镜像顶层目录名与真包同名，一旦成了常规包就会在
   `sys.path` 上**抢先**真包（实测：只要没有 `__init__.py`，真包是常规包、
   仍然优先命中）。测试模块因此按**文件路径**载入，不按包名 import。

## 两种检查，各管一件事

| | 写法 | 测什么 | 用在哪 |
|---|---|---|---|
| **golden 比对** | `report.check(用例, got, golden 路径, update)` | 输出**变没变** | 渲染（`render_entry` 五档、三个属性库的表格） |
| **断言** | `report.expect(用例, 实际, 期望)` / `report.truthy(用例, 条件, 说明)` | 行为**对不对** | 契约、信封、装配、发现——"对错"能直接判的 |

`Report.summary()` 把两类分开报（`N 份 golden 一致` / `N 条断言通过`）。

## 各模块锁什么（当前 11 个）

| 镜像路径 | 类型 | 锁什么 |
|---|---|---|
| `functions/core/test_contract.py` | 断言 28 | 记录的接受/拒绝（**拒绝消息按完整字符串断言**）、分词、派生键被重算 |
| `functions/core/test_envelope.py` | 断言 13 | 信封往返、gzip 与明文、版本/形态拒绝、写入可复现、路径规范化 |
| `functions/core/test_render.py` | golden 8 | 未命中、搜索零命中（有无相近建议）、搜索页正文 |
| `functions/test_index.py` | 断言 25 | 装配计划（同一文件不当两个来源）、合并与遮蔽、坏源跳过、健康检查、查询/搜索/建议、构建落盘 |
| `functions/test_registry.py` | 断言 16 | 发现到谁、按 `ORDER` 升序、恰好一个基准、接口齐全、渲染配置分派 |
| `functions/sources/official/test_render.py` | golden 135 | 27 条官方记录 × 五档 |
| `functions/sources/custom/test_render.py` | golden 5 | `（自定义）` 标记 + `load()` 前提行——"只因来源不同"的那几行 |
| `functions/sources/custom/test_catalog.py` | 断言 15 | `VIRTUOSO_CUSTOM_INDEX` 解析（多项/目录/去重/不存在的路径照收）、相对路径出声、进程内缓存、`owns` |
| `database/db｜techdb｜cdfdb/test_render.py` | golden 4/5/4 | 三个属性库的表格渲染（列宽、截断、`rw` 列两支） |

合计 **161 份 golden + 97 条断言**。

## fixture 从哪来

- `functions/sources/official/fixtures/`：从本机索引录的**真实记录**（`index.query_function`）。
  27 个名字各挂一条已记录的边界：ROD 的参数预算与子参数 `lists`、`hiSetCursor` 的
  `text_fallback` 正文、`absAbstract` 4.6 万字的选项字典、`assoc` 的共享声明、`pstddev`
  只有 `definition`、`abeLayerGrow` 的默认值片段……
- `functions/sources/custom/fixtures/synthetic.json`：**手写**的 v3 信封（官方没有同名函数）。
- 三个属性库：`search_*_attr()` 返回的行；`database/techdb/fixtures/rw_shown.json` 例外——
  该库索引里 `rw` 恒为 `?`，"显示 rw 列"那一支走不到，所以是手写行（文件里标了
  `"synthetic": true`）。

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

- **`server.py` 的接线**（哪个工具调哪个渲染函数、参数怎么传）：改了服务入口或 MCP 接口，
  要真起 stdio 客户端调一遍，不能以导入成功代替。
- **`sources/official/catalog.py` 的解析器**（936 行 HTML 解析）：**目前没有直接测试**——
  要测它得引入官方 doc 的 topic HTML 当夹具（厂商原文整段进公开仓库的许可问题还没定），
  或者手写极小的排版用例。现状只靠 `test_render` 的录制记录与"从 doc 重建时的一致性"兜底。
- **三个属性库的 `core/catalog.py`**（检索与解析）：只测了渲染那一半。
- `tests/capture_fixtures.py` 只在需要重采 fixture 时手动跑，不在 `run_tests.py` 里。

## 体积与许可

`tests/` 约 1.4 MB，golden 含官方文档原文摘录（单个最大 `absAbstract.full.txt` 51 KB）。
这些是派生自 Cadence 官方 doc 的内容，随公开仓库分发前应确认符合其许可。
