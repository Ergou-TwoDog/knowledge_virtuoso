# database/dd/core：数据管理对象的属性与关系

本模块把"数据管理对象"（`lib` / `cell` / `view` / `libFile` / `cellFile` / `viewFile`）
的属性与关系从官方 doc 解析出来、落成索引，并按**对象**回答"它有哪些属性、哪些关系"。
索引存取在 `database/core/store.py`，行形状与文本在 `database/dd/render.py`。

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
| 适用对象 | 每个对象**各自一格**（不是拼成一串文本）；空格子 = 不适用 |
| 关系的基数 | 关系表第二格，原文只有 `1:1` 与 `1:n` |
| **对象全集与顺序** | 表 19-1 的适用列**没有列名**，顺序拿不到；只能从关系表里 `lib` / `parent` 那两行取——它们把 6 个对象依次列全 |
| **没有继承** | 全节没有 `include` 之类的指针（这一章里 `inherit` 一词全指 view type 使能，与属性无关） |

## 二、本库**拿不到**类型，也**拿不到**说明

属性表只有"名字 | 适用对象"两列。类型图例虽然在 HTML 里（那张 9 行表），但正文说的是
"types … are shown **in these figures**"——**逐条字母只出现在图里，而本节 `<img>` 为 0**。所以本库的行里**没有 `type`、也没有 `desc`**，渲染出来只有
`name / kind / 基数 / 适用对象`。

**这不是解析漏了**，这一点写进了工具 docstring 与渲染的首行提示，免得调用方以为丢了数据。

## 三、载荷为什么**照原文存**，而不是逐对象存

db / techdb / cdfdb 都是"每个对象一张表"，而且同名属性在不同对象里可以是不同的东西
（techdb 实测 24 个名字跨类、类型各不相同），所以那三库必须**逐对象**存，否则会丢。

本库**一条记录只说一遍**，同一个名字对所有适用对象是同一回事（键叫 `objectTypes` 而不是 `objects`——统一后 `objects` 在另三库是"对象 id → 记录"的字典，同名不同义是个坑）：

```json
{"version": 2,
 "objectTypes": ["lib", "cell", "view", "libFile", "cellFile", "viewFile"],
 "attributes":  {"group": {"name": "group", "kind": "attr",
                           "objectTypes": ["libFile", "cellFile", "viewFile"]}},
 "relations":   {"cells": {"name": "cells", "kind": "relation", "cardinality": "1:n",
                           "objectTypes": ["lib"]}}}
```

逐对象复制反而**制造**重复——这里没有可丢的信息，照原文存最忠实；按对象取是**查询时**的事。
所以"载荷形状与另三库不同"是**推断出来的差异**，不是随手定的。

## 四、解析与装配规则

1. **按表头签名挑表**，不按位置：同节有四张表，位置会随排版变，表头不会。
2. **对象全集取"枚举得最全的关系行"**，并要求这些行彼此一致；不一致就构建失败——
   表 19-1 的列名缺失，顺序只能从这儿来，取错了整张表的适用对象都会错位。
3. **构建期校验**（`_validated`）：对象全集非空；每条记录的适用对象都在全集里；
   关系的基数形如 `1:1`/`1:n`；属性名与关系名不撞车；名字形状合法。
   本节靠"表头签名 + 最全的那行"解析，排版一变就可能悄悄错位——宁可不构建。
4. **载荷照原文存**（见第三节），不预判归属。
5. **选择器**：对象名精确匹配 → 忽略大小写。认不出返回空（区别于"认识但筛完没结果"）。

## 五、测试

`tests/knowledge_virtuoso/database/dd/`——检索用 `core/fixtures/search.json`（手写载荷与
期望），解析用 `core/fixtures/html/dd_section.{html,json}`（官方 doc 的整节，出处见该目录
README），另有一组自造 HTML 钉住第三节那几处脆技巧（表头签名挑表、空格子、基数、对象全集）。
