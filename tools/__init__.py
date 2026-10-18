"""Tool registry with lazy imports.

Only the tools used by the B 档 MVP live here:
- search_destination
- get_weather_forecast

Keeping imports lazy means tests and app startup do not pull in optional
dependencies until a tool is actually requested.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY: dict[str, str] = {
    "search_destination": ".search_tool",
    "get_weather_forecast": ".weather_tool",
}

__all__ = list(_LAZY)


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
