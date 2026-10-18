"""目的地搜索工具。

优先用 Tavily SDK；SDK 未安装时回退到 Tavily REST API（只需要 requests），
这样 B 档 MVP 不必为了一个搜索工具安装额外依赖。
"""
from __future__ import annotations

import os

import requests
from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

TAVILY_URL = "https://api.tavily.com/search"


def _tavily_search(query: str, api_key: str, max_results: int = 5) -> dict:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": True,
    }

    # Prefer the SDK when available; fall back to REST (requests-only).
    try:
        from tavily import TavilyClient  # type: ignore

        return TavilyClient(api_key=api_key).search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
        )
    except ImportError:
        response = requests.post(TAVILY_URL, json=payload, timeout=20)
        response.raise_for_status()
        return response.json()


@tool("search_destination")
def search_destination(query: str) -> str:
    """
    搜索目的地相关信息（景点、美食、活动、交通等）。
    输入：搜索关键词，如 "大理小众徒步路线"
    输出：搜索结果摘要（含来源 URL）
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return (
            f"[搜索不可用] 未配置 TAVILY_API_KEY。查询：{query}\n"
            "请基于模型知识回答，并明确标注“需核实”。"
        )

    try:
        data = _tavily_search(query, api_key)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (401, 403):
            return (
                "[搜索不可用] TAVILY_API_KEY 无效或已过期。\n"
                "请基于模型知识回答，并标注“需核实”。"
            )
        return f"[搜索失败] {type(exc).__name__}: {exc}\n请基于模型知识回答，并标注“需核实”。"
    except Exception as exc:
        return f"[搜索失败] {type(exc).__name__}: {exc}\n请基于模型知识回答，并标注“需核实”。"

    parts: list[str] = []
    if data.get("answer"):
        parts.append(f"【摘要】{data['answer']}")

    for item in data.get("results", [])[:5]:
        title = item.get("title", "").strip()
        content = (item.get("content") or "").strip().replace("\n", " ")[:240]
        url = item.get("url", "")
        parts.append(f"【{title}】{content}\n来源：{url}")

    return "\n\n".join(parts) if parts else f"[无结果] 查询：{query}"
