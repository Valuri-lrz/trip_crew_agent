"""Shapley值计算测试"""
import pytest
from tools.shapley_calculator import calculate_shapley_values, calculate_shapley_sampling


def test_shapley_basic():
    """基本Shapley值测试"""
    users = ["A", "B", "C"]

    def utility(subset):
        """简单效用函数：每人贡献不同"""
        contributions = {"A": 3, "B": 2, "C": 1}
        return sum(contributions.get(u, 0) for u in subset)

    result = calculate_shapley_values(users, utility)

    # 对于可加效用函数，Shapley值 = 各自贡献
    assert abs(result["A"] - 3.0) < 0.01
    assert abs(result["B"] - 2.0) < 0.01
    assert abs(result["C"] - 1.0) < 0.01


def test_shapley_synergy():
    """有协同效应的Shapley值"""
    users = ["A", "B"]

    def utility(subset):
        if len(subset) == 0:
            return 0
        elif len(subset) == 1:
            return 1
        else:
            return 5  # 协同：1+1 > 2

    result = calculate_shapley_values(users, utility)

    # 对称博弈，Shapley值相等
    assert abs(result["A"] - result["B"]) < 0.01
    # 总和 = v({A,B}) - v({}) = 5
    assert abs(result["A"] + result["B"] - 5.0) < 0.01


def test_shapley_sum_property():
    """Shapley值总和 = 大联盟效用"""
    users = ["A", "B", "C"]

    def utility(subset):
        return len(subset) ** 2  # 超可加

    result = calculate_shapley_values(users, utility)

    # 总和应等于 v({A,B,C}) = 9
    total = sum(result.values())
    assert abs(total - 9.0) < 0.01


def test_shapley_sampling():
    """采样近似Shapley值"""
    users = ["A", "B", "C", "D", "E", "F", "G"]  # 7人，用采样

    def utility(subset):
        return len(subset) * 2

    result = calculate_shapley_sampling(users, utility, num_samples=5000)

    # 对称博弈，所有人Shapley值应接近
    values = list(result.values())
    assert max(values) - min(values) < 0.5  # 允许采样误差


if __name__ == "__main__":
    pytest.main([__file__, "-v"])