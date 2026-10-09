"""Virtuoso 官方知识库 MCP 服务。"""

from importlib.metadata import PackageNotFoundError, version

try:
    # 以已安装包的元数据为唯一来源，避免与 pyproject 版本各写一份而漂移。
    __version__ = version("knowledge-virtuoso")
except PackageNotFoundError:  # 未安装、直接从源码运行
    __version__ = "0+unknown"
