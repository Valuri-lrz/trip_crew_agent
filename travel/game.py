"""博弈层：候选方案上的 Shapley 值与让步账本。

为什么 v(S) 必须写成「联盟共享同一个方案」：

    v(S) = max_{p ∈ P} Σ_{i∈S} u_i(p)

如果写成每人各取各的最优（v(S)=Σ max u_i），那 Shapley 就退化成
「这个人自己最想要的东西有多想要」，跟联盟里的其他人完全无关，
φ_i 只等于 u_i(best) 加一个常数——算了个寂寞。

写成共享方案之后，加一个人会改变"大家一起选哪个"，边际贡献才真正依赖联盟构成。

另一个关键：φ 高不代表"话语权大"，恰恰相反。
φ 高 = 有他不多、没他不少（好带）；φ 低 = 他的诉求和集体最优冲突，被牺牲了。
所以账本要用 Δ = 独自最优 − 实际拿到 来定价补偿，而不是用 φ 加权。
"""
from __future__ import annotations

import math
from itertools import combinations


def coalition_value(S, U: dict[str, list[float]]) -> float:
    """联盟能拿到的最好结果：大家只能共享同一个方案。"""
    if not S:
        return 0.0
    m = len(next(iter(U.values())))
    return max(sum(U[p][j] for p in S) for j in range(m))


def shapley(players: list[str], U: dict[str, list[float]]) -> dict[str, float]:
    """精确 Shapley，O(2^n)。n ≤ 6 都很快。"""
    n = len(players)
    phi = {p: 0.0 for p in players}
    for p in players:
        rest = [q for q in players if q != p]
        for size in range(len(rest) + 1):
            w = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            for S in combinations(rest, size):
                phi[p] += w * (coalition_value(set(S) | {p}, U) - coalition_value(set(S), U))
    return phi


def pick_nash(players: list[str], U: dict[str, list[float]], eps: float = 1e-3) -> int:
    """选方案：最大化各人效用的乘积（比例公平），而不是总和。"""
    m = len(next(iter(U.values())))
    best, best_v = 0, -1e18
    for j in range(m):
        v = sum(math.log(max(U[p][j], eps)) for p in players)
        if v > best_v:
            best, best_v = j, v
    return best


def ledger(players: list[str], U: dict[str, list[float]], chosen: int) -> list[dict]:
    """让步账本：谁贡献多少、谁被牺牲、该补偿多少。"""
    phi = shapley(players, U)
    rows = []
    for p in players:
        best_alone = max(U[p])
        got = U[p][chosen]
        rows.append({
            "user": p,
            "shapley": round(phi[p], 3),
            "best_alone": round(best_alone, 3),
            "got": round(got, 3),
            "concession": round(best_alone - got, 3),
        })
    return rows


def blocking(players: list[str], U: dict[str, list[float]], chosen: int) -> list[str]:
    """核心检查：有没有一个联盟，能靠换个方案让里面所有人都更好。"""
    m = len(next(iter(U.values())))
    out = []
    for size in range(2, len(players) + 1):
        for S in combinations(players, size):
            for j in range(m):
                if j != chosen and all(U[p][j] > U[p][chosen] + 1e-9 for p in S):
                    out.append("、".join(S))
                    break
    return out
