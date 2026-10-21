"""博弈层单测：三个性质 + 一个手算例子。

这些是数学性质，不是"看起来对"：
  效率性  Σφ = v(N)
  对称性  完全一样的两个人，φ 相等
  哑元    对谁都没影响的人，φ = 0
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from travel import game  # noqa: E402


class TestShapley(unittest.TestCase):
    def test_hand_computed_two_players(self):
        # 两个方案，a 只在方案0 有用，b 只在方案1 有用：
        # v(a)=1, v(b)=1, v(ab)=max(1,1)=1  →  φ_a = φ_b = 0.5
        U = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        phi = game.shapley(["a", "b"], U)
        self.assertAlmostEqual(phi["a"], 0.5)
        self.assertAlmostEqual(phi["b"], 0.5)

    def test_efficiency(self):
        U = {"a": [0.9, 0.2, 0.4], "b": [0.3, 0.8, 0.1], "c": [0.2, 0.3, 0.9]}
        phi = game.shapley(["a", "b", "c"], U)
        self.assertAlmostEqual(sum(phi.values()), game.coalition_value({"a", "b", "c"}, U))

    def test_symmetry(self):
        U = {"a": [1.0, 0.0], "b": [1.0, 0.0], "c": [0.0, 1.0]}
        phi = game.shapley(["a", "b", "c"], U)
        self.assertAlmostEqual(phi["a"], phi["b"])

    def test_dummy_player_gets_zero(self):
        # b 对任何方案都拿 0，改变不了联盟能拿到什么
        U = {"a": [1.0, 0.0], "b": [0.0, 0.0]}
        phi = game.shapley(["a", "b"], U)
        self.assertAlmostEqual(phi["b"], 0.0)
        self.assertAlmostEqual(phi["a"], 1.0)


class TestChoice(unittest.TestCase):
    def test_nash_prefers_balanced(self):
        # 方案0 一人独吞，方案1 两人都不差 → 比例公平应选 1
        U = {"a": [1.0, 0.6], "b": [0.1, 0.6]}
        self.assertEqual(game.pick_nash(["a", "b"], U), 1)

    def test_ledger_concession(self):
        U = {"a": [1.0, 0.6], "b": [0.1, 0.6]}
        rows = game.ledger(["a", "b"], U, 1)
        a = next(r for r in rows if r["user"] == "a")
        self.assertAlmostEqual(a["concession"], 0.4)

    def test_blocking_detected(self):
        # 方案0 对两人都更好，但被选成 1 时，{a,b} 是阻塞联盟
        U = {"a": [0.7, 0.5], "b": [0.7, 0.5]}
        self.assertEqual(game.blocking(["a", "b"], U, 1), ["a、b"])

    def test_no_blocking(self):
        U = {"a": [0.7, 0.5], "b": [0.4, 0.6]}
        self.assertEqual(game.blocking(["a", "b"], U, 1), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
