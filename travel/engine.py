"""计算内核：打分 + 选目的地 + 排每日行程。纯 Python，不依赖任何 API。

隐性偏好三层在这里落成数字：
  审美 → taste_sim()      与景点/目的地的 5 维向量比
  情绪 → need_match()     点位的气质能不能满足这 6 种需求
  社交 → social_match()   独处/结伴、看/参与、怕不怕人多

这一层是确定性的：同样输入必然同样输出，可以单测。Agent 只调用，不自己算。
"""
from __future__ import annotations

import re

from travel.schemas import (
    DayPlan, Destination, DestinationCard, Emotion, Itinerary, POI, PlanItem,
    Profile, Social, Taste,
)
from travel.vibe import affinity

SLOTS = ["morning", "afternoon", "evening"]

# 文字 → 三层偏好。这是无模型时的兜底，也是给模型看的提示词素材。
RULES: list[dict] = [
    {"words": ("海", "看海", "海边", "沿海"), "tag": "海边",
     "taste": {"nature_urban": -0.5, "warm_cool": 0.2},
     "emotion": {"beauty": 0.25, "restore": 0.1}},
    {"words": ("安静", "人少", "清净", "不吵", "别太挤"), "tag": "安静",
     "taste": {"quiet_lively": -0.7},
     "emotion": {"restore": 0.3}, "social": {"crowd_tolerance": -0.25}},
    {"words": ("拍照", "出片", "摄影", "拍片"), "tag": "出片",
     "taste": {"classic_trendy": 0.15, "minimal_ornate": 0.2},
     "emotion": {"beauty": 0.3}},
    {"words": ("徒步", "爬山", "登山", "走山"), "tag": "徒步",
     "taste": {"nature_urban": -0.8, "quiet_lively": -0.3},
     "emotion": {"achieve": 0.4, "novelty": 0.1}, "social": {"participate": 0.3}},
    {"words": ("吃", "美食", "小吃", "好吃"), "tag": "吃",
     "taste": {"quiet_lively": 0.3, "warm_cool": 0.4},
     "emotion": {"belong": 0.15, "novelty": 0.1}},
    {"words": ("热闹", "夜市", "酒吧", "夜生活"), "tag": "热闹",
     "taste": {"quiet_lively": 0.7},
     "emotion": {"belong": 0.2}, "social": {"crowd_tolerance": 0.2, "together": 0.2}},
    {"words": ("累", "放松", "休息", "发呆", "不赶", "悠闲", "慢"), "tag": "慢",
     "taste": {"quiet_lively": -0.4, "warm_cool": 0.2},
     "emotion": {"restore": 0.35}, "social": {"crowd_tolerance": -0.15}},
    {"words": ("古城", "老城", "历史", "古建", "老房子"), "tag": "老城",
     "taste": {"classic_trendy": -0.7}, "emotion": {"beauty": 0.1}},
    {"words": ("城市", "逛街", "购物", "商场"), "tag": "逛街",
     "taste": {"nature_urban": 0.5}, "social": {"crowd_tolerance": 0.1}},
    {"words": ("文艺", "咖啡", "书店", "展"), "tag": "文艺",
     "taste": {"minimal_ornate": -0.3, "classic_trendy": 0.3},
     "emotion": {"beauty": 0.15, "restore": 0.1}},
    {"words": ("朋友", "一起", "结伴", "兄弟", "闺蜜"), "tag": "结伴",
     "emotion": {"belong": 0.2}, "social": {"together": 0.4}},
    {"words": ("一个人", "独自", "自己"), "tag": "独处",
     "social": {"together": -0.8}},
    {"words": ("孩子", "带娃", "家庭", "爸妈", "父母"), "tag": "家庭",
     "emotion": {"belong": 0.2}, "social": {"together": 0.5, "participate": -0.2}},
    {"words": ("新鲜", "不一样", "刺激", "没去过"), "tag": "新鲜",
     "emotion": {"novelty": 0.35}},
    {"words": ("攻略", "计划", "安排", "确定"), "tag": "要安排",
     "emotion": {"control": 0.3}},
]

MONTH_WORDS = ["元旦", "春节", "清明", "五一", "端午", "暑假", "十一", "国庆", "周末",
               "冬天", "春天", "夏天", "秋天"]
NUM_CN = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

EMO_WORDS = {
    "restore": "松下来", "novelty": "找点新鲜的", "control": "把事都定好",
    "belong": "有人一起", "beauty": "看好看的东西", "achieve": "走点有点难度的",
}


# ------------------------------------------------------------------ 打分
def taste_sim(a: Taste, b: Taste) -> float:
    """5 维曼哈顿距离归一化到 [0,1]，1 = 完全同调。"""
    va, vb = a.vec(), b.vec()
    d = sum(abs(x - y) for x, y in zip(va, vb)) / len(va)
    return max(0.0, 1.0 - d / 2.0)


def need_match(poi: POI, profile: Profile) -> float:
    """这个点位能满足多少情绪需求（按需求的权重平均）。"""
    v = affinity(poi)
    e = profile.emotion
    needs = {"restore": e.restore, "novelty": e.novelty, "belong": e.belong,
             "beauty": e.beauty, "achieve": e.achieve}
    total = sum(needs.values()) or 1.0
    return sum(w * v[k] for k, w in needs.items()) / total


def social_match(poi: POI, profile: Profile) -> float:
    """社交风格是否合拍：结伴/独处、看/参与。"""
    v = affinity(poi)
    want_together = (profile.social.together + 1) / 2
    want_part = (profile.social.participate + 1) / 2
    diff = abs(want_together - v["together"]) + abs(want_part - v["participate"])
    return max(0.0, 1.0 - diff / 2)


def score_poi(poi: POI, profile: Profile) -> float:
    """一个人对一个点位的满意度，[0, 1]。"""
    text = poi.name + " ".join(poi.tags)
    if any(a and a in text for a in profile.avoid):
        return 0.0
    sim = taste_sim(profile.aesthetic, poi.taste)
    hit = len(set(profile.interests) & set(poi.tags))
    tag = min(hit / max(1, len(profile.interests)), 1.0) if profile.interests else 0.0
    cost = min(poi.cost / 300.0, 1.0)
    crowd_pen = max(0.0, poi.crowd - profile.social.crowd_tolerance) * 1.5
    u = (0.40 * sim + 0.12 * tag + 0.10 * (1 - cost)
         + 0.22 * need_match(poi, profile) + 0.16 * social_match(poi, profile))
    return round(max(0.0, min(1.0, u - 0.12 * crowd_pen)), 4)


def group_utility(poi: POI, profiles: list[Profile]) -> float:
    """多人：均值 + 最不满意那个人的分数，避免有人完全被牺牲。"""
    if not profiles:
        return 0.0
    scores = [score_poi(poi, p) for p in profiles]
    return round(0.7 * (sum(scores) / len(scores)) + 0.3 * min(scores), 4)


# ------------------------------------------------------------------ 选目的地
def best_subset(items: list[tuple[int, float, int]], budget: int, max_k: int) -> list[int]:
    """0/1 背包：items = [(下标, 效用, 时长)]，在时长与个数约束下取效用最大。

    dp[i][k][t] = 只考虑前 i 个、选 k 个、耗时 t 时的最大效用。
    比原地的二维写法多用一点内存，换来回溯一定对——这一点比省内存重要。
    """
    usable = [it for it in items if 0 < it[2] <= budget]
    n = len(usable)
    if n == 0 or max_k <= 0:
        return []

    NEG = float("-inf")
    dp = [[[NEG] * (budget + 1) for _ in range(max_k + 1)] for _ in range(n + 1)]
    dp[0][0][0] = 0.0
    for i in range(1, n + 1):
        _, u, d = usable[i - 1]
        for k in range(max_k + 1):
            for t in range(budget + 1):
                best = dp[i - 1][k][t]
                if k > 0 and t >= d and dp[i - 1][k - 1][t - d] > NEG:
                    cand = dp[i - 1][k - 1][t - d] + u
                    if cand > best:
                        best = cand
                dp[i][k][t] = best

    bk, bt, best = 0, 0, 0.0
    for k in range(max_k + 1):
        for t in range(budget + 1):
            if dp[n][k][t] > best:
                best, bk, bt = dp[n][k][t], k, t

    chosen: list[int] = []
    i, k, t = n, bk, bt
    while i > 0 and k > 0:
        if abs(dp[i][k][t] - dp[i - 1][k][t]) < 1e-9:
            i -= 1
        else:
            idx, _, d = usable[i - 1]
            chosen.append(idx)
            t -= d
            k -= 1
            i -= 1
    return sorted(chosen)


def plan_days(pois: list[POI], profiles: list[Profile], days: int,
              budget: int = 480, max_k: int = 3, scorer=None) -> list[DayPlan]:
    """把候选点位排进每一天，同一点位只用一次。

    control 高（希望被安排清楚）的人，一天排满 3 个；control 低就留白。
    """
    control = sum(p.emotion.control for p in profiles) / max(1, len(profiles))
    if control <= 0.35:
        max_k = min(max_k, 2)
    used: set[str] = set()
    out: list[DayPlan] = []
    for d in range(1, days + 1):
        avail = [p for p in pois if p.id not in used]
        if not avail:
            out.append(DayPlan(day=d, items=[], note="候选点位用完了，建议缩短天数"))
            continue
        sc = scorer or (lambda x: group_utility(x, profiles))
        items = [(i, sc(p), p.duration_min) for i, p in enumerate(avail)]
        picked = best_subset(items, budget, max_k)
        chosen = _dedup_category([avail[i] for i in picked])
        order = {s: n for n, s in enumerate(SLOTS)}
        chosen.sort(key=lambda p: order.get(p.best_slot, 9))
        plan_items: list[PlanItem] = []
        clock = 9 * 60          # 一天从 9 点开始
        for n, (slot, poi) in enumerate(zip(SLOTS, chosen)):
            used.add(poi.id)
            travel = 0 if n == 0 else 25      # 市内两点之间先按 25 分钟估
            clock += travel
            item = make_item(poi, slot, profiles)
            item.start_time = f"{clock // 60:02d}:{clock % 60:02d}"
            item.travel_min = travel
            clock += poi.duration_min
            plan_items.append(item)
        out.append(DayPlan(day=d, items=plan_items,
                           total_min=sum(i.duration_min for i in plan_items)))
    return out


def make_item(poi: POI, slot: str, profiles: list[Profile]) -> PlanItem:
    """把点位变成一条"攻略条目"：为什么、亮点、避坑、花费。"""
    return PlanItem(
        poi_id=poi.id, name=poi.name, slot=slot, duration_min=poi.duration_min,
        indoor=poi.indoor, utility=group_utility(poi, profiles),
        why=_why(poi, profiles), highlight=_highlight(poi), tip=_tip(poi),
        cost=poi.cost,
    )


def _dedup_category(pois: list[POI]) -> list[POI]:
    seen, out = set(), []
    for p in pois:
        if p.category in seen:
            continue
        seen.add(p.category)
        out.append(p)
    return out


def _why(poi: POI, profiles: list[Profile]) -> str:
    tags = "、".join(poi.tags[:2])
    for p in profiles:
        for i in p.interests:
            if i in poi.tags:
                return f"{tags}，对上你想的「{i}」"
    return tags


def _highlight(poi: POI) -> str:
    """一句话亮点。目标：看一眼就知道这地方好在哪。"""
    tags = set(poi.tags)
    if "海" in tags:
        return "海就在边上，风大，待着比拍照舒服"
    if tags & {"古建", "老宅", "老房子", "骑楼", "老建筑"}:
        return "老房子和巷子，慢慢走才有意思"
    if tags & {"梯田", "视野", "山", "晒秋"}:
        return "要爬一段，上去了视野值回票价"
    if tags & {"小吃", "夜市", "海鲜", "本地", "市井"}:
        return "本地人也在吃的店，别赶饭点"
    if tags & {"咖啡", "小店", "发呆", "喝茶"}:
        return "坐下来就不太想走的地方"
    if poi.indoor:
        return "室内，下雨也不耽误"
    return "、".join(poi.tags[:2]) if poi.tags else poi.name


def _tip(poi: POI) -> str:
    """避坑。不确定的一律写成"出发前确认"，不装懂。"""
    bits: list[str] = []
    if poi.crowd >= 0.75:
        bits.append("人多，尽量早上去")
    if poi.duration_min >= 180:
        bits.append("半天起步，带水")
    if poi.cost > 0:
        bits.append(f"人均约 ¥{int(poi.cost)}")
    if poi.indoor:
        bits.append("雨天首选")
    bits.append("营业/预约未核实")
    return "，".join(bits)


def build_from(dest: Destination, pois: list[POI], profiles: list[Profile],
               days: int, budget: int = 480, max_k: int = 3, scorer=None) -> Itinerary:
    """用给定的点位排行程（点位可以来自库，也可以是模型现场写的）。"""
    days_plan = plan_days(pois, profiles, days, budget, max_k, scorer)
    notes: list[str] = []
    if any(not d.items for d in days_plan):
        notes.append("有几天没排满，候选点位不够，可以考虑少玩一天。")
    return Itinerary(dest=dest, days=days_plan, notes=notes)


def swap_item(itinerary: Itinerary, day_no: int, poi_id: str, spare: list[POI],
              profiles: list[Profile], budget: int = 480) -> tuple[Itinerary, str]:
    """只换这一个点位，其他天、其他条都不动。"""
    days = [d.model_copy(deep=True) for d in itinerary.days]
    day = next((d for d in days if d.day == day_no), None)
    if day is None:
        return itinerary, "没找到这一天。"
    idx = next((n for n, i in enumerate(day.items) if i.poi_id == poi_id), None)
    if idx is None:
        return itinerary, "没找到这个安排。"

    old = day.items[idx]
    used = {i.poi_id for d in days for i in d.items}
    cands = [p for p in spare if p.id not in used]
    if not cands:
        return itinerary, "这个城市能换的都换过了。"

    old_cat = next((p.category for p in spare if p.id == poi_id), "")
    room = budget - (day.total_min - old.duration_min)
    same = [p for p in cands if p.category == old_cat]
    fits = [p for p in same + cands if p.duration_min <= room]
    if not fits:
        return itinerary, f"第 {day_no} 天已经排满，换不下新的了。"

    def gain(p: POI) -> float:
        base = group_utility(p, profiles)
        bonus = 0.08 if p.category == old_cat else 0.0
        return base + bonus

    best = max(fits, key=gain)
    day.items[idx] = make_item(best, old.slot, profiles)
    day.total_min = sum(i.duration_min for i in day.items)
    new = itinerary.model_copy(update={"days": days})
    return new, f"把「{old.name}」换成了「{best.name}」。"


# ------------------------------------------------------------------ 文字解析
def extract_brief(text: str) -> dict:
    """从一句话里抽人数、天数、时间、三层偏好。抽不到给默认值，不追问。"""
    t = text or ""
    people = 2
    if re.search(r"一个人|独自|自己去|solo", t):
        people = 1
    else:
        m = re.search(r"(\d)\s*(?:个人|人|位)", t)
        if m:
            people = max(1, min(6, int(m.group(1))))
        else:
            m = re.search(r"([一二两三四五六])\s*(?:个人|人|位)", t)
            if m:
                people = NUM_CN.get(m.group(1), 2)
        if re.search(r"女朋友|男朋友|老婆|老公|对象|情侣|我们俩|我和|朋友|带娃|爸妈|孩子", t):
            people = max(people, 2)

    days = 3
    m = re.search(r"(\d)\s*天", t)
    if m:
        days = max(1, min(7, int(m.group(1))))
    else:
        m = re.search(r"([一二两三四五六七八])\s*天", t)
        if m:
            days = NUM_CN.get(m.group(1), 3)

    month = next((w for w in MONTH_WORDS if w in t), "")

    taste = {k: 0.0 for k in Taste().model_dump()}
    emotion = Emotion().model_dump()
    social = Social().model_dump()
    tags: list[str] = []
    for rule in RULES:
        if not any(w in t for w in rule["words"]):
            continue
        if rule["tag"] not in tags:
            tags.append(rule["tag"])
        for k, v in rule.get("taste", {}).items():
            taste[k] += v
        for k, v in rule.get("emotion", {}).items():
            emotion[k] += v
        for k, v in rule.get("social", {}).items():
            social[k] += v

    # 人数本身就是社交信号
    if people == 1:
        social["together"] -= 0.6
    elif people >= 3:
        social["together"] += 0.4

    hint = ""

    return {
        "people": people, "days": days, "month": month, "hint": hint,
        "tags": tags[:3],
        "taste": {k: max(-1.0, min(1.0, v)) for k, v in taste.items()},
        "emotion": {k: max(0.0, min(1.0, v)) for k, v in emotion.items()},
        "social": {
            "together": max(-1.0, min(1.0, social["together"])),
            "participate": max(-1.0, min(1.0, social["participate"])),
            "crowd_tolerance": max(0.15, min(1.0, social["crowd_tolerance"])),
        },
    }


def rule_profiles(texts: list[str]) -> list[Profile]:
    """没有模型时的画像：关键词规则。输出形状和模型版完全一致。"""
    profiles: list[Profile] = []
    for i, text in enumerate(texts):
        b = extract_brief(text)
        profiles.append(Profile(
            user_id=f"u{i + 1}",
            tags=b["tags"] or ["随便看看"],
            summary=describe(b),
            interests=b["tags"],
            aesthetic=Taste(**b["taste"]),
            emotion=Emotion(**b["emotion"]),
            social=Social(**b["social"]),
            confidence=0.45,
        ))
    return profiles


def describe(b: dict) -> str:
    """把三层翻译成一句人话。"""
    emo = max(EMO_WORDS, key=lambda k: b["emotion"][k])
    head = f"你想要的是一次「{EMO_WORDS[emo]}」的旅行"
    bits = []
    if b["days"]:
        bits.append(f"{b['days']} 天")
    q = b["taste"]["quiet_lively"]
    if q < -0.25:
        bits.append("最好安静点")
    elif q > 0.25:
        bits.append("热闹点也没事")
    if b["taste"]["nature_urban"] < -0.25:
        bits.append("多在自然里")
    together = b["social"]["together"]
    if together > 0.3:
        bits.append("有人一起")
    elif together < -0.3:
        bits.append("一个人待着")
    return head + "：" + ("，".join(bits) if bits else "按你的节奏来") + "。"


# ------------------------------------------------------------------ 候选方案集
def user_utility(itinerary, profile: Profile, index: dict) -> float:
    """某个人在这个方案上的满意度：他所去点位的平均分。"""
    ids = [i.poi_id for d in itinerary.days for i in d.items]
    scores = [score_poi(index[i], profile) for i in ids if i in index]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def candidate_plans(dest: Destination, pois: list[POI], profiles: list[Profile],
                    days: int, budget: int = 480, max_k: int = 3) -> list:
    """出一组取舍不同的方案：平均照顾 / 各自主导。博弈就在这组方案上算。"""
    k = len(profiles)
    if k == 0:
        return [build_from(dest, pois, profiles, days, budget, max_k)]

    weight_sets = [[1.0] * k]
    for i in range(k):
        w = [0.25] * k
        w[i] = 1.5
        weight_sets.append(w)

    plans, seen = [], set()
    for w in weight_sets:
        def sc(p, w=w):
            return sum(w[i] * score_poi(p, profiles[i]) for i in range(k)) / sum(w)

        it = build_from(dest, pois, profiles, days, budget, max_k, scorer=sc)
        key = tuple(tuple(i.poi_id for i in d.items) for d in it.days)
        if key and any(key) and key not in seen:
            seen.add(key)
            plans.append(it)
    return plans
