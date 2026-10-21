"""存储位置：优先用项目里的 data/，不可写就退到系统临时目录。

有些环境（容器、只读挂载、受限沙箱）不允许在项目目录里建文件。
这里做一次探测，避免整个服务起不来。
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def writable_dir(preferred: Path, name: str = "travel-agent") -> Path:
    for candidate in (preferred, Path(tempfile.gettempdir()) / name):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            return candidate
        except Exception:
            continue
    return Path(tempfile.gettempdir()) / name
