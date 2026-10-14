# cdfdb 解析器的 HTML 片段（夹具）

由 `tests/capture_attrs_html.py` 从本机官方 doc 切出。片段就是**本库解析器
会看成一段**的那块 HTML：db 是节短语到下一个 `<h3`（形状节取标题最后一次
出现），techdb 是一个 `techID~>` 的 `<h3>` 段，cdfdb 是一个对象类的字段区。

同名 `.json` 是期望值，**取自线上索引**（按片段的归属过滤），不是解析器跑出来
的：db 按 `objTypes` 含本节运行时类型、techdb/cdfdb 按 `classes[cid].attributes`。
`names` 是归属成员、**全部要比**；`unique` 是只属于本片段的名字——只有它们的
字段可比（另一个节也列过的名字，线上字段取自首发节，见 `expectation()`）。

| 片段 | 体积 | 源文件（doc 根下） | 归属 |
|---|---|---|---|
| `class_cdfDataId.html` | 6.9 KB | `skartistref/chap21.html` | cdfDataId |
| `class_cdfParamId.html` | 17.8 KB | `skartistref/chap21.html` | cdfParamId |
| **合计** | **24.7 KB** | | |

**这是 Cadence 官方文档的原文摘录**：进公开仓库前请确认符合其许可；要缩小
暴露就减少片段（改 `capture_attrs_html.py` 的 `TARGETS` 后重跑，测试会报出
缺了哪些夹具）。

