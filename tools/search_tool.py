"""目的地搜索工具"""
import os
from dotenv import load_dotenv
from crewai.tools import tool

load_dotenv()


@tool("search_destination")
def search_destination(query: str) -> str:
    """
    搜索目的地相关信息（景点、美食、活动、交通等）。
    输入：搜索关键词，如 "大理小众徒步路线"
    输出：搜索结果摘要
    """
    tavily_key = os.getenv("TAVILY_API_KEY")

    if tavily_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True
            )

            results = []
            if response.get("answer"):
                results.append(f"【摘要】{response['answer']}")

            for r in response.get("results", []):
                results.append(f"【{r['title']}】{r['content'][:200]}")

            return "\n\n".join(results) if results else "未找到相关结果"

        except Exception as e:
            return f"搜索出错: {str(e)}"
    else:
        # 无Tavily时返回提示
        return (
            f"[搜索工具未配置] 查询: {query}\n"
            "请设置 TAVILY_API_KEY 环境变量以启用搜索功能。\n"
            "当前将基于模型自身知识回答。"
        )