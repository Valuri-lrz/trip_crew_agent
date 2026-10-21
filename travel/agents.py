"""CrewAI 的三个智能体。

分工只有一句话：它们负责"读懂人"和"说人话"，不负责算。
  Profiler  文字 + 图片线索 → 每个人的三层画像
  Matcher   从候选里挑 3 个目的地，写推荐理由
  Planner   把排程器的结果翻译成行程 + 提一个真正的问题

每次 kickoff 只做一件事，因为对话要停下来等用户。
没有 key 时上层直接走规则，不会进到这里。
"""
from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

from travel.config import get_settings
from travel.schemas import DestinationCard, Itinerary, Profile

os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_DISABLE_VERSION_CHECK", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

# 必须在 import crewai 之前调用，否则 Windows 上会在 settings 试写时卡死。
from travel.crewai_bootstrap import bootstrap_crewai  # noqa: E402

bootstrap_crewai()


class ProfileBundle(BaseModel):
    profiles: list[Profile] = Field(default_factory=list)
    analysis: str = Field(default="", description="按五层读出来的结论，给用户看")
    city_hint: str = Field(default="", description="用户提到的具体地方，没提就是空")
    clarify: str = Field(default="", description="一个真正值得问的问题，没有就空")
    opening: str = Field(default="", description="对用户说的第一句话")


class CardBundle(BaseModel):
    cards: list[DestinationCard] = Field(default_factory=list)


class PlanOut(BaseModel):
    itinerary: Itinerary
    question: str = ""


class ItemText(BaseModel):
    """只回文字，不回结构——模型不用把整份行程复述一遍，省一半 token。"""

    poi_id: str
    why: str = ""
    highlight: str = ""
    tip: str = ""


class DayNote(BaseModel):
    day: int
    note: str = ""


class DayStory(BaseModel):
    day: int
    story: str = ""


class PlanPatch(BaseModel):
    analysis: str = ""
    stories: list[DayStory] = Field(default_factory=list)
    items: list[ItemText] = Field(default_factory=list)
    day_notes: list[DayNote] = Field(default_factory=list)
    question: str = ""


def _llm(temperature: float = 0.3, thinking: bool = False, max_tokens: int = 8000):
    from crewai import LLM

    s = get_settings()
    return LLM(
        model=f"openai/{s.model}",
        base_url=s.base_url,
        api_key=s.api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        additional_params={"extra_body": {"thinking": {"type": "enabled" if thinking else "disabled"}}},
    )


def _parse(output, model):
    """CrewAI 不同版本给的字段不一样，能拿的都试一遍。"""
    for attr in ("pydantic", "json_dict"):
        val = getattr(output, attr, None)
        if val is None:
            continue
        if isinstance(val, model):
            return val
        try:
            return model.model_validate(val)
        except Exception:
            pass
    raw = getattr(output, "raw", "") or ""
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return model.model_validate(json.loads(raw[start:end + 1]))
    except Exception:
        return None


# ------------------------------------------------------------------ Profiler
def run_profiler(texts: list[str], visuals: list[dict], people: int):
    """文字 + 图片 → 三层偏好。

    这一层是整个产品的脑子：谁说的、图里缺什么、哪两句话在打架。
    结论必须落成数字，理由必须能指回证据。
    """
    from crewai import Agent, Crew, Process, Task

    visual_lines = []
    for i, v in enumerate(visuals):
        if not v:
            visual_lines.append(f"- 第 {i + 1} 位：没有图片")
            continue
        visual_lines.append(
            f"- 第 {i + 1} 位：【{v.get('place_guess') or '未认出'}】"
            f"{v.get('summary', '')}\n"
            f"    场景 {v.get('scene', {})}\n"
            f"    标签 {v.get('tags', [])}｜证据 {v.get('evidence', [])}\n"
            f"    视觉侧初判：审美 {v.get('aesthetic', {})}｜情绪 {v.get('emotion', {})}｜"
            f"社交 {v.get('social', {})}｜置信 {v.get('confidence')}"
        )

    user_block = "\n".join(
        f"- 第 {i + 1} 位说的话：{t}\n  {visual_lines[i] if i < len(visual_lines) else ''}"
        for i, t in enumerate(texts)
    )
    schema = json.dumps(ProfileBundle.model_json_schema(), ensure_ascii=False)

    def check(output):
        bundle = _parse(output, ProfileBundle)
        if bundle is None:
            return False, "不是合法的 ProfileBundle JSON"
        if len(bundle.profiles) != people:
            return False, f"需要 {people} 份画像，现在是 {len(bundle.profiles)} 份"
        if len({p.user_id for p in bundle.profiles}) != people:
            return False, "user_id 必须互不相同"
        if any(len(p.tags) > 3 for p in bundle.profiles):
            return False, "tags 最多 3 个"
        return True, output

    profiler = Agent(
        role="多模态隐性偏好推理师",
        goal="分清每个人真正想要什么，把没说出口的部分推出来，并落成可计算的数字",
        backstory="你是视觉心理学出身，做消费行为研究。你知道人被一张图吸住，"
                  "往往是因为图里补了他现实里缺的东西。你也知道客人说'随便'是决策疲劳，"
                  "说'都行'是心里有雷区但不想讲。你从不把客套话当需求。",
        llm=_llm(0.25),
        allow_delegation=False,
        max_iter=3,
        verbose=False,
    )
    task = Task(
        description=f"""今天有 {people} 位旅行者。
注意：下面的文字可能是一个人说的，也可能一句话里混了几个人的诉求
（"她喜欢拍照，我怕人多"）。提到 {people} 个人就拆成 {people} 份画像，
不许合并成一份，也不许把两个人的诉求平均摊给所有人。
{user_block}

【一、先分清谁说的】
一句话里常混着两个人的诉求（"她喜欢拍照，我怕人多"）。
把每个诉求归到具体的人；归不掉的单列，不要平均分摊给所有人。
图片如果只代表其中一个人，说清楚是谁的。

【二、读图，五层】
1. 空间：开阔 → 想要自由；封闭 → 想要安全感
2. 人物：无人 → 内向充电；成群 → 社交需求
3. 色温：暖 → 治愈；冷 → 冷静思考
4. 秩序：精致 → 控制感；粗粝 → 释放感
5. 时间：黄昏 → 感性；正午 → 活力；夜里 → 内省
多张图之间也要看：是一个感觉，还是两种互相拉扯的？
互相拉扯就写进 conflicts，不要揉成"既安静又热闹"这种和稀泥的话。

【三、读文字信号】
- 形容词 → 他此刻的情绪状态
- 否定（"不想""受不了""别"）→ 隐性排斥，比正面要求更硬
- 比较（"上次""不如"）→ 他的参照系
- 模糊（"随便""都行""看你们"）→ 决策疲劳 → 给他的选项要少
- 身份线索（带娃 / 爸妈 / 情侣 / 一个人）→ 直接决定节奏和体力上限

【四、落成数字，并且能解释】
aesthetic 五维 -1~1，emotion 六维 0~1，social 三维。
任何超过 ±0.7 的极端值，必须在 evidence 里写出依据（哪句话、图里哪个细节）。
推不出来的维度就留 0/中位，不要为了完整而编。

【五、留一个澄清点】
如果某个判断置信度低于 0.6，写进 clarify，一句人话问出来。
没问题就留空——宁可不问，也不要问废话（"你想住哪"这种）。

输出要求：
- 每人一份 profile，user_id 用 u1/u2/...
- tags 最多 3 个，要具体（"雪后渔村"好过"安静"）
- summary 一句话，说清他想要的是一次什么样的旅行
- must_haves 只放真正不可让步的（不能爬山 / 必须能拍照 / 不吃辣）
- analysis：把你按五层读出来的结论说给用户听，该写多长写多长，不要为了短而漏掉判断
- opening：你先对用户说的那段话。口语，自然，长度随内容，别为了短而砍掉信息
- city_hint：用户明确提到的地名，没提留空

只输出 ProfileBundle JSON。

Schema:
{schema}""",
        expected_output="ProfileBundle",
        agent=profiler,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[profiler], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    return _parse(out.tasks_output[-1] if out.tasks_output else out, ProfileBundle)


# ------------------------------------------------------------------ Matcher
def run_matcher(  # noqa: D401  当前未接入：多一次调用换一句推荐理由，不划算（+5s）
    profiles: list[Profile], candidates: list[dict]) -> list[DestinationCard] | None:
    from crewai import Agent, Crew, Process, Task

    def check(output):
        bundle = _parse(output, CardBundle)
        if bundle is None:
            return False, "不是合法的 CardBundle JSON"
        if not 2 <= len(bundle.cards) <= 3:
            return False, "要挑 2~3 个"
        allowed = {c["id"] for c in candidates}
        if any(c.id not in allowed for c in bundle.cards):
            return False, "只能从给定候选里选，不许新增"
        return True, output

    matcher = Agent(
        role="目的地推荐官",
        goal="从候选里挑出最像这几个人想要的 3 个地方，每个用一句话说清为什么",
        backstory="你在旅行杂志做过十年编辑，一眼能看出一个地方适合什么样的人。"
                  "你从不推荐'因为有名'，只推荐'因为像你要的'。",
        llm=_llm(0.4),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    profile_text = json.dumps([p.model_dump() for p in profiles], ensure_ascii=False)
    cand_text = json.dumps(candidates, ensure_ascii=False)
    task = Task(
        description=f"""旅行者画像：
{profile_text}

候选目的地（只能从这里选）：
{cand_text}

挑 2~3 个，并为每个写一句推荐理由：
- 理由必须引用画像里的具体东西（"你说想要人少"），不要写"风景优美"
- 理由要说清"为什么是他，不是别人"
- id 必须来自候选列表
只输出 CardBundle JSON。""",
        expected_output="CardBundle",
        agent=matcher,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[matcher], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    bundle = _parse(out.tasks_output[-1] if out.tasks_output else out, CardBundle)
    return bundle.cards if bundle else None


# ------------------------------------------------------------------ Planner
def run_planner(draft: Itinerary, profiles: list[Profile]) -> tuple[Itinerary, str] | None:
    """写攻略。让它先把"取舍"想明白，再动笔——analysis 那一段就是被强制写出来的思考。"""
    from crewai import Agent, Crew, Process, Task

    allowed = {i.poi_id for d in draft.days for i in d.items}
    brief = [
        {"poi_id": i.poi_id, "name": i.name, "day": d.day, "slot": i.slot,
         "duration_min": i.duration_min, "cost": i.cost, "indoor": i.indoor}
        for d in draft.days for i in d.items
    ]
    who = [
        {"tags": p.tags, "summary": p.summary, "must_haves": p.must_haves,
         "avoid": p.avoid, "evidence": p.evidence[:2]}
        for p in profiles
    ]

    def check(output):
        patch = _parse(output, PlanPatch)
        if patch is None:
            return False, "不是合法的 PlanPatch JSON"
        ids = {i.poi_id for i in patch.items}
        if not ids <= allowed:
            return False, f"出现了清单里没有的 poi_id：{ids - allowed}"
        return True, output

    planner = Agent(
        role="本地向导",
        goal="把这趟行程写成能照着走的攻略：几点、哪个门、多少钱、哪里会踩坑",
        backstory="你在这个城市带过五年团。你带过人凌晨五点去等日出，也拦过人中午去排网红店。"
                  "你说话像朋友发微信，不像攻略网站。",
        llm=_llm(0.5, thinking=get_settings().think, max_tokens=8000),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    task = Task(
        description=f"""点位清单（顺序和点位都不许动）：
{json.dumps(brief, ensure_ascii=False)}

旅行者：
{json.dumps(who, ensure_ascii=False)}

动笔前先按这些常识过一遍：

【行程常识】
- 同一天别跨两个方向来回跑；一天最多一个片区
- 第 1 天刚到，排轻的；最费体力的放第 2 天；最后一天别排远的（除非晚上才走）
- 饭点要留出来，别把两个点卡在 12 点前后
- 热门点要么开门前到，要么闭门前一小时去；中午去等于排队
- 看 duration_min 和 indoor 判断体力：费体力的别排在下午后半段，也别连排两天
- 有室内备选的，写进 tip

【小众优先】
- 清单里如果有本地人才去的地方，highlight 里说明"为什么值得绕过去"
- 不要因为名气大就把它写得更详细，按体验写，不按知名度写

【什么算具体】
- 能照着做：几点、哪个门、哪道菜、什么角度、多少钱
- 判断标准：**这句话换成别的城市也成立，就是废话**
- 反面词：风景优美、值得一去、适合拍照、很有氛围、不容错过

【必须诚实】
- 价格、营业时间、是否要预约：拿不准写「未核实」
- 不许编店名，不许编票价

输出顺序：
1. analysis：先写这段，不超过 80 字。说清这群人的核心矛盾是什么（比如一个想拍照一个怕人多），
   以及这三天你打算怎么取舍（哪天按谁的来、哪里留白）。这是给你自己看的，用户也会看到。
2. items：每个 poi_id 三条
   - why：为什么适合这些人，要引用他们具体说过的东西
   - highlight：具体到能照着做
   - tip：具体代价，含未核实标注
3. stories：每天一段，像写给人看的一天，写透——
   几点出门、路上大概多久、到那儿先干什么、中午在哪吃、下午怎么安排、累了有什么退路。
   要写成连续的一段话，不要分点，不要"首先其次"。
4. day_notes：每天一句节奏提示（这一天是松还是赶，为什么）
4. question：最多一个会真正改变行程的问题

该详细就详细：宁可写长，也不要把具体信息压成一句空话。可以分段。

只输出这个形状的 JSON：
{{"analysis":"...",
 "items":[{{"poi_id":"...","why":"...","highlight":"...","tip":"..."}}],
 "stories":[{{"day":1,"story":"..."}}],
 "day_notes":[{{"day":1,"note":"..."}}],"question":""}}""",
        expected_output="PlanPatch",
        agent=planner,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[planner], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    patch = _parse(out.tasks_output[-1] if out.tasks_output else out, PlanPatch)
    if not patch:
        return None

    by_id = {i.poi_id: i for i in patch.items}
    notes = {n.day: n.note for n in patch.day_notes if n.note}
    stories = {x.day: x.story for x in patch.stories if x.story}
    days = []
    for d in draft.days:
        items = []
        for it in d.items:
            t = by_id.get(it.poi_id)
            if t:
                it = it.model_copy(update={
                    "why": t.why or it.why,
                    "highlight": t.highlight or it.highlight,
                    "tip": t.tip or it.tip,
                })
            items.append(it)
        days.append(d.model_copy(update={"items": items, "note": notes.get(d.day, d.note),
                                          "story": stories.get(d.day, d.story)}))
    new = draft.model_copy(update={"days": days})
    if patch.analysis:
        new.notes.append("取舍：" + patch.analysis)
    return new, patch.question


# ------------------------------------------------------------------ 现场写点位
class DraftPOI(BaseModel):
    name: str
    category: str = "景点"
    tags: list[str] = Field(default_factory=list)
    duration_min: int = 120
    cost: float = 0.0
    indoor: bool = False
    best_slot: str = "any"
    crowd: float = 0.5
    taste: dict = Field(default_factory=dict)


class POIDraft(BaseModel):
    pois: list[DraftPOI] = Field(default_factory=list)


def run_draft_pois(city: str, profiles: list[Profile], days: int) -> list | None:
    """库里没有这个地方时，让模型按记忆写一批候选点位。

    这些东西没有核实过，所以回来以后统一标 source="model"，
    界面上会提示"出发前自己核一遍"。
    """
    from crewai import Agent, Crew, Process, Task

    from travel.schemas import POI, Taste

    def check(output):
        draft = _parse(output, POIDraft)
        if draft is None:
            return False, "不是合法的 POIDraft JSON"
        if not 6 <= len(draft.pois) <= 15:
            return False, f"需要 6~15 个点位，现在 {len(draft.pois)} 个"
        if any(not p.name.strip() for p in draft.pois):
            return False, "有点位没名字"
        return True, output

    guide = Agent(
        role="当地向导",
        goal="为这个城市列出真正存在、能排进行程的点位",
        backstory="你在世界各地带过团，知道哪些地方值得占掉半天、哪些半小时就够。"
                  "你只写自己确实知道的地方，不确定的会说明。",
        llm=_llm(0.5),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    task = Task(
        description=f"""目的地：{city}，玩 {days} 天。

旅行者：
{json.dumps([{"tags": p.tags, "must_haves": p.must_haves, "avoid": p.avoid} for p in profiles], ensure_ascii=False)}

列出 8~12 个点位，覆盖不同时段和室内外。
**其中至少 2 个是本地人才去、游客一般不知道的**；不要全是攻略榜上的热门。
每个点位给：
name（真实名字，别编）、category（景点/餐饮/体验/自然/街区/展馆）、
tags（3 个具体标签）、duration_min（分钟）、cost（人均，人民币）、indoor、
best_slot（morning/afternoon/evening/any）、crowd（0~1 人多不多）、
taste（quiet_lively/nature_urban/minimal_ornate/warm_cool/classic_trendy，各 -1~1）。

只输出 JSON：
{{"pois":[{{"name":"...","category":"...","tags":["",""],"duration_min":120,
 "cost":0,"indoor":false,"best_slot":"morning","crowd":0.5,
 "taste":{{"quiet_lively":0,"nature_urban":0,"minimal_ornate":0,"warm_cool":0,"classic_trendy":0}}}}]}}""",
        expected_output="POIDraft",
        agent=guide,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[guide], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    draft = _parse(out.tasks_output[-1] if out.tasks_output else out, POIDraft)
    if not draft:
        return None

    base = Taste()
    out_pois = []
    for i, d in enumerate(draft.pois, 1):
        taste = base.model_copy(update={
            k: max(-1.0, min(1.0, float(v)))
            for k, v in (d.taste or {}).items() if k in base.model_dump()
        })
        out_pois.append(POI(
            id=f"gen-{i}", dest_id="custom", name=d.name, category=d.category,
            tags=list(d.tags)[:3], taste=taste,
            crowd=max(0.0, min(1.0, d.crowd)),
            duration_min=max(20, min(360, d.duration_min)),
            cost=max(0.0, d.cost), indoor=bool(d.indoor),
            best_slot=d.best_slot if d.best_slot in ("morning", "afternoon", "evening", "any") else "any",
            source="model",
        ))
    return out_pois


# ------------------------------------------------------------------ 说话
def run_voice(situation: str, draft: str) -> str | None:
    """把模板话术改写成一句人话。失败返回 None，上层用原文。

    这一层存在的唯一理由：之前所有回话都是我写死的字符串，
    用户其实是在跟模板聊天，模型只在旁边写括号里的解释。
    """
    from crewai import Agent, Crew, Process, Task

    writer = Agent(
        role="旅行搭子",
        goal="用一两句自然的话把现在的情况说清楚",
        backstory="你是个话不多但靠谱的旅行搭子。你不说'为您服务'，也不列 1234，"
                  "就像朋友发微信。",
        llm=_llm(0.7),
        allow_delegation=False,
        max_iter=1,
        verbose=False,
    )
    task = Task(
        description=f"""现在的情况：{situation}

本来准备回这段话（草稿）：
{draft}

把它改写成你会说的话：
- 口语，自然，长度随内容，需要时可以分段
- 不要说"作为 AI"这类话
- 不许新增事实：天气、价格、评分、营业时间一律不许自己加
- 用户马上能看到的东西（列表、卡片）别再念一遍
只输出这句话本身。""",
        expected_output="一句话",
        agent=writer,
    )
    crew = Crew(agents=[writer], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    text = (out.raw or "").strip()
    text = text.strip('"').strip()
    return text if 4 <= len(text) <= 120 else None


# ------------------------------------------------------------------ 攻略抽取
def run_guide_summary(name: str, city: str, snippets: list[dict]):
    """从搜索摘要里抽事实。规矩：指得来来源、抹平不了矛盾就报矛盾、不许补内容。"""
    from crewai import Agent, Crew, Process, Task

    from travel.guides import GuideBundle

    numbered = "\n".join(
        f"[{i}] {x.get('title','')}｜{x.get('content','')[:220]}"
        for i, x in enumerate(snippets)
    )

    def check(output):
        from travel.agents import _parse

        bundle = _parse(output, GuideBundle)
        if bundle is None:
            return False, "不是合法的 GuideBundle JSON"
        if any(not f.field for f in bundle.facts):
            return False, "有事实没写字段名"
        if any(f.source >= len(snippets) for f in bundle.facts):
            return False, "source 指向了不存在的摘要"
        return True, output

    reader = Agent(
        role="攻略核对员",
        goal="从多篇攻略里抽出可核对的事实，并指出它们互相矛盾的地方",
        backstory="你做过旅游编辑，专门负责校对。你知道网上的攻略一半是抄的，"
                  "年份不同价格就差一截。你从不替作者圆场。",
        llm=_llm(0.2),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    task = Task(
        description=f"""地点：{city} {name}

下面是搜到的 {len(snippets)} 条摘要，每条前面是编号：
{numbered}

抽事实，规矩只有三条：
1. 每条事实必须标 source（第几条），指不出来源的就别写
2. 同一件事出现不同说法（比如门票 20 和 50），**不要挑一个**，
   两条都写进 facts，并把差异写进 conflicts，格式："门票：20（[0]）vs 50（[2]）"
3. 摘要里没提到的，一个字都不许补。你不知道就说不知道

字段只用这六种：门票 / 开放时间 / 怎么去 / 排队 / 适合谁 / 注意

只输出 JSON：
{{"facts":[{{"field":"门票","value":"...","source":0,"year_hint":""}}],
 "conflicts":["..."]}}""",
        expected_output="GuideBundle",
        agent=reader,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[reader], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    from travel.agents import _parse

    return _parse(out.tasks_output[-1] if out.tasks_output else out, GuideBundle)


# ------------------------------------------------------------------ 推荐目的地
class DestItem(BaseModel):
    name: str
    region: str = ""
    days: int = 3
    reason: str = ""


class DestBundle(BaseModel):
    cards: list[DestItem] = Field(default_factory=list)


def suggest_destinations(profiles: list[Profile], hint: str = "") -> list:
    """没有库了，三个候选也由模型给。可以是中国，也可以是国外。"""
    from crewai import Agent, Crew, Process, Task

    from travel.schemas import DestinationCard

    def check(output):
        b = _parse(output, DestBundle)
        if b is None:
            return False, "不是合法的 DestBundle JSON"
        if not 2 <= len(b.cards) <= 4:
            return False, f"要 2~4 个，现在 {len(b.cards)} 个"
        if any(not c.name.strip() for c in b.cards):
            return False, "有地方没名字"
        return True, output

    who = [{"tags": p.tags, "summary": p.summary, "must_haves": p.must_haves,
            "avoid": p.avoid, "scene": p.scene, "place": p.place_guess} for p in profiles]

    picker = Agent(
        role="目的地推荐官",
        goal="按这些人的隐性需求，挑三个真正对得上的地方，并用一句话说清为什么",
        backstory="你走的地方多，知道'想去海边'和'想去没人的海边'是两回事。"
                  "你不推网红城市凑数，宁可推一个小地方。",
        llm=_llm(0.7),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    task = Task(
        description=f"""旅行者：
{json.dumps(who, ensure_ascii=False)}

{('他们明确提到了：' + hint) if hint else '他们还没说去哪。'}

推荐 2~3 个地方（城市或地区都行，国内外都行）。每个给：
- name：真实地名（如"泉州""罗弗敦群岛"）
- region：省/国家
- days：建议玩几天（1~7）
- reason：一句话，必须引用画像里的具体东西（"你说怕人多"），
  并说清"为什么是它，不是隔壁那个"

不许推荐只是因为有名的地方。理由里不许出现"风景优美""值得一去"。

只输出 JSON：{{"cards":[{{"name":"...","region":"...","days":3,"reason":"..."}}]}}""",
        expected_output="DestBundle",
        agent=picker,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[picker], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    b = _parse(out.tasks_output[-1] if out.tasks_output else out, DestBundle)
    if not b:
        return []
    return [
        DestinationCard(id=c.name, name=c.name, region=c.region, days=max(1, min(7, c.days)),
                        reason=c.reason, tags=[], score=0.0)
        for c in b.cards
    ]


class AutoPOIDraft(POIDraft):
    city: str = ""


def run_draft_pois_auto(text: str, days: int) -> tuple[str, list] | None:
    """从这段话里自己认出城市，同时写点位——为了能和"读人"并行跑。

    认不出城市就返回 city=""，上层改成让模型推荐目的地。
    """
    from crewai import Agent, Crew, Process, Task

    from travel.schemas import POI, Taste

    def check(output):
        d = _parse(output, AutoPOIDraft)
        if d is None:
            return False, "不是合法的 AutoPOIDraft JSON"
        if len(d.pois) > 15:
            return False, "点位太多，最多 15 个"
        return True, output

    guide = Agent(
        role="当地向导",
        goal="认出用户要去的地方，并列出那里能排进行程的点位",
        backstory="你在世界各地带过团。你知道哪些地方值得占掉半天、哪些半小时就够。"
                  "你只写自己确实知道的地方。",
        llm=_llm(0.5),
        allow_delegation=False,
        max_iter=2,
        verbose=False,
    )
    task = Task(
        description=f"""用户说：{text}

第一步：判断他要去哪。明确提到就写进 city（只写地名，如"大理"）。
只是说"想海边"这种没说地方的，city 留空字符串。

第二步：如果 city 有值，给这个城市 8~12 个点位，玩 {days} 天。
覆盖不同时段和室内外，其中至少 2 个是本地人才去、游客一般不知道的。
每个点位给：name（真实名字，别编）、category、tags（3 个）、duration_min、
cost（人均人民币）、indoor、best_slot（morning/afternoon/evening/any）、
crowd（0~1）、taste（quiet_lively/nature_urban/minimal_ornate/warm_cool/classic_trendy，各 -1~1）。
city 为空时，pois 返回空数组。

只输出 JSON：
{{"city":"...","pois":[{{"name":"...","category":"...","tags":["",""],"duration_min":120,
 "cost":0,"indoor":false,"best_slot":"morning","crowd":0.5,
 "taste":{{"quiet_lively":0,"nature_urban":0,"minimal_ornate":0,"warm_cool":0,"classic_trendy":0}}}}]}}""",
        expected_output="AutoPOIDraft",
        agent=guide,
        guardrail=check,
        guardrail_max_retries=2,
    )
    crew = Crew(agents=[guide], tasks=[task], process=Process.sequential,
                verbose=False, memory=False)
    out = crew.kickoff()
    d = _parse(out.tasks_output[-1] if out.tasks_output else out, AutoPOIDraft)
    if not d or not d.city.strip():
        return None

    base = Taste()
    pois = []
    for i, x in enumerate(d.pois, 1):
        taste = base.model_copy(update={
            k: max(-1.0, min(1.0, float(v)))
            for k, v in (x.taste or {}).items() if k in base.model_dump()
        })
        pois.append(POI(
            id=f"gen-{i}", dest_id="custom", name=x.name, category=x.category,
            tags=list(x.tags)[:3], taste=taste,
            crowd=max(0.0, min(1.0, x.crowd)),
            duration_min=max(20, min(360, x.duration_min)),
            cost=max(0.0, x.cost), indoor=bool(x.indoor),
            best_slot=x.best_slot if x.best_slot in ("morning", "afternoon", "evening", "any") else "any",
            source="model",
        ))
    return d.city.strip(), pois
