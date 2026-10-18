"""Agent 3: 博弈协商（核心创新）"""
from crewai import Agent, Task
from config.llm_config import get_llm


def create_negotiator_agent() -> Agent:
    return Agent(
        role="博弈协商官",
        goal="""
基于Shapley值博弈机制，为多位旅行者生成公平行程。

协商协议（3阶段）：
【阶段1-提案】每个用户代理提出最理想方案
【阶段2-让步】按Shapley值确定让步优先级，must_have不可让步
【阶段3-补偿】对让步最多者设计补偿，确保无人连续两天被牺牲

效用函数：6维情感评分，按用户画像动态调权
终止条件：公平性指数 ≥ 0.75 或达到5轮
公平性指数 = 1 - 满意度标准差/均值
""",
        backstory="""你是一位博弈论专家兼谈判调解员。
你深知"公平"不是"平均"，而是让每个人觉得核心需求被尊重。
你用Shapley值量化话语权，用帕累托最优确保没有更好的替代方案。""",
        llm=get_llm(temperature=0.5),  # ← 统一模型
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )


def create_negotiation_task(
        user_profiles: str,
        destination_info: str,
        shapley_values: str = "",
        days: int = 3
) -> Task:
    agent = create_negotiator_agent()

    shapley_section = ""
    if shapley_values:
        shapley_section = f"\n【Shapley值（已计算）】\n{shapley_values}\n"

    return Task(
        description=f"""
【用户画像】
{user_profiles}

【目的地可选活动】
{destination_info}

【天数】{days}天
{shapley_section}

【博弈流程】
Step 1: 偏好冲突检测（硬性/软性）
Step 2: Shapley值分析，确定让步优先级
Step 3: 多轮协商（提案→让步→补偿）
Step 4: 生成行程（标注每个活动满足谁）
Step 5: 公平性报告

【输出】
{{
    "conflict_analysis": [...],
    "shapley_values": {{...}},
    "negotiation_rounds": [...],
    "itinerary": [
        {{
            "day": 1,
            "theme": "...",
            "items": [
                {{
                    "time_slot": "09:00-11:00",
                    "activity": "...",
                    "location": "...",
                    "target_users": ["user_1"],
                    "emotion_score": {{...}},
                    "weather_dependency": "outdoor"
                }}
            ]
        }}
    ],
    "satisfaction_scores": {{...}},
    "fairness_index": 0.82,
    "compensation_plans": [...],
    "pareto_optimal": true
}}
""",
        agent=agent,
        expected_output="NegotiationResult JSON",
    )