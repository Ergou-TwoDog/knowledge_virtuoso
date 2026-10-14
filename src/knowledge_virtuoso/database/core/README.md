# database/core：属性库的共用件与四库对照

这一层放**跨库共用**的东西，以及"四个属性库各是什么形状"的一张对照表。

> **加一个属性库 = 在 `database/` 下加一棵树**。库自己的三样东西写在
> `database/<库>/__init__.py`（接口：`NAME`/`SELECTOR`/`DOC` + `build`/`search`/`render`），
> `registry.py` 扫 `database/` **自动发现**；上层（`server.py` 的工具、`cli.py` 的子命令）
> 一行不用改。`knowledge-virtuoso-build libs` 可核对发现结果。

---

## 一、这层有什么

| 文件 | 管什么 |
|---|---|
| `registry.py` | **发现**属性库（`pkgutil` 扫 `database/`），校验接口与选择器名，供上层生成工具与子命令 |
| `objects.py` | **对象模型**：构建期校验、选择器解析、继承合并、"名字 → 声明它的对象" |
| `render.py` | **表格渲染**：四份渲染器同构（标题 + 定宽列 + 可选截断 + 整列占位就藏列），所以收成一份；各库只**声明自己的列** |
| `store.py` | **索引存取**：读 JSON / 坏了从官方 doc 重建 / 进程内缓存与锁；`query_rows` 做关键词过滤与排序 |

`objects.py` 与 `store.py` 合起来覆盖了"拿到索引之后的所有公共步骤"；各库剩下的只有
**解析器 + 别名表 + 行工厂 + 一份列声明**。

## 二、四库载荷对照

db / techdb / cdfdb **共用同一套容器**（`objects.py` 的模型）：

```
{version, objects: {<id>: {id, title, parent, attrs: [...]}}}
```

| | db | techdb | cdfdb | **dd** |
|---|---|---|---|---|
| 顶层键 | `objects` | `objects` | `objects` | **`objectTypes` + `attributes` + `relations`** |
| 一条属性记录属于 | 一个对象 | 一个对象 | 一个对象 | **N 个对象**（原文转置：一条只说一遍，后面列适用对象） |
| **继承** | ✅ `parent` 有 69 条边、7 个根 | ❌ `parent` 恒 `null`（全是根） | ❌ 同左 | ❌ 无此概念 |
| 记录的字段 | `name · modify · type · desc` | `name · type · desc` | `name · rw · type · desc · source` | `name · kind · cardinality · objectTypes` |
| 对象级附加字段 | `section · runtime` | `desc` | `title`(`g_cdfDataId`) · `section` | —— |
| 原文给的 | 四列（含 Modify） | 两列（名字\|说明） | 散文里说可编辑性 | **只有名字 + 适用对象**（无类型、无说明） |
| 选择器 | `objType` | `className` | `className` | `object` |
| 渲染列 | `name rw type desc` | `name [rw] type 所属类` | `name rw type desc` | `name kind [card] 适用对象` |

三条要点：

1. **"有没有继承"不用旗子标。** 没有继承的库 `parent` 全是 `null`，`merged()` 走一遍就
   返回自身——退化情形本身就是如实的表示（"该库全是根节点"）。校验同理：没有父就没有环可查。
2. **属性记录不统一，因为它们不是一回事**：只有设计库的原文有 Modify 列（所以 db 存的
   是原文的 `modify`）；CDF 的可编辑性写在散文里（所以 cdfdb 存的是推出来的 `rw`）、
   还有两条属性来自 `cdfCreateParam` 的实参（所以有 `source` 标出处）；技术库两列都没有。
   强行统一成一套字段，就得用空值去表示"这库没有这个概念"——那正是"缺失状态"要分开写的地方。
3. **dd 站在容器之外**，因为它的原文是**转置**的：一条记录只说一遍、后面列出适用对象。
   塞进"每个对象一张表"的容器要**物化 3.4×**（22 条记录 → 74 条副本），而那恰恰是原文的
   反面。所以它自带一套载荷（`objectTypes`/`attributes`/`relations`），只共用 `store.py`
   与 `registry.py`。**这个边界是"每个对象一张表"这一族，不是"所有属性库"。**

**渲染器也是共用的**（`core/render.py`）：四份渲染器的差别**全在列上**——列宽、描述截断
（db 60 / cdfdb 55）、整列都是占位值就藏列（techdb 的 `rw="?"`、dd 的空基数）、列表值拼接。
没有一处是结构差异，所以按同一条判据（换个库要不要重写）该抽；**解析器那边答案相反**，
四份文档记法各不相同，换个库得重写，所以三库的 `core/catalog.py` 仍然各写各的。

## 三、跨对象（不给选择器）时的口径

| | 行为 | 为什么 |
|---|---|---|
| db | 按名去重（先到先占），`definedIn` 记归属 | 它的表**没有"所属对象"列**，分对象分行只会印出一堆看着重复、又分不出归属的行 |
| techdb / cdfdb | 每个对象各一行 | 它们的表**有"所属类"列**，分行才读得出归属 |

**口径跟着各自的表走**，不是随手定的。

## 四、版本

索引 JSON 顶层带 `version`（各库自己的 `_PAYLOAD_VERSION`）：**版本不符即当作损坏**——
有 `VIRTUOSO_DOC_DIR` 就自动重建，没有就明确报"索引不可用"。db/techdb/cdfdb 自并入本层的
对象模型起为 **v2**（techdb/cdfdb 的 `classes` 键也随之改名 `objects`），dd 为 **v2**
（`objects` → `objectTypes`，"全集"与"某条记录的适用子集"同名太绕）。
