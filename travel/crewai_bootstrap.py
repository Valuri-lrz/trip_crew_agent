"""CrewAI 导入前的路径接管（Windows 上必做）。

问题：crewai 导入时会在模块级构造 tracing 监听器 → PlusAPI → Settings →
``get_writable_config_path()``，它会用 ``tempfile.mkstemp`` 去"试写"候选目录。
如果候选目录落在受限的工作区里（沙箱、只读挂载、组策略限制），这一步会**卡死**
（实测 3 分钟以上，且不抛错）。

对策：在 import crewai **之前**，把默认配置路径指到一个确定可写的临时目录，
让第一次试写立刻成功、直接返回。

用法（必须在 import crewai 之前）：
    from travel.crewai_bootstrap import bootstrap_crewai
    bootstrap_crewai()
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def bootstrap_crewai() -> Path:
    data_dir = Path(tempfile.gettempdir()) / "travel-agent" / "crewai"
    data_dir.mkdir(parents=True, exist_ok=True)

    import crewai_core.paths as paths
    import crewai_core.settings as settings

    # get_writable_config_path() 在调用时读这个模块全局，所以直接覆盖有效。
    settings.DEFAULT_CONFIG_PATH = data_dir / "settings.json"
    paths.db_storage_path = lambda: str(data_dir)  # type: ignore[assignment]
    return data_dir
