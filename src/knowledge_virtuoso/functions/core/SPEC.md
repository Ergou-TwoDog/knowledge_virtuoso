# 产出规范：给函数库喂索引（PRODUCER SPEC）

**读者**：要产出索引给本服务消费的外部工具（如二次开发函数库的产生器）。
**依据**：`core/envelope.py`（文件层校验）与 `core/contract.py`（记录层校验）的实际行为；
文中每条拒绝/通过的判定都在 7667 个官方记录与本机实测上核过。

本规范只讲**你必须产出什么**。为什么要这么设计见 `../README.md`（本层设计说明）。

---

## 0. 两条接法

| 接法 | 你要做的 | 本项目改动 |
|---|---|---|
| **A. 产出信封文件 + 环境变量**（推荐） | 按本规范产出一份 v3 信封，把它（或其所在目录）写进 `VIRTUOSO_CUSTOM_INDEX` | **零** |
| B. 在 `functions/sources/` 加一棵来源树 | 实现来源接口的 10 项（`../README.md` §1.1）；`rebuild()` 可返回 `None` | 本项目同仓开发 |

除非你要与本项目同仓演进，用 **A**。

---

## 1. 文件层：信封（`core/envelope.py` 校验）

一个 JSON 对象：

```jsonc
{
  "schema_version": 3,            // 必须
  "corpus": { "product": "…" },   // 可选，内容不校验（建议写，便于排障）
  "functions": { "<函数名>": { …记录… } }   // 必须：非空对象
}
```

| 规则 | 违反时的结果（实测消息） |
|---|---|
| `schema_version` 必须是**整数 3** | 整个文件被拒：`索引格式版本不兼容（文件为 2，当前需要 3）` |
| `functions` 必须是非空对象 | 该源被**忽略**（警告 `{来源}索引为空，忽略: <路径>`），不是报错 |
| 其它顶层键 | 忽略 |
| 编码 | UTF-8 |
| 压缩 | 明文或 gzip 都行（按魔数 `1f 8b` 自动识别） |
| 后缀 | 目录形式只收 `*.json`；**直接给文件路径时不检查后缀** |

函数名就是 `functions` 的键：必须以小写字母开头、只含 `[a-zA-Z0-9_]`。

## 2. 记录层（`core/contract.py` 校验）

```jsonc
{
  "type": "function",
  "decl":  [ { "text": "myFunc( t_in ) => t_out", "shared_from": null } ],
  "where": { "file": "src/my/func.il", "topic": "myFunc",
             "marker_text": "myFunc", "anchor": "myFunc" },
  "also_at": [],
  "sections": { … },
  "field_status": { … },
  "status": "active"
}
```

| 字段 | 必需 | 类型要求 | 备注 |
|---|---|---|---|
| `type` | 否（但请写） | 字符串 | 当前恒为 `"function"`，不校验 |
| `decl` | **是** | list，每项 dict 且 `text` 为 str | **至少一条**，否则查不到（见 §4.1） |
| `where` | **是** | dict；`where.file` 为 str | `file` 可为空串，但那样输出的 `来源:` 是空的（§4.2） |
| `also_at` | 否 | list | 同名补充来源；`full` 档会显示 |
| `sections` | **是** | dict（**可为 `{}`**） | 见 §3 |
| `field_status` | **是** | dict，每个值必须是 str | 取值语义见 §4.3 |
| `status` | 否 | 字符串 | 缺省按 `active`；`"deprecated"` 会被渲染成"已弃用" |
| `prefix`、`tokens` | **不要写** | — | 加载时按函数名重算并**覆盖**你写的值 |

`returns` 的每个条目**必须同时有 `value` 和 `desc`**（两者都由契约校验）——`desc` 是渲染
直接取的键，缺了会被拒绝：`<名>.sections.returns.items.desc must be str`。

**扩展键**（本项目读，契约不校验）：

| 键 | 作用 |
|---|---|
| `origin` | 写 `"custom"` 才会被认作二次开发函数：digest 出 `（自定义）`、头部出 `load()` 前提行。其它值（或不写）= 按普通函数渲染 |
| `origin_meta` | `{ "custom": { "load": "load(\"src/my/func.il\")" } }`——那行前提行的文本来源 |
| `lint` | 自由内容，本项目不读（留给产生器记自己的检查结果） |
| 其它未知键 | **一律放行**，不校验 |

## 3. `sections` 的节形状

只有官方文档里出现的节才写（**稀疏**：没有的节直接不写）。逐节：

| 节 | 形状 |
|---|---|
| `description`（或 `definition`） | `{"text": "…"}` |
| `arguments` | `{"root": {"title": str\|null, "items": [条目]}, "lists": [子列表], "text": "…"}` |
| `returns` | `{"items": [{"value": str, "desc": str}], "text": "…"}` |
| `reference` | `{"text": "…", "links": [{"text": str, "href": str}]}` |
| 其余 12 个规范节名 | `{"text": "…"}`，含表格时另给 `"items": [{"name": str, "desc": str}]` |

**条目**（`arguments` 的 root.items 与 lists[].items）：`{"name": str, "desc": str, "values": null | [{"value": str, "desc": str}]}`。

**子列表**：`{"title": str, "list_type": str\|null, "parent": null | {"arg": str, "type": str, "match": str}, "items": [条目]}`。`list_type` 是标题括号里的 token（如 `l_subrectArgs`），`parent` 指向根参数、匹配用 `list_type` 与根参数的类型 token（`match` 写 `"exact"` 或 `"case_insensitive"`），命中 0/多处写 `null`。

规范节名共 16 个：`description`、`arguments`、`returns`、`example`、`reference`、`related_functions`、`prerequisites`、`additional_information`、`interactive_function`、`associated_options`、`option_descriptions`、`purpose`、`format`、`definition`、`overview`、`errors`。

> 多行文本用真实的 `\n`（JSON 里写 `\n`）。渲染层会按换行组织续行缩进。

## 4. 契约**不查**、但决定"有没有用"的（必读）

### 4.1 `decl` 至少一条带 `text` 的声明

`decl: []` **能通过契约**，但 `query_function` 会把它当成不存在——查它返回"未找到函数"，
而它的名字又能出现在搜索结果里（两处行为不一致）。直接调渲染则会 `IndexError`。

### 4.2 `where.file` 必须是真值

契约只查类型（`""` 也算 str，实测通过），但渲染的 `来源:` 行直接取它。
空值 = 输出里没有来源，消费方无法回查原文。

### 4.3 `field_status` 的取值语义

契约只要求"值是字符串"。渲染只认三个**异常**值并翻译成中文措辞：
`text_fallback`（原文保留但未结构化）、`unparsed`（未能可靠提取）、`shared_declaration`
（声明取自共享主题）。其余值（如 `present`、`not_documented`、`documented_none`）**不显示**。
所以：**不要把"官网上没有"写成 `unparsed`**，那会被当成解析失败报给消费方。

### 4.4 `sections` 与 `field_status` 要自洽

写了某节却把它标成 `not_documented`（或反之）不会被拦，但输出会自相矛盾。

## 5. 最小可运行样例

```json
{
  "schema_version": 3,
  "corpus": {"product": "my-toolchain", "scope": "project-internal"},
  "functions": {
    "myProjectFunc": {
      "type": "function",
      "decl": [{"text": "myProjectFunc( t_in t_mode ) => t_out / nil", "shared_from": null}],
      "where": {"file": "src/my/func.il", "topic": "myProjectFunc",
                "marker_text": "myProjectFunc", "anchor": "myProjectFunc"},
      "also_at": [],
      "sections": {
        "description": {"text": "把 t_in 按 t_mode 处理。"},
        "arguments": {
          "root": {"title": null, "items": [
            {"name": "t_in", "desc": "输入。", "values": null},
            {"name": "t_mode", "desc": "模式。", "values": [
              {"value": "'fast", "desc": "跳过校验。"},
              {"value": "'safe", "desc": "默认。"}]}]},
          "lists": [],
          "text": "t_in\n输入。\nt_mode\n模式。"
        },
        "returns": {"items": [{"value": "t_out", "desc": "处理结果。"}], "text": "t_out\n处理结果。"}
      },
      "field_status": {"description": "present", "arguments": "present", "returns": "present",
                       "decl": "present", "example": "not_documented"},
      "status": "active",
      "origin": "custom",
      "origin_meta": {"custom": {"load": "load(\"src/my/func.il\")"}}
    }
  }
}
```

## 6. 自查

```bash
# ① 被收进来了吗（来源清单 + 顺序 + 索引路径）
VIRTUOSO_CUSTOM_INDEX=<你的信封或它所在目录> \
  uv run python -B -m knowledge_virtuoso.functions --sources

# ② 查一个函数，看五档渲染
VIRTUOSO_CUSTOM_INDEX=<…> uv run python -B -m knowledge_virtuoso.functions myProjectFunc
```

要**不经过本项目**、直接把两道闸门跑一遍（可复制进你的构建流程）：

```python
from knowledge_virtuoso.functions.core import envelope, contract

entries = envelope._read_index_entries("你的信封.json", require_envelope=True, label="我的来源")
contract._rebuild_runtime_indexes(entries)     # 不合格会抛 ValueError，消息点到字段路径
print("通过:", len(entries), "条")
```

失败时 `ValueError` 的消息形如 `myProjectFunc.sections.arguments.root.items.desc must be str`——
**直接指到出问题的那条记录与那一层字段**。

## 7. 版本与兼容

- 信封版本是 `schema_version: 3`。本项目**格式**变了会自动判不兼容并触发重建；
  你的产出对不上时加载期就会报 `索引格式版本不兼容`。
- `prefix`/`tokens` 是派生字段：写不写都会被覆盖，**不要**把它们当成可以控制的输入。
- 本项目**只读消费**你的索引，**不产出、不修改**它。

## 8. 本项目不保证的事

- 契约的"通过"只保证**查询与渲染不会因为类型不对而失败**（§4.4 那处除外），
  不保证你的记录忠实于任何原文——那是你自己的解析责任。
- 未知键放行意味着写错键名**不会被拦**（只会静默地不起作用）。
- 同名冲突：你的记录与官方（或更早的来源）同名时会**覆盖**它，并在 stderr 打遮蔽警告。
