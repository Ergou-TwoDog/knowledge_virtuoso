#!/usr/bin/env python3
"""属性库的**装配**：把一份声明装成一个能用的库。

库根的 `index.py` 只填**声明**——库名、载荷版本、来源文档、① 解析、② 归一、本库的选择器
别名与跨对象口径、本库自己的构建期校验：

    LIB = Library(name="db", version=5, doc_parts=("skdfref", "attrib.html"),
                  parse=parse, decorate=decorate, aliases=_ALIASES, cross=query.POOL)

`Library` 出的是装配这一摊：`payload`（打版本与 `lib` + 校验）、`extract_all`/`build`/`load`
（索引存取）、`main`（库里自带的小 CLI；`cli.py` 那条路走的是 `build`，与这里无关）。
**查询入口不在这里**——它在 `core/query.py` 的 `Query`（库包里 `Query(LIB)` 现绑一份），
"装配归装配、查询归查询"。

**为什么这段能收在这儿**：四库的"② 之后打版本与 `lib` → 校验 → 读索引/坏了重建 → CLI"
逐字相同（判据仍是"换个库要不要重写"——不用）。**库名、版本、来源文档、别名、口径、校验**
是各库自己的事实，所以由调用方传进来，而不是在这里猜。

载荷顶层键固定为 `objects.PAYLOAD_KEYS`（`version` / `lib` / `objects`）：`lib` 是类型区分
字段，装载时与库名核对（`store.Store._mismatch`），构建时由 `objects.validate_payload` 查。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_virtuoso._paths import atomic_write_json, index_path
from knowledge_virtuoso.database.core import objects as objects_mod
from knowledge_virtuoso.database.core import query, store

__all__ = ["Library"]


class Library:
    """一个属性库：声明进来，入口出去。"""

    def __init__(self, *, name: str, version: int, doc_parts, parse, decorate,
                 aliases: dict | None = None, cross: str = query.POOL,
                 check=None, summary=None, label: str | None = None) -> None:
        self.name = name                    # 库名 = 索引目录名 = 载荷里的 `lib`
        self.version = version              # 载荷格式版本（改了推法或键集就要抬）
        self.aliases = aliases or {}        # 本库的选择器词汇（原文没写过、使用者在用的那些）
        self.cross = cross                  # 跨对象口径（`query.POOL` / `query.EACH`）
        self.parse = parse                  # ① 如实
        self.decorate = decorate            # ② 归一
        self._check = check                 # 本库自己的构建期校验（可选）
        self._summary = summary             # CLI 里多打几行（可选）
        self.store = store.Store(
            index_path=index_path(name), label=label or f"{name}_attr", lib=name,
            doc_parts=doc_parts, parse=parse, payload=self.payload, version=version)

    # ── 载荷：② 之后打版本与 `lib`，再校验 ──
    def validate(self, payload: dict) -> None:
        """**构建期校验**：共用的那套（顶层键集、`lib` 与库名一致、两层键集）加本库自己的几条。

        测试里手写的载荷也走它（`tests/common.py` 的 `run_attr_search_cases`）——手写载荷
        本来就可能缺键或写错归属，让它在这一道过一遍才算数。
        """
        objects_mod.validate_payload(payload, self.name)
        if self._check is not None:
            self._check(payload["objects"])

    def payload(self, raw: dict) -> dict:
        """`raw`（① 的产出）→ 要落盘的载荷。

        **顺序不能反**：先拼出最终形状（打上版本与 `lib`），再校验它——校验必须覆盖最终形状。
        """
        payload = {"version": self.version, "lib": self.name,
                   "objects": self.decorate(raw)["objects"]}
        self.validate(payload)
        return payload

    # ── ①② 的整体入口 + 索引存取 ──
    def extract_all(self, doc_path: str) -> dict:
        """① + ② 的整体入口（**不打版本、不校验**）——测试与调试用，能吃半份文档。"""
        return self.decorate(self.parse(doc_path))

    def build(self, doc_path: str | None = None) -> dict:
        """从来源 HTML 构建载荷；不给路径时取 `VIRTUOSO_DOC_DIR` 下的默认文档。"""
        return self.store.build(doc_path)

    def load(self) -> dict:
        """索引载荷（进程内缓存；缺失、损坏、版本或 `lib` 不符时从官方 doc 重建）。"""
        return self.store.load()

    # ── 查询入口不在这：`core/query.py` 的 `Query` 按这份声明现绑一份（`Query(LIB)`）──

    # ── 库里自带的小 CLI（`cli.py` 不走这里，它直接用 `build`）──
    def main(self, argv=None) -> None:
        parser = argparse.ArgumentParser(description=f"从官方 doc 重建 {self.name} 索引")
        parser.add_argument("--doc", default=None,
                            help="来源 HTML（默认取 VIRTUOSO_DOC_DIR 下的来源文档）")
        parser.add_argument("--output", default=str(self.store.index_path),
                            help="输出 JSON 路径")
        args = parser.parse_args(argv)

        payload = self.build(args.doc)
        atomic_write_json(Path(args.output), payload)

        objects = payload["objects"]
        print(f"\n已导出到 {args.output}")
        print(f"  lib/版本:  {payload['lib']} v{payload['version']}")
        print(f"  对象:      {len(objects)} 个")
        print(f"  记录:      {sum(len(o['attrs']) for o in objects.values())} 条")
        for line in (self._summary(objects) if self._summary else ()):
            print(f"  {line}")
