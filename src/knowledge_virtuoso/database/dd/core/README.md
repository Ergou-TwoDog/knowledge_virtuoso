# database/dd/core：数据管理对象的属性与关系

本模块把"数据管理对象"（`lib` / `cell` / `view` / `libFile` / `cellFile` / `viewFile`）
的属性与关系从官方 doc 解析出来、落成索引，并按**对象**回答"它有哪些属性、哪些关系"。
**按三层切，各占一个文件**（与另三个属性库同一张图）：

| 文件 | 层 | 管什么 |
|---|---|---|
| `parse.py` | ① 如实 | 这一节 h2 小节里有**哪几张表**、每张表有哪些格子。**不解释** |
| `decorate.py` | ② 归一 | 按**表头签名**挑出属性表与关系表；对象全集取"枚举得最全的关系行"；再摊平 |
| `../index.py` | ③ 声明 | **`LIB = Library(...)` 一行**：库名、载荷版本、来源文档、①② 两层、别名表（本库没有：对象名就是选择器）、跨对象口径（按名收一遍）、本库自己的构建期校验（`_check`）与 CLI 统计。装配由 `core/assembly.py` 出、查询入口由 `core/query.py` 的 `Query` 按它现绑 |

**查询机制不在这一层**：四库共用 `database/core/query.py`（选择器 → 记录池 → 行）。
索引存取在 `database/core/store.py`；渲染声明（列与提示语）在库接口
`database/dd/__init__.py` 的 `RenderSpec`，渲染机制在 `database/core/render.py`。

唯一来源：`$VIRTUOSO_DOC_DIR/skdfref/chap3.html`
（*Virtuoso Design Environment SKILL Reference* IC6.1.8，第 19 章
*Design Management Functions* 的 **"Attributes of Data Management Objects"** 一节）。

---

## 一、原文是怎么记的

这一节的记法与另外三个库**都不一样**——它是**转置**的：

```
Attribute Names | Object Types Attribute is Valid For
group           | libFile | cellFile | viewFile          ← 适用对象各占一格
name            | lib | cell | view | libFile | cellFile | viewFile
```

再加一张关系表：

```
Relation names | Relationship | Object Types Attributes is Valid For
cells          | 1:n          | lib
parent         | 1:1          | lib | cell | view | libFile | cellFile | viewFile
```

| 事实 | 认法 |
|---|---|
| 小节边界 | `<h2>Attributes of Data Management Objects</h2>` 到下一个 `<h2>`；**这一节里没有 h3/h4** |
| 同节还有两张表 | 运算符图例（`(~>)` / `(~>?)` / `(~>??)`）与类型图例（`b`/`d`/`f`/`g`/`l`/`n`/`s`/`t`/`x`）。按**表头签名**挑表即可避掉：属性表首格是 `Attribute Names`、关系表首格是 `Relation names` |
| 适用对象 | 每个对象**各自一格**（不是拼成一串文本）；空格子 = 不适用。6 个子列**位置固定**（`lib`\|`cell`\|`view`\|`libFile`\|`cellFile`\|`viewFile`，表头用一个 `colspan="6"` 的格子盖住），但解析只取**非空格子**，所以不依赖位置 |
| 关系的基数 | 关系表第二格，原文只有 `1:1` 与 `1:n` |
| **对象全集与顺序** | 表 19-1 的适用列**没有列名**，顺序拿不到；只能从关系表里 `lib` / `parent` 那两行取——它们把 6 个对象依次列全 |
| **没有继承** | 全节没有 `include` 之类的指针（这一章里 `inherit` 一词全指 view type 使能，与属性无关） |

## 二、本库**拿不到**类型，也**拿不到**说明

属性表只有"名字 | 适用对象"两列——**逐条属性没有类型、也没有说明**。

同节确实有一张类型图例（9 行，`b`=a DDPI object … `x`=an integer），正文也写着
"types … are shown **in these figures**"。但**这套 doc 里没有那样的图**（逐处查过）：

| 查法 | 结果 |
|---|---|
| dd 节里的 `<img>` | **0 张** |
| 本章（第 19 章）的图 | 只有 Figure 19-1——库的组织结构图，在**前一节**，画的是 lib/cell/view 与 UNIX 文件的对应，**没有属性名、也没有类型字母**；本章另一个"Figure 19-2"实为一张触发器名表 |
| 印刷版 `skdfref/skdfref.pdf` 正文 **1728 / 1729** 页（承载 Table 19-1、19-2 的正是这两页） | content stream 里**绘图指令 `Do` 为 0 条**，全是文本；前一页 1727 也是 0 条 |

所以那句图例是**孤立的样板文字**（"these figures" 没有指代对象），逐条属性的类型在原文里
**无处可取**——**不是"有图、但图没进 HTML"**。本库的行里因此没有 `type`、也没有 `desc`，
渲染出来只有 `name / kind / 基数 / 适用对象`。

**这不是解析漏了**，这一点写进了工具 docstring 与渲染的首行提示，免得调用方以为丢了数据。

## 三、载荷**摊成和另三库一样的容器**（物化）

这一节记的是一个**改过的决定**，连同当时的取舍。

原文是转置的（一条记录只说一遍、后面列适用对象），本库最初就**照原文存**：
`{objectTypes, attributes, relations}`，键叫 `objectTypes` 而不是 `objects`。那样最忠实，
且没有可丢的信息——同一个名字对所有适用对象确实是同一回事（不像 techdb，24 个名字跨类、
类型各不相同，不逐对象存就会丢）。

**后来改成物化了**（v3），因为"忠实"的代价落在了上层：一个库的载荷形状与另外三个不同，
联合查询、渲染的对象头、`validate_objects` 的校验都得为它开特例。现在：

```json
{"version": 5, "lib": "dd",
 "objects": {
   "lib": {"id": "lib", "title": null, "runtime": null, "section": null,
           "desc": null, "parent": null,
           "attrs": [{"name": "name", "kind": "attr", "cardinality": null,
                      "objectTypes": ["lib", "cell", "view", "libFile", "cellFile", "viewFile"]},
                     {"name": "cells", "kind": "relation", "cardinality": "1:n",
                      "objectTypes": ["lib"]}]},
   "cellFile": {…}, …}}
```

记录按 `database/core/objects.py` 的 `ATTR_KEYS` 写全（九键）：**本库只填得起四样**
（`name`/`kind`/`cardinality`/`objectTypes`），其余五键（`type`/`rw`/`desc`/`modify`/`source`）
恒 `null`——那是**原文没给**，不是解析漏了（见第二节）。

* **代价是副本**：22 条记录摊成 6 个对象共 **74 条**（3.36×）。索引几 KB，值得。
* **`objectTypes` 每条都留着**——它是原文的原话（"这条适用于哪几个对象"），留着才谈得上
  "索引只存事实"；行里那列「适用对象」也才有东西可印。
* **`objectTypes` 里的名字必须在对象全集里**，这条校验在 ② 做：摊平之后 ③ 只看得到挂上去
  的那些，一条"只挂在全集之外"的记录会连影子都没有——不能静默漏。
* 原文那个转置的记法**没有丢**：`core/decorate.py` 里先照原文读一遍（`records`/`relations`），
  再摊平；那两张表的形状也写在本文件第一节与 `parse.py` 里。

## 四、解析与装配规则

1. **按表头签名挑表**，不按位置：同节有四张表，位置会随排版变，表头不会。
2. **对象全集取"枚举得最全的关系行"**，并要求这些行彼此一致；不一致就构建失败——
   表 19-1 的列名缺失，顺序只能从这儿来，取错了整张表的适用对象都会错位。
3. **构建期校验分两处**：
   * 在 ②（`decorate`）：**适用对象必须在对象全集里**——摊平之前才看得全，宁可构建失败；
   * 在 ③（`LIB` 的构建期校验）：对象全集非空、每个对象至少一条记录、关系的基数形如 `1:1`/`1:n`、
     同一个名字不能既当属性又当关系（摊平后未必落在同一个对象里，所以按名收一遍）；
     键集与对象内重名交给共用件 `objects_mod.validate_objects`。
   本节靠"表头签名 + 最全的那行"解析，排版一变就可能悄悄错位——宁可不构建。
4. **载荷摊成七键容器**（见第三节），`objectTypes` 原样留着。
5. **选择器**：对象名精确匹配 → 忽略大小写。认不出返回空（区别于"认识但筛完没结果"）。
6. **跨对象（不给选择器）按名去重**，先到先占——同一条记录挂在多个对象下，逐对象分行只会
   印出重复行，而「适用对象」那列本来就把归属说全了。口径与 db 一致。

## 五、测试

`tests/knowledge_virtuoso/database/dd/`——与这边的树**同名同层**：① 用
`core/fixtures/raw/`（自造片段，钉"有几张表、有哪些格子"）、② 用
`core/fixtures/html/dd_section.{html,json}`（官方 doc 的整节，出处见该目录 README；期望值是
**六个对象各自的记录名**）+ 自造 HTML 钉住表头签名挑表、空格子、基数、对象全集与物化、
以及"适用对象不在全集里要炸"；③ 用 `fixtures/search.json`（手写载荷与期望）。
