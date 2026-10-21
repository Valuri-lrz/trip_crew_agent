"""内核单测：不联网、不调模型，纯逻辑。

没有点位库了，测试自己造点位——引擎只认 POI 对象，不关心它从哪来。
"""
from __future__ import annotations

import itertools
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from travel import adjust, engine  # noqa: E402
from travel.schemas import Destination, POI, Taste  # noqa: E402
from travel.vibe import DIMS, affinity  # noqa: E402


def make_poi(i: int, category: str = "景点", indoor: bool = False,
             dur: int = 120, crowd: float = 0.5, cost: float = 0.0,
             tags: list[str] | None = None) -> POI:
    return POI(id=f"p{i}", dest_id="t", name=f"点位{i}", category=category,
               tags=tags or ["安静", "走路"], taste=Taste(quiet_lively=-0.4),
               crowd=crowd, duration_min=dur, cost=cost, indoor=indoor)


POOL = [
    make_poi(1, "自然", False, 150, 0.4),
    make_poi(2, "古镇", False, 120, 0.6),
    make_poi(3, "展馆", True, 90, 0.3),
    make_poi(4, "餐饮", True, 60, 0.7, 50),
    make_poi(5, "街区", False, 90, 0.9),
    make_poi(6, "自然", False, 180, 0.2),
    make_poi(7, "体验", True, 120, 0.4, 80),
    make_poi(8, "古迹", False, 90, 0.5, 40),
    make_poi(9, "村落", False, 120, 0.3),
]

DEST = Destination(id="t", name="测试城")


def brute(items, budget, max_k):
    best, best_val = (), -1.0
    for k in range(max_k + 1):
        for combo in itertools.combinations(items, k):
            if sum(c[2] for c in combo) <= budget:
                val = sum(c[1] for c in combo)
                if val > best_val:
                    best_val, best = val, combo
    return sorted(c[0] for c in best)


class TestTaste(unittest.TestCase):
    def test_identity(self):
        t = Taste(quiet_lively=-0.4, nature_urban=0.2)
        self.assertAlmostEqual(engine.taste_sim(t, t), 1.0)

    def test_bounds(self):
        a = Taste(quiet_lively=-1, nature_urban=-1, minimal_ornate=-1,
                  warm_cool=-1, classic_trendy=-1)
        b = Taste(quiet_lively=1, nature_urban=1, minimal_ornate=1,
                  warm_cool=1, classic_trendy=1)
        self.assertAlmostEqual(engine.taste_sim(a, b), 0.0)


class TestKnapsack(unittest.TestCase):
    def test_matches_brute_force(self):
        rnd = random.Random(7)
        for _ in range(200):
            n = rnd.randint(1, 7)
            items = [(i, round(rnd.random(), 3), rnd.randint(20, 200)) for i in range(n)]
            budget = rnd.randint(60, 500)
            max_k = rnd.randint(1, 3)
            got = engine.best_subset(items, budget, max_k)
            want = brute(items, budget, max_k)
            self.assertAlmostEqual(sum(items[i][1] for i in got),
                                   sum(items[i][1] for i in want), places=6)
            self.assertLessEqual(sum(items[i][2] for i in got), budget)


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.profiles = engine.rule_profiles(["两个人 三天 想安静 喜欢拍照"])

    def test_no_duplicate_and_within_budget(self):
        it = engine.build_from(DEST, POOL, self.profiles, 3)
        ids = [i.poi_id for d in it.days for i in d.items]
        self.assertEqual(len(ids), len(set(ids)))
        for d in it.days:
            self.assertLessEqual(sum(i.duration_min for i in d.items), 480)

    def test_deterministic(self):
        a = engine.build_from(DEST, POOL, self.profiles, 3).model_dump()
        b = engine.build_from(DEST, POOL, self.profiles, 3).model_dump()
        self.assertEqual(a, b)


class TestAdjust(unittest.TestCase):
    def setUp(self):
        self.profiles = engine.rule_profiles(["两个人 三天"])
        self.it = engine.build_from(DEST, POOL, self.profiles, 3)

    def test_rain_makes_day_dry_without_duplicates(self):
        # 下雨可以"从别的天借室内"，所以不保证别的天一字不动；
        # 但必须：第 1 天没有户外了，而且全程不出现重复点位。
        new, msg = adjust.adjust(self.it, "rain", self.profiles, POOL, day=1)
        self.assertTrue(msg)
        self.assertEqual([i.indoor for i in new.days[0].items],
                         [True] * len(new.days[0].items))
        ids = [i.poi_id for d in new.days for i in d.items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_tired_shrinks_one_day(self):
        new, _ = adjust.adjust(self.it, "tired", self.profiles, POOL, day=2)
        self.assertLessEqual(len(new.days[1].items), len(self.it.days[1].items))
        self.assertEqual(len(new.days[2].items), len(self.it.days[2].items))


class TestSwap(unittest.TestCase):
    def test_swap_keeps_others(self):
        profiles = engine.rule_profiles(["两个人 三天"])
        it = engine.build_from(DEST, POOL, profiles, 3)
        target = it.days[0].items[0]
        new, msg = engine.swap_item(it, 1, target.poi_id, POOL, profiles)
        self.assertTrue(msg)
        self.assertNotEqual(new.days[0].items[0].poi_id, target.poi_id)
        self.assertEqual([x.model_dump() for x in new.days[1].items],
                         [x.model_dump() for x in it.days[1].items])


class TestBrief(unittest.TestCase):
    def test_people_and_days(self):
        b = engine.extract_brief("我们三个人想五一去大理玩四天，喜欢安静，怕人多")
        self.assertEqual(b["people"], 3)
        self.assertEqual(b["days"], 4)
        self.assertEqual(b["month"], "五一")
        self.assertLess(b["social"]["crowd_tolerance"], 0.6)

    def test_defaults(self):
        b = engine.extract_brief("随便看看")
        self.assertGreaterEqual(b["people"], 1)
        self.assertEqual(b["days"], 3)


class TestVibe(unittest.TestCase):
    def test_bounds(self):
        for p in POOL:
            v = affinity(p)
            self.assertEqual(set(v), set(DIMS))
            for k, x in v.items():
                self.assertTrue(0.0 <= x <= 1.0, f"{p.name} {k}={x}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
