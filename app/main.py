"""
TravelCrew - 多智能体博弈驱动的个性化旅游规划系统
统一使用 DeepSeek 多模态模型
"""
import os
import json
import time
from typing import List, Optional
from dotenv import load_dotenv
from crewai import Crew, Process

from agents.multimodal_profiler import create_profiler_agent, create_profiling_task
from agents.researcher import create_researcher_agent, create_research_task
from agents.game_negotiator import create_negotiator_agent, create_negotiation_task
from agents.dynamic_scheduler import create_scheduler_agent, create_scheduling_task

load_dotenv()


def run_travel_crew(
        user_inputs: List[dict],
        destination: str,
        days: int = 3,
        image_paths: Optional[List[str]] = None,
) -> dict:
    """
    运行完整旅游规划流水线

    所有Agent统一使用 DeepSeek 多模态模型
    """
    start_time = time.time()

    print("\n" + "🚀" * 20)
    print(f"TravelCrew 启动 | 模型: {os.getenv('MODEL_NAME')}")
    print("🚀" * 20)

    # ===== 阶段1：多模态画像 =====
    print("\n📸 阶段1: 多模态隐性偏好推理...")
    combined_text = "\n\n".join([
        f"【{u.get('user_id', f'user_{i + 1}')}】: {u['text']}"
        for i, u in enumerate(user_inputs)
    ])

    profiler_agent = create_profiler_agent()
    profiling_task = create_profiling_task(combined_text, image_paths)
    profiling_task.agent = profiler_agent

    # ===== 阶段2：目的地研究 =====
    print("🔍 阶段2: 目的地深度研究...")
    researcher_agent = create_researcher_agent()
    research_task = create_research_task(destination, "{阶段1输出}", days)
    research_task.agent = researcher_agent

    # ===== 阶段3：博弈协商 =====
    print("⚖️ 阶段3: Shapley值博弈协商...")
    negotiator_agent = create_negotiator_agent()
    negotiation_task = create_negotiation_task(
        "{阶段1输出}", "{阶段2输出}", days=days
    )
    negotiation_task.agent = negotiator_agent

    # ===== 阶段4：动态调度 =====
    print("🔄 阶段4: 动态调度...")
    scheduler_agent = create_scheduler_agent()
    scheduling_task = create_scheduling_task("{阶段3输出}", destination, days)
    scheduling_task.agent = scheduler_agent

    # ===== 组装 & 执行 =====
    crew = Crew(
        agents=[profiler_agent, researcher_agent, negotiator_agent, scheduler_agent],
        tasks=[profiling_task, research_task, negotiation_task, scheduling_task],
        process=Process.sequential,
        verbose=True,
    )

    print("\n⏳ 执行中...")
    result = crew.kickoff()

    elapsed = time.time() - start_time
    print(f"\n✅ 完成！耗时: {elapsed:.1f}s")

    return {
        "result": str(result),
        "elapsed_time": round(elapsed, 1),
        "destination": destination,
        "days": days,
        "participants": len(user_inputs),
        "model": os.getenv("MODEL_NAME"),
    }


# ===== 演示入口 =====

def demo_single():
    """单人演示"""
    return run_travel_crew(
        user_inputs=[{
            "user_id": "user_1",
            "text": "我想去大理，喜欢安静的地方，不想太商业化，最好能看到洱海"
        }],
        destination="大理",
        days=3,
    )


def demo_multi():
    """多人博弈演示"""
    return run_travel_crew(
        user_inputs=[
            {"user_id": "user_A", "text": "我想去博物馆，安静的那种，不喜欢人多"},
            {"user_id": "user_B", "text": "我想吃遍当地美食，夜市大排档都行"},
            {"user_id": "user_C", "text": "我想拍照发朋友圈，要好看的地方"},
        ],
        destination="成都",
        days=3,
    )


def demo_with_images():
    """带图片的多模态演示"""
    return run_travel_crew(
        user_inputs=[
            {"user_id": "user_1", "text": "想去个放松的地方"},
            {"user_id": "user_2", "text": "我想冒险，刺激一点的"},
        ],
        destination="云南",
        days=4,
        image_paths=[
            "test_images/grassland.jpg",  # 空旷草原
            "test_images/night_market.jpg",  # 夜市
        ],
    )


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "single"

    if mode == "multi":
        result = demo_multi()
    elif mode == "images":
        result = demo_with_images()
    else:
        result = demo_single()

    print("\n" + "=" * 50)
    print(result["result"])