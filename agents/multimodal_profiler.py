"""Agent 1: 多模态隐性偏好推理"""
from crewai import Agent, Task
from config.llm_config import get_llm
from tools.image_analysis import analyze_reference_image, analyze_multiple_images


def create_profiler_agent() -> Agent:
    return Agent(
        role="多模态隐性偏好推理师",
        goal="""
从用户的文本描述和参考图片中，推理出深层隐性偏好。
核心能力不是"识别图片内容"，而是"推理吸引力背后的心理需求"。

图片分析框架（5维度）：
1. 空间感：开阔→自由需求 / 封闭→安全感需求
2. 人物关系：独处→内向充电 / 群体→社交需求
3. 色调温度：暖色→治愈 / 冷色→冷静思考
4. 场景秩序：精致→控制感 / 粗犷→释放感
5. 时间暗示：黄昏→感性 / 正午→活力 / 深夜→内省

文本分析框架：
- 形容词选择 → 情绪状态
- 否定表达 → 隐性排斥
- 比较表达 → 参照系
- 模糊表达 → 决策疲劳程度
""",
        backstory="""你是一位视觉心理学家兼消费行为研究者。
你相信人们被某张图片吸引，不是因为图片本身，
而是因为图片映射了他们内心缺失的东西。""",
        llm=get_llm(temperature=0.3),  # ← 统一模型
        tools=[analyze_reference_image, analyze_multiple_images],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )


def create_profiling_task(user_text: str, image_paths: list = None) -> Task:
    agent = create_profiler_agent()

    image_section = ""
    if image_paths:
        image_section = f"""
【用户上传图片】共{len(image_paths)}张：
{chr(10).join(f'- {p}' for p in image_paths)}
请使用 analyze_reference_image 或 analyze_multiple_images 工具分析。
"""

    return Task(
        description=f"""
【用户文本输入】
{user_text}
{image_section}

【任务】
1. 提取显式偏好（明确说出的），标注权重和是否must_have
2. 推理隐性偏好（没说但暗示的）
3. 判断情感基调/审美风格/社交偏好/决策疲劳
4. 交叉验证图片和文本是否矛盾

【输出】严格JSON：
{{
    "user_id": "user_1",
    "explicit_preferences": [
        {{"content": "...", "category": "...", "weight": 0.8, "is_must_have": false}}
    ],
    "implicit_preferences": [
        {{"content": "...", "confidence": 0.85, "reasoning_chain": "...", "source_modality": "image/text", "source_detail": "..."}}
    ],
    "emotional_tone": "治愈型",
    "aesthetic_style": "极简",
    "social_preference": "小群体",
    "energy_level": "中",
    "decision_fatigue": "高"
}}
""",
        agent=agent,
        expected_output="UserProfile JSON",
    )