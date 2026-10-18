"""公平性指标计算"""
import numpy as np
from typing import Dict, List


def calculate_fairness_index(satisfaction_scores: Dict[str, float]) -> float:
    """
    公平性指数 = 1 - 变异系数

    变异系数 = 标准差 / 均值
    值越接近1越公平

    例：
    - 所有人满意度相同 → 公平性 = 1.0
    - 一人极高一人极低 → 公平性接近 0
    """
    if not satisfaction_scores:
        return 0.0

    values = list(satisfaction_scores.values())

    if len(values) == 1:
        return 1.0

    mean = np.mean(values)
    if mean == 0:
        return 0.0

    std = np.std(values)
    cv = std / mean  # 变异系数

    fairness = max(0.0, 1.0 - cv)
    return round(fairness, 4)


def check_pareto_optimal(
        current_allocation: Dict[str, float],
        alternative_allocations: List[Dict[str, float]]
) -> bool:
    """
    检查当前分配是否帕累托最优

    帕累托最优：不存在另一个分配方案，
    使得至少一人更好且没有人更差
    """
    for alt in alternative_allocations:
        # 检查alt是否帕累托优于current
        at_least_one_better = False
        no_one_worse = True

        for user in current_allocation:
            if user in alt:
                if alt[user] < current_allocation[user] - 1e-6:
                    no_one_worse = False
                    break
                if alt[user] > current_allocation[user] + 1e-6:
                    at_least_one_better = True

        if at_least_one_better and no_one_worse:
            return False  # 存在帕累托改进，当前不是最优

    return True


def calculate_gini_coefficient(satisfaction_scores: Dict[str, float]) -> float:
    """
    基尼系数（辅助指标）
    0 = 完全公平，1 = 完全不公平
    """
    values = sorted(satisfaction_scores.values())
    n = len(values)

    if n == 0:
        return 0.0

    total = sum(values)
    if total == 0:
        return 0.0

    cumulative = 0
    gini_sum = 0
    for i, v in enumerate(values):
        cumulative += v
        gini_sum += cumulative

    gini = (2 * gini_sum) / (n * total) - (n + 1) / n
    return max(0.0, gini)