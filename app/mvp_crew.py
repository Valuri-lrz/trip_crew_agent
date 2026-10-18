"""
TravelCrew B 档 MVP：CrewAI 三 Agent 串行，结构化输出 + 工具。

范围（刻意保持小）：
- 文本输入，1-5 位旅行者
- Profiler -> Researcher -> Planner
- 搜索/天气工具（未配置 key 时工具会返回提示，不编造）
- 输出 Itinerary（Pydantic），UI 不再解析字符串 JSON

不包含：图片、多用户独立画像、Shapley/公平性/补偿、记忆、RAG、多轮协商。
这些等 MVP 使用感验证后再加。
"""
import json
import os
import pathlib
import sys
import time
from typing import Any, Literal

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Keep CrewAI from asking "share execution trace?" in a web app and from
# spending an extra LLM call on trace summarization.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_DISABLE_VERSION_CHECK", "true")

try:
    from app.crewai_bootstrap import bootstrap_crewai
except ImportError:  # `streamlit run app/streamlit_mvp.py` puts app/ on sys.path
    from crewai_bootstrap import bootstrap_crewai

# CrewAI 1.15 may block on ~/.config probing; redirect it before importing crewai.
bootstrap_crewai()

from crewai import Agent, Crew, LLM, Process, Task  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.settings import api_key, base_url, model_name, provider_prefix  # noqa: E402
from app.multimodal import VisualProfile, analyze_images  # noqa: E402
from tools.search_tool import search_destination  # noqa: E402
from tools.weather_tool import get_weather_forecast  # noqa: E402


def get_llm(temperature: float = 0.3) -> LLM:
    """DeepSeek 走 OpenAI 兼容接口。

    `openai/` 前缀强制 LiteLLM 走 OpenAI-compatible 路径；如果当前 LiteLLM
    不认，把 LLM_PROVIDER_PREFIX 改成 `deepseek` 再试。
    """
    return LLM(
        model=f"{provider_prefix()}/{model_name()}",
        base_url=base_url(),
        api_key=api_key(),
        temperature=temperature,
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        # DeepSeek supports json_object, not OpenAI's json_schema structured
        # output.  Keep the LLM in JSON mode and validate with Pydantic below.
        response_format={"type": "json_object"},
        # Disable thinking mode: reasoning tokens made 3-agent runs take 40-100s
        # and sometimes truncated the JSON.  Quality is sufficient for MVP.
        additional_params={"extra_body": {"thinking": {"type": "disabled"}}},
    )


# ---------------------------------------------------------------------------
# 契约
# ---------------------------------------------------------------------------
class UserProfile(BaseModel):
    user_id: str
    summary: str = Field(description="一句话概括这位旅行者")
    interests: list[str] = Field(default_factory=list)
    pace: Literal["轻松", "适中", "紧凑"] = "适中"
    must_haves: list[str] = Field(default_factory=list, description="不可让步的需求，最多3个")
    avoid: list[str] = Field(default_factory=list, description="明确不想要的东西")
    visual_summary: str = Field(default="", description="图片线索总结；无图片则为空")
    visual_mood: str = Field(default="", description="图片情绪基调；无图片则为空")


class ProfileBundle(BaseModel):
    profiles: list[UserProfile]


class Activity(BaseModel):
    name: str
    location: str = ""
    time_slot: str = Field(description="例如 09:00-11:30")
    why: str = Field(description="为什么适合这些人")
    tags: list[str] = Field(default_factory=list)
    weather_dependency: Literal["indoor", "outdoor", "any"] = "any"
    estimated_cost: str = ""
    source: str = Field(default="", description="来源/参考；不确定就写需核实")


class ResearchBundle(BaseModel):
    destination: str
    weather_summary: str = ""
    activities: list[Activity]
    sources: list[str] = Field(default_factory=list)


class DayPlan(BaseModel):
    day: int
    theme: str = ""
    items: list[Activity] = Field(default_factory=list)


class Itinerary(BaseModel):
    destination: str
    summary: str = ""
    days: list[DayPlan] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Guardrails：结构之外的最小语义校验
# ---------------------------------------------------------------------------
def _json_text(raw: str) -> str:
    """Strip Markdown fences / prose around the JSON object."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def _schema_hint(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


def _as_pydantic(output, schema):
    if output.pydantic is not None:
        return output.pydantic
    if output.json_dict is not None:
        try:
            return schema.model_validate(output.json_dict)
        except Exception:
            return None
    try:
        return schema.model_validate(json.loads(_json_text(output.raw)))
    except Exception:
        return None


def validate_profiles(expected_count: int):
    def _validate(output) -> tuple[bool, Any]:
        bundle = _as_pydantic(output, ProfileBundle)
        if bundle is None:
            return False, "输出不是合法的 ProfileBundle JSON，请修复格式。"
        if len(bundle.profiles) != expected_count:
            return False, f"需要恰好 {expected_count} 份画像，当前是 {len(bundle.profiles)} 份。"
        ids = [p.user_id for p in bundle.profiles]
        if len(ids) != len(set(ids)):
            return False, "user_id 重复，请为每位旅行者保留唯一 ID。"
        return True, output

    return _validate


def validate_research(min_activities: int = 6):
    def _validate(output) -> tuple[bool, Any]:
        bundle = _as_pydantic(output, ResearchBundle)
        if bundle is None:
            return False, "输出不是合法的 ResearchBundle JSON，请修复格式。"
        if len(bundle.activities) < min_activities:
            return False, f"至少需要 {min_activities} 个候选活动，当前只有 {len(bundle.activities)} 个。"
        return True, output

    return _validate


def validate_itinerary(expected_days: int):
    def _validate(output) -> tuple[bool, Any]:
        itinerary = _as_pydantic(output, Itinerary)
        if itinerary is None:
            return False, "输出不是合法的 Itinerary JSON，请修复格式。"
        if len(itinerary.days) != expected_days:
            return False, f"需要 {expected_days} 天行程，当前是 {len(itinerary.days)} 天。"
        if any(len(day.items) == 0 for day in itinerary.days):
            return False, "每天至少要有 1 个活动，不能出现空白天。"
        return True, output

    return _validate


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
def build_agents() -> tuple[Agent, Agent, Agent]:
    profiler = Agent(
        role="旅行偏好分析师",
        goal="把多位旅行者的自然语言描述整理成结构化画像，识别冲突和硬性需求。",
        backstory="你擅长从模糊描述中提取真实需求，也知道哪些话只是客气。",
        llm=get_llm(0.2),
        allow_delegation=False,
        max_iter=3,
        verbose=False,
    )
    researcher = Agent(
        role="目的地研究员",
        goal="为这个目的地找到具体、可执行、匹配画像的活动，并标注天气依赖。",
        backstory="你在当地生活过，知道哪些地方值得去、哪些是游客陷阱。",
        llm=get_llm(0.5),
        tools=[search_destination, get_weather_forecast],
        allow_delegation=False,
        max_iter=8,
        verbose=False,
    )
    planner = Agent(
        role="行程规划师",
        goal="把候选活动排成每天可执行的行程，考虑交通、体力、用餐和天气。",
        backstory="你做过很多次自由行，知道行程不能排太满。",
        llm=get_llm(0.3),
        allow_delegation=False,
        max_iter=4,
        verbose=False,
    )
    return profiler, researcher, planner


# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------
def build_crew(
    destination: str,
    days: int,
    users: list[dict],
    visuals: dict[str, VisualProfile] | None = None,
) -> Crew:
    profiler, researcher, planner = build_agents()
    visuals = visuals or {}

    user_lines: list[str] = []
    for user in users:
        visual = visuals.get(user["user_id"])
        line = f"- {user['user_id']}: {user['text']}"
        if visual and visual.confidence > 0:
            needs = "、".join(visual.implicit_needs) or "无"
            line += (
                f"\n  图片线索：{visual.summary}；情绪：{visual.mood or '未知'}；"
                f"隐性需求：{needs}（置信度 {visual.confidence:.0%}）"
            )
        user_lines.append(line)
    user_text = "\n".join(user_lines)
    profile_task = Task(
        name="profile",
        description=f"""分析以下 {len(users)} 位旅行者：
{user_text}

要求：
1. 每人一个 UserProfile；保留 user_id，不要合并。
2. must_haves 最多 3 个，只放真正不可让步的。
3. 标出 avoid（明确不想要的）。
4. 如果多人偏好冲突，在 summary 里点明。
5. 如果输入里有“图片线索”，把它融入 summary/interests；visual_summary 填图片线索摘要，
   visual_mood 填情绪基调；没有图片就留空。
只输出 ProfileBundle JSON。

JSON Schema：
{_schema_hint(ProfileBundle)}""",
        expected_output="ProfileBundle JSON",
        agent=profiler,
        guardrail=validate_profiles(len(users)),
        guardrail_max_retries=2,
    )

    research_task = Task(
        name="research",
        description=f"""目的地：{destination}；天数：{days}。
基于 context 中的 ProfileBundle，给出候选活动。

要求：
1. 至少 8 个候选，覆盖室内/室外、不同时段、不同体力强度。
2. 每个活动写清楚 location、time_slot、why、weather_dependency。
3. 优先使用搜索/天气工具的结果；工具不可用时，明确写“基于模型知识，需核实”。
4. 不要编造不存在的店/景点；不确定就写“需核实”。
只输出 ResearchBundle JSON。

JSON Schema：
{_schema_hint(ResearchBundle)}""",
        expected_output="ResearchBundle JSON",
        agent=researcher,
        context=[profile_task],
        guardrail=validate_research(6),
        guardrail_max_retries=2,
    )

    plan_task = Task(
        name="plan",
        description=f"""把 context 中的候选活动排成 {days} 天行程。

要求：
1. 每天 2-3 个主要活动，留出交通和吃饭时间。
2. 不要连续两天高强度。
3. 每位旅行者每天至少有一个匹配其兴趣的活动；做不到就在 tips 里说明。
4. 天气依赖的活动给备选。
5. 只使用候选活动中出现过的地点，不要新增。
只输出 Itinerary JSON。

JSON Schema：
{_schema_hint(Itinerary)}""",
        expected_output="Itinerary JSON",
        agent=planner,
        context=[profile_task, research_task],
        guardrail=validate_itinerary(days),
        guardrail_max_retries=2,
    )

    return Crew(
        agents=[profiler, researcher, planner],
        tasks=[profile_task, research_task, plan_task],
        process=Process.sequential,
        verbose=os.getenv("CREW_VERBOSE", "0") == "1",
        memory=False,
        tracing=False,
        task_callback=_task_tracer,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
_TASK_TRACE: list[dict] = []
_TASK_LAST = [0.0]


def _task_tracer(output) -> None:
    """记录每个 Task 的耗时，方便判断慢在画像/研究/规划哪一段。"""
    now = time.time()
    elapsed = round(now - (_TASK_LAST[0] or now), 1)
    _TASK_LAST[0] = now
    _TASK_TRACE.append({
        "agent": getattr(output, "agent", ""),
        "task": getattr(output, "name", "") or "",
        "seconds": elapsed,
        "raw_preview": (getattr(output, "raw", "") or "")[:200],
    })


def run_trip(destination: str, days: int, users: list[dict]) -> dict:
    if not users:
        raise ValueError("至少需要一位旅行者")
    if days < 1 or days > 7:
        raise ValueError("天数必须在 1-7 之间")

    _TASK_TRACE.clear()
    _TASK_LAST[0] = time.time()
    start = time.time()

    # Multimodal pre-analysis: one vision call per user, shared with all images.
    visuals: dict[str, VisualProfile] = {}
    visual_errors: dict[str, str] = {}
    for user in users:
        paths = user.get("image_paths") or []
        if not paths:
            continue
        try:
            visuals[user["user_id"]] = analyze_images(paths, user.get("text", ""))
        except Exception as exc:
            visual_errors[user["user_id"]] = f"{type(exc).__name__}: {exc}"
            visuals[user["user_id"]] = VisualProfile(
                summary="图片分析失败，已降级为文本偏好",
                confidence=0.0,
            )

    crew = build_crew(destination, days, users, visuals)
    out = crew.kickoff()

    raw = out.tasks_output[-1].raw if out.tasks_output else out.raw
    try:
        itinerary = Itinerary.model_validate(json.loads(_json_text(raw)))
    except Exception as exc:
        raise RuntimeError(
            f"Planner 没有返回合法 Itinerary：{exc}。原始输出：\n{raw}"
        ) from exc

    profiles: list[UserProfile] = []
    if out.tasks_output:
        try:
            bundle = ProfileBundle.model_validate(
                json.loads(_json_text(out.tasks_output[0].raw))
            )
            for profile in bundle.profiles:
                visual = visuals.get(profile.user_id)
                if visual is not None:
                    profile = profile.model_copy(update={
                        "visual_summary": visual.summary,
                        "visual_mood": visual.mood,
                    })
                profiles.append(profile)
        except Exception:
            # The plan is still usable; the UI will hide the profile cards.
            profiles = []

    elapsed = round(time.time() - start, 1)
    return {
        "itinerary": itinerary.model_dump(),
        "profiles": [p.model_dump() for p in profiles],
        "visuals": {uid: v.model_dump() for uid, v in visuals.items()},
        "visual_errors": visual_errors,
        "images": {u["user_id"]: list(u.get("image_paths") or []) for u in users},
        "elapsed_seconds": elapsed,
        "participants": len(users),
        "model": model_name(),
        "trace": list(_TASK_TRACE),
    }


if __name__ == "__main__":
    result = run_trip(
        destination="大理",
        days=3,
        users=[
            {"user_id": "u1", "text": "想安静看海，不想太商业化，最好能骑车。"},
            {"user_id": "u2", "text": "想吃当地小吃，晚上想逛夜市，但不想太累。"},
        ],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
