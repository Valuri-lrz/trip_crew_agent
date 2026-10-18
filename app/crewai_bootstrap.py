"""CrewAI path bootstrap for Windows / sandboxed environments.

CrewAI 1.15 probes ``~/.config/crewai`` and ``%LOCALAPPDATA%`` for a writable
settings/DB path during import.  On some Windows setups that probe blocks on
``tempfile.mkstemp`` (observed as a multi-minute `import crewai` hang).

Call ``bootstrap_crewai()`` **before** importing ``crewai``.  It redirects the
settings and SQLite storage paths into the project's ``.data/crewai`` folder.
"""
from __future__ import annotations

from pathlib import Path


def bootstrap_crewai() -> Path:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / ".data" / "crewai"
    data_dir.mkdir(parents=True, exist_ok=True)

    import crewai_core.paths as paths
    import crewai_core.settings as settings

    # get_writable_config_path() reads this module global at call time.
    settings.DEFAULT_CONFIG_PATH = data_dir / "settings.json"
    paths.db_storage_path = lambda: str(data_dir)  # type: ignore[assignment]
    return data_dir
