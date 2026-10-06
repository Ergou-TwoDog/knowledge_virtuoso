"""索引目录定位与原子写。仅依赖标准库。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_APP_DIRNAME = "knowledge-virtuoso"


def data_dir() -> Path:
    """索引根目录：VIRTUOSO_DATA_DIR 优先（须为绝对路径），否则平台默认。

    环境变量在进程内首次调用时读取；修改后需重启进程。
    """
    override = os.environ.get("VIRTUOSO_DATA_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else home / "AppData" / "Local"
        return root / _APP_DIRNAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / _APP_DIRNAME
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else home / ".local" / "share"
    return root / _APP_DIRNAME


def index_path(lib: str) -> Path:
    """返回 <data_dir>/<lib>/index.json。"""
    return data_dir() / lib / "index.json"


def atomic_write_json(path: str | Path, obj) -> None:
    """原子写 JSON，输出格式与属性库既有索引一致（indent=2, ensure_ascii=False）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temp = Path(stream.name)
            stream.write(json.dumps(obj, indent=2, ensure_ascii=False))
        temp.replace(path)
    finally:
        if temp and temp.exists():
            temp.unlink()
