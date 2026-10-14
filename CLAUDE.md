# 开发与维护约定

项目结构、接入方式、工具及索引恢复机制见 [README.md](README.md)；测试见 [tests/README.md](tests/README.md)；记录契约与渲染取舍见 [functions/README.md](src/knowledge_virtuoso/functions/README.md)。

- 修改限于本项目；官方原文和外部项目只读，不擅自修改使用方配置或全局环境。
- **按来源分树**：`functions/sources/<来源>/` 各成一棵树（`catalog.py` 该来源的索引本事、`render.py` 该来源的渲染差异、`__init__.py` 来源接口），来源树之间**互不认识**；与来源无关的放 `functions/core/`（记录契约、信封、渲染主干）；跨来源的只有两处——`registry.py` 扫描 `sources/` **自动发现**（顺序由各来源自己的 `ORDER` 决定，**绝不用目录名字母序**：改名不该改变"谁覆盖谁"；发现失败/接口不全的来源警告并跳过），`index.py` 装配成一张索引并查询。**加一个来源 = 在 `sources/` 下加一棵树，别处一行不用改**（`--sources` 可核对发现结果）。渲染层只做"记录/行 → 文本"，不 import `mcp`、不 import 来源、不读索引；`server.py` 只做接线（校验 → 查询 → 渲染）。四个属性库（`database/db|techdb|cdfdb|dd/`）**互相独立**（各自的 `core/catalog.py` + `render.py` + 索引），上层由 `database/core/registry.py` 扫描 `database/` **自动发现**（各库在自己的 `__init__.py` 里声明接口），校验/选择器/继承合并收在 `database/core/objects.py`、表格渲染收在 `database/core/render.py`（db/techdb/cdfdb 共用同一套载荷容器；dd 原文是转置的，站在容器之外，见 `database/core/README.md`）——**加一个属性库 = 在 `database/` 下加一棵树，别处一行不用改**（`knowledge-virtuoso-build libs` 可核对发现结果）。分隔符仍按"随包/不随包"：包内只放实现与随包文档（`data/`），索引不进包、写入平台数据目录且不随仓库分发；不为预期需求引入额外框架。
- 知识内容必须可追溯到官方文档；不得编造签名、属性或说明，保留解析缺失状态与共享声明的区别。
- 修改 MCP 接口或索引格式时检查兼容性，明确说明不兼容变化。
- 索引由解析器生成，不手工修补 JSON。恢复测试使用临时输出；非数据更新任务保持正式索引内容不变。
- 按改动范围验证 CLI、查询和恢复逻辑；涉及服务入口或接口时验证真实 MCP stdio 调用，不能仅以导入成功代替。**改解析或渲染后跑 `uv run python -B tests/run_tests.py`**；搬移类改动另用另一份代码重放同一套 golden 双向验证。golden 是**变更探测器，不是正确性判据**——它只说明输出没变、不说明输出对，**没有输出变化不要 `--update`**；它也覆盖不到 `server.py` 的接线，改了入口照旧跑 stdio。
- 验证使用 `uv run python -B`，临时材料限定本项目并在结束后清理。测试是**常驻资产**（`tests/` 进仓库）；临时的探针、报告、缓存不保留。
- 若编写 SKILL，先查真实函数签名及对象属性，完成后必须在 Virtuoso 真实执行验证；纯 Python 文档维护不要求调用 Bridge。
