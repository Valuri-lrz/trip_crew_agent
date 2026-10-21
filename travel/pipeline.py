"""流水线：把 Agent、引擎、外部数据串起来，每一步都可降级。

没有点位库了。所有目的地和点位都由模型现生成，
引擎只负责"用给定的点位排出一个可行的行程"。
可信度靠标注，而不是靠预置数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from travel import agents, engine, live, vision
from travel.config import get_settings
from travel.schemas import (
    Destination, DestinationCard, Emotion, Itinerary, POI, Profile, Social, Taste,
)


@dataclass
class Intake:
    profiles: list[Profile] = field(default_factory=list)
    cards: list[DestinationCard] = field(default_factory=list)
    mode: str = "demo"
    opening: str = ""
    city_hint: str = ""
    analysis: str = ""
    clarify: str = ""


def _blend(a: float, b: float, wa: float = 0.55) -> float:
    return round(wa * b + (1 - wa) * a, 3)


def merge_visual(profile: Profile, visual: dict | None) -> Profile:
    """把图片线索并进画像。图片和文字冲突时，两边都留，标注在 evidence。"""
    if not visual:
        return profile
    wa = 0.55 if profile.interests else 0.85
    tags = list(dict.fromkeys(list(visual.get("tags") or []) + list(profile.tags)))[:5]
    aes = dict(profile.aesthetic.model_dump())
    for k, v in (visual.get("aesthetic") or {}).items():
        if k in aes:
            aes[k] = max(-1.0, min(1.0, _blend(aes[k], float(v), wa)))
    emo = dict(profile.emotion.model_dump())
    for k, v in (visual.get("emotion") or {}).items():
        if k in emo:
            emo[k] = max(0.0, min(1.0, _blend(emo[k], float(v), wa)))
    soc = dict(profile.social.model_dump())
    for k, v in (visual.get("social") or {}).items():
        if k in soc:
            soc[k] = max(-1.0 if k != "crowd_tolerance" else 0.15,
                         min(1.0, _blend(soc[k], float(v), wa)))
    return profile.model_copy(update={
        "tags": tags,
        "aesthetic": Taste(**aes),
        "emotion": Emotion(**emo),
        "social": Social(**soc),
        "evidence": list(visual.get("evidence") or [])[:3],
        "confidence": max(profile.confidence, float(visual.get("confidence") or 0)),
        "scene": visual.get("scene") or {},
        "far": bool(visual.get("far")),
        "place_guess": visual.get("place_guess") or "",
        "summary": profile.summary or (visual.get("summary") or ""),
    })


def build_intake(texts: list[str], images: list[list[str]]) -> Intake:
    """文字 + 图片 → 画像 + 候选目的地。"""
    s = get_settings()
    visuals = [vision.analyze(images[i] if i < len(images) else [], t)
               for i, t in enumerate(texts)]

    # 一句话里可能有两个人的诉求，人数以文字抽出来的为准
    said = engine.extract_brief(" ".join(texts)).get("people", 1)
    people = max(len(texts), max(1, min(4, int(said or 1))))

    out = Intake()
    profiles: list[Profile] | None = None
    if s.llm_ready:
        try:
            bundle = agents.run_profiler(texts, visuals, people)
            if bundle:
                profiles = bundle.profiles
                out.opening = bundle.opening or ""
                out.city_hint = (bundle.city_hint or "").strip()
                out.analysis = bundle.analysis or ""
                out.clarify = bundle.clarify or ""
                out.mode = "llm"
        except Exception:
            profiles = None
    if not profiles:
        profiles = engine.rule_profiles(texts)

    out.profiles = [merge_visual(p, visuals[i] if i < len(visuals) else None)
                    for i, p in enumerate(profiles)]

    if s.llm_ready:
        try:
            out.cards = agents.suggest_destinations(out.profiles, out.city_hint)
        except Exception:
            out.cards = []
    return out


def verify_pois(pois: list[POI], city: str) -> dict[str, dict]:
    """用高德核对模型写的点位：查得到就挂上评分/营业时间，查不到就标注。

    这是"AI 生成 + 真实数据"唯一靠谱的组合方式：
    生成负责覆盖面的，查证负责可信度。
    """
    if not get_settings().amap_ready or not pois:
        return {}
    found: dict[str, dict] = {}
    for p in pois:
        f = live.place_facts(p.name, city)
        if f:
            found[p.id] = f
        else:
            p.note = "高德没查到这个点位，可能名字不对或已经不在了"
    return found


def _profile_only(texts: list[str], images: list[list[str]]) -> Intake:
    """只读人，不推目的地。给并行用。"""
    s = get_settings()
    visuals = [vision.analyze(images[i] if i < len(images) else [], t)
               for i, t in enumerate(texts)]
    said = engine.extract_brief(" ".join(texts)).get("people", 1)
    people = max(len(texts), max(1, min(4, int(said or 1))))

    out = Intake()
    profiles = None
    if s.llm_ready:
        try:
            bundle = agents.run_profiler(texts, visuals, people)
            if bundle:
                profiles = bundle.profiles
                out.opening = bundle.opening or ""
                out.city_hint = (bundle.city_hint or "").strip()
                out.analysis = bundle.analysis or ""
                out.clarify = bundle.clarify or ""
                out.mode = "llm"
        except Exception:
            profiles = None
    if not profiles:
        profiles = engine.rule_profiles(texts)
    out.profiles = [merge_visual(p, visuals[i] if i < len(visuals) else None)
                    for i, p in enumerate(profiles)]
    return out


def _plan_from(city: str, pois: list[POI], profiles: list[Profile], days: int):
    """点位已经有了：排程 + 高德核对 + 天气。"""
    cfg = get_settings()
    dest = Destination(id=city, name=city, region="", best_days=days,
                       tags=["未核实"], blurb="模型按记忆写的点位，没核实过")
    it = engine.build_from(dest, pois, profiles, days,
                           cfg.day_budget_min, cfg.max_items_per_day)
    it.notes.append("点位和时长是模型按记忆写的，营业时间/门票/还开不开都没核实。")

    # 多人：在候选方案上算 Shapley，选一个比例公平的，并给出让步账本
    if len(profiles) >= 2:
        try:
            from travel import game

            cands = engine.candidate_plans(dest, pois, profiles, days,
                                           cfg.day_budget_min, cfg.max_items_per_day)
            if len(cands) >= 2:
                index = {p.id: p for p in pois}
                U = {p.user_id: [engine.user_utility(c, p, index) for c in cands]
                     for p in profiles}
                players = list(U)
                j = game.pick_nash(players, U)
                it = cands[j]
                it.ledger = game.ledger(players, U, j)
                stuck = game.blocking(players, U, j)
                line = "；".join(
                    f"{r['user']} 让了 {r['concession']:.2f}" for r in it.ledger
                )
                it.notes.append(f"从 {len(cands)} 个取舍里选了这一个：{line}。")
                if stuck:
                    it.notes.append(f"注意：{stuck} 一起换方案会都更好，说明这次没排到最稳。")
        except Exception:
            pass

    facts = verify_pois(pois, city)
    if facts:
        for day in it.days:
            for item in day.items:
                if item.poi_id in facts:
                    item.facts = facts[item.poi_id]
        missed = sum(1 for p in pois if not p.note and p.id not in facts)
        if missed == 0:
            it.notes.append(f"{len(facts)} 个点位都在高德查到了，评分和营业时间来自高德。")
        else:
            it.notes.append(f"{len(facts)} 个点位高德查到了，其余没查到，出发前自己确认。")

    it = attach_weather(it)
    return it, pois, _fallback_question(it)


def intake_parallel(text: str, images: list[str], days: int):
    """读人 和 写点位 同时跑——它们本来互不依赖，串着跑白等一倍时间。"""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(_profile_only, [text], [images])
        fb = ex.submit(agents.run_draft_pois_auto, text, days)
        intake = fa.result()
        try:
            auto = fb.result()
        except Exception:
            auto = None

    if not auto or not intake.profiles:
        return intake, None
    city, pois = auto
    if not pois:
        return intake, None
    return intake, _plan_from(city, pois, intake.profiles, days)


def build_plan_for(city: str, profiles: list[Profile], days: int):
    """任意城市：模型现写点位 → 引擎排程。

    返回 (行程, 点位池, 问题)，失败返回 None。
    """
    cfg = get_settings()
    if not cfg.llm_ready:
        return None
    try:
        pois = agents.run_draft_pois(city, profiles, days)
    except Exception:
        pois = None
    if not pois:
        return None

    dest = Destination(id=city, name=city, region="", best_days=days,
                       tags=["未核实"], blurb="模型按记忆写的点位，没核实过")
    it = engine.build_from(dest, pois, profiles, days,
                           cfg.day_budget_min, cfg.max_items_per_day)
    it.notes.append("点位和时长是模型按记忆写的，营业时间/门票/还开不开都没核实。")
    facts = verify_pois(pois, city)
    if facts:
        for day in it.days:
            for item in day.items:
                if item.poi_id in facts:
                    item.facts = facts[item.poi_id]
        missed = sum(1 for p in pois if not p.note and p.id not in facts)
        if missed == 0:
            it.notes.append(f"{len(facts)} 个点位都在高德查到了，评分和营业时间来自高德。")
        else:
            it.notes.append(f"{len(facts)} 个点位高德查到了，其余没查到，出发前自己确认。")

    it = attach_weather(it)
    return it, pois, _fallback_question(it)


def polish(itinerary: Itinerary, profiles: list[Profile]) -> Itinerary:
    """把草稿文案换成具体攻略。失败就原样返回，不阻塞。"""
    if not get_settings().llm_ready:
        return itinerary
    try:
        got = agents.run_planner(itinerary, profiles)
        return got[0] if got else itinerary
    except Exception:
        return itinerary


def say(situation: str, draft: str) -> str:
    """让模型把模板话术说成人话。任何失败都退回草稿，绝不卡住。"""
    if not get_settings().llm_ready:
        return draft
    try:
        return agents.run_voice(situation, draft) or draft
    except Exception:
        return draft


def attach_weather(itinerary: Itinerary) -> Itinerary:
    """有 adcode 才拉天气（现在都是现生成的目的地，通常没有）。"""
    if not itinerary.dest.adcode:
        itinerary.notes.append("天气没查（没有这个城市的编码），出发前自己看一眼。")
        return itinerary
    casts = live.weather(itinerary.dest.adcode)
    if not casts:
        itinerary.notes.append("天气没拿到（高德不可用），出发前自己看一眼。")
        return itinerary
    for i, day in enumerate(itinerary.days):
        if i >= len(casts):
            break
        day.weather = f"{casts[i]['text']} {casts[i]['temp']}"
        if live.is_bad_weather(casts[i]["text"]):
            itinerary.notes.append(f"第 {day.day} 天可能有雨，可以一键换成室内。")
    return itinerary


def _fallback_question(itinerary: Itinerary) -> str:
    for d in itinerary.days:
        if len(d.items) >= 3:
            return f"第 {d.day} 天排了 3 个地方，会不会太赶？"
    return ""


def check_constraints(itinerary: Itinerary, budget: int) -> list[str]:
    """硬约束检查。不通过就回给引擎重排。"""
    problems = []
    seen: set[str] = set()
    for day in itinerary.days:
        if not day.items:
            problems.append(f"第 {day.day} 天空白")
        total = sum(i.duration_min for i in day.items)
        if total > budget:
            problems.append(f"第 {day.day} 天 {total} 分钟，超预算")
        for item in day.items:
            if item.poi_id in seen:
                problems.append(f"{item.name} 重复出现")
            seen.add(item.poi_id)
    return problems
