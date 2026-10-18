"""Agent 4: 动态调度"""
from crewai import Agent, Task
from config.llm_config import get_llm
from tools.weather_tool import get_weather_forecast


def create_scheduler_agent() -> Agent:
    return Agent(
        role="动态行程调度员",
        goal="""
为行程设计备选方案和动态调整策略。

触发→调整：
- 天气突变 → 室外换室内，保持情感基调
- 用户疲劳 → 降低强度，插入休息
- 景点关闭 → 启用备选
- 时间不够 → 砍优先级最低的

原则：
1. 保持情感曲线节奏
2. 不破坏博弈均衡
3. 调整幅度最小化
""",
        backstory="""你是一位带过500+团的旅行领队。
你深知计划赶不上变化，所以永远有Plan B。""",
        llm=get_llm(temperature=0.5),  # ← 统一模型
        tools=[get_weather_forecast],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )


def create_scheduling_task(itinerary: str, destination: str, days: int = 3) -> Task:
    agent = create_scheduler_agent()

    return Task(
        description=f"""
【已生成行程】
{itinerary}

【目的地】{destination}
【天数】{days}天

【任务】
1. 查询天气
2. 为室外活动设计室内备选
3. 为高体力活动设计低体力备选
4. 设计疲劳应对方案
5. 设计时间不够方案

【输出】
{{
    "weather_alert": "...",
    "backup_plans": [
        {{
            "original_activity": "...",
            "trigger": "下雨/疲劳/关闭",
            "backup_activity": "...",
            "emotion_score_preserved": true
        }}
    ],
    "fatigue_protocol": "...",
    "time_overflow_protocol": "..."
}}
""",
        agent=agent,
        expected_output="动态调度方案 JSON",
    )