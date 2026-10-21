"""动态调整：不重排全部，只做局部替换。

三种触发：
  rain   下雨 → 户外换室内；没有空闲室内就从别的天借，把那天的户外挪过去
  tired  累了 → 去掉最费体力的那个
  loosen 太赶 → 去掉最不值的那个

点位池由会话提供（现在没有库了），所以 spare 从外面传进来。
"""
from __future__ import annotations

from travel.engine import score_poi
from travel.schemas import DayPlan, Itinerary, PlanItem, POI, Profile


def adjust(itinerary: Itinerary, kind: str, profiles: list[Profile],
           spare: list[POI] | None = None, day: int | None = None) -> tuple[Itinerary, str]:
    """返回 (新行程, 给用户看的一句话)。原对象不修改。"""
    days = [d.model_copy(deep=True) for d in itinerary.days]
    idx = _pick_day(days, day)
    if idx is None:
        return itinerary, "这几天的安排都挺松了，不用改。"

    if kind == "rain":
        msg = _swap_indoor(days, idx, profiles, itinerary, spare or [])
        _recount(days)
    elif kind == "tired":
        msg = _drop(days[idx], by_duration=True)
    elif kind == "loosen":
        msg = _drop(days[idx], by_duration=False)
    else:
        return itinerary, "这个调整我还没学会，先按原来的来。"

    return itinerary.model_copy(update={"days": days}), msg


def _pick_day(days: list[DayPlan], day: int | None) -> int | None:
    if day is not None and 1 <= day <= len(days):
        return day - 1
    for i, d in enumerate(days):
        if len(d.items) >= 2:
            return i
    return 0 if days else None


def _recount(days: list[DayPlan]) -> None:
    for d in days:
        d.total_min = sum(i.duration_min for i in d.items)


def _copy(item: PlanItem, slot: str) -> PlanItem:
    new = item.model_copy(deep=True)
    new.slot = slot
    return new


def _swap_indoor(days: list[DayPlan], idx: int, profiles: list[Profile],
                 it: Itinerary, spare: list[POI]) -> str:
    day = days[idx]
    used = {i.poi_id for d in days for i in d.items}
    pool = [p for p in spare if p.indoor and p.id not in used]
    pool.sort(key=lambda p: -(score_poi(p, profiles[0]) if profiles else 0.0))

    replaced = borrowed = 0
    for item in [i for i in day.items if not i.indoor]:
        if pool:
            cand = pool.pop(0)
            item.poi_id, item.name = cand.id, cand.name
            item.duration_min, item.indoor = cand.duration_min, True
            item.why = "下雨的备选：" + "、".join(cand.tags[:2])
            replaced += 1
            continue

        found = None
        for j in range(len(days)):
            if j == idx:
                continue
            for x in days[j].items:
                if x.indoor:
                    found = (j, x)
                    break
            if found:
                break
        if found is None:
            break
        j, other = found
        days[j].items = [x for x in days[j].items if x.poi_id != other.poi_id]
        days[j].items.append(_copy(item, slot=other.slot))
        item.poi_id, item.name = other.poi_id, other.name
        item.duration_min, item.indoor = other.duration_min, True
        item.why = "从别的天挪过来的室内，你那天的户外换过去"
        borrowed += 1

    if replaced or borrowed:
        day.note = f"改成室内：换了 {replaced + borrowed} 个"
        if borrowed:
            return (f"第 {day.day} 天换成室内了：{replaced} 个直接换掉，"
                    f"{borrowed} 个从别的天挪过来，那边的户外挪到晴天去。")
        return f"第 {day.day} 天换成室内了：{replaced} 个换掉，其余不动。"

    keep = [i for i in day.items if i.indoor]
    dropped = len(day.items) - len(keep)
    day.items = keep
    day.note = f"没有合适的室内替代，{dropped} 个先空出来"
    return (f"第 {day.day} 天找不到合适的室内替代，先把 {dropped} 个户外的空出来，"
            f"剩下的不动。")


def _drop(day: DayPlan, by_duration: bool) -> str:
    if len(day.items) <= 1:
        return f"第 {day.day} 天已经只剩一个安排了，再减就空了。"
    key = (lambda i: i.duration_min) if by_duration else (lambda i: i.utility)
    victim = max(day.items, key=key)
    day.items = [i for i in day.items if i.poi_id != victim.poi_id]
    day.total_min = sum(i.duration_min for i in day.items)
    day.note = "松了一点，空出来的时间可以随便走走"
    reason = "最费体力的" if by_duration else "最不值得的"
    return (f"第 {day.day} 天去掉了{reason}那个（{victim.name}），"
            f"现在剩 {len(day.items)} 个地方，中间能坐一会儿。")
