import pathlib

# 1) 排程：去重后如果还没排满，把能塞的补上（漠河第 1 天只排 1 个就是这毛病）
p = pathlib.Path("travel/engine.py")
s = p.read_text(encoding="utf-8")
old = '''        chosen = _dedup_category([avail[i] for i in picked])'''
new = '''        chosen = _dedup_category([avail[i] for i in picked])
        chosen = _top_up(chosen, avail, picks_budget=budget, max_k=max_k)'''
if old in s and "_top_up" not in s:
    s = s.replace(old, new, 1)
    s = s.replace(
        "def _dedup_category(pois: list[POI]) -> list[POI]:",
        '''def _top_up(chosen: list[POI], avail: list[POI], picks_budget: int,
            max_k: int) -> list[POI]:
    """背包按效用选，可能选到两个同类，去重后位置就空了——这里把空位补回来。"""
    if len(chosen) >= max_k:
        return chosen
    used = {p.id for p in chosen}
    cats = {p.category for p in chosen}
    total = sum(p.duration_min for p in chosen)
    pool = sorted((p for p in avail if p.id not in used and p.category not in cats),
                  key=lambda p: -p.duration_min)
    for p in pool:
        if len(chosen) >= max_k:
            break
        if total + p.duration_min <= picks_budget:
            chosen.append(p)
            cats.add(p.category)
            total += p.duration_min
    return chosen


def _dedup_category(pois: list[POI]) -> list[POI]:''',
        1,
    )
    p.write_text(s, encoding="utf-8")
print("top_up:", "_top_up" in p.read_text(encoding="utf-8"))

# 2) 已经看过图了，就别在图上看第二遍（转国内那次白花 7 秒）
q = pathlib.Path("travel/session.py")
t = q.read_text(encoding="utf-8")
old_intake = '''    profiles, cards, mode = pipeline.build_intake([s.text_input], [s.images])
    p0 = profiles[0] if profiles else None
    s.profiles, s.stage = profiles, 1
'''
new_intake = '''    # 转国内那次：图已经看过，画像也有了，只需要重新排一次目的地
    if s.domestic_forced and s.profiles:
        profiles, mode = s.profiles, _mode()
        cards = engine.rank_destinations(profiles, "", k=3)
    else:
        profiles, cards, mode = pipeline.build_intake([s.text_input], [s.images])
    p0 = profiles[0] if profiles else None
    s.profiles, s.stage = profiles, 1
'''
if old_intake in t:
    t = t.replace(old_intake, new_intake, 1)
    q.write_text(t, encoding="utf-8")
print("跳过二次看图:", "s.domestic_forced and s.profiles" in t)
