"""Shapley值计算工具"""
import math
from itertools import combinations
from typing import List, Dict, Callable
from crewai.tools import tool


def calculate_shapley_values(
        users: List[str],
        utility_function: Callable[[List[str]], float]
) -> Dict[str, float]:
    """
    精确计算Shapley值

    Shapley值 = 用户加入任意联盟时的平均边际贡献

    旅游场景含义：
    - 值高 → 该用户偏好对整体影响大 → 话语权大
    - 值低 → 该用户偏好容易被满足 → 可适当让步

    复杂度：O(2^n)，适合 n ≤ 6
    """
    n = len(users)
    shapley_values = {user: 0.0 for user in users}

    for user in users:
        others = [u for u in users if u != user]

        for size in range(len(others) + 1):
            for subset in combinations(others, size):
                subset_list = list(subset)

                # 边际贡献 = v(S ∪ {i}) - v(S)
                marginal = (
                        utility_function(subset_list + [user]) -
                        utility_function(subset_list)
                )

                # Shapley权重
                weight = (
                        math.factorial(size) * math.factorial(n - size - 1)
                        / math.factorial(n)
                )

                shapley_values[user] += weight * marginal

    return shapley_values


def calculate_shapley_sampling(
        users: List[str],
        utility_function: Callable[[List[str]], float],
        num_samples: int = 1000
) -> Dict[str, float]:
    """
    蒙特卡洛采样近似Shapley值（用户数 > 6 时使用）
    """
    import random

    n = len(users)
    shapley_values = {user: 0.0 for user in users}

    for _ in range(num_samples):
        # 随机排列
        perm = users.copy()
        random.shuffle(perm)

        prev_value = utility_function([])
        for user in perm:
            current_subset = perm[:perm.index(user) + 1]
            current_value = utility_function(current_subset)
            shapley_values[user] += (current_value - prev_value)
            prev_value = current_value

    # 取平均
    for user in users:
        shapley_values[user] /= num_samples

    return shapley_values


@tool("calculate_shapley")
def calculate_shapley_tool(users_json: str, utilities_json: str) -> str:
    """
    计算多用户的Shapley值。
    输入：
        users_json: 用户ID列表的JSON字符串，如 '["user1","user2","user3"]'
        utilities_json: 各用户对各活动的效用值JSON，如 '{"user1": {"活动A": 0.8, "活动B": 0.3}, ...}'
    输出：Shapley值JSON
    """
    import json

    try:
        users = json.loads(users_json)
        utilities = json.loads(utilities_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON解析失败: {e}"}, ensure_ascii=False)

    def utility_function(subset: List[str]) -> float:
        if not subset:
            return 0.0
        total = 0.0
        for user in subset:
            if user in utilities:
                # 取该用户最高效用的活动
                user_utils = utilities[user]
                if user_utils:
                    total += max(user_utils.values())
        return total

    n = len(users)
    if n <= 6:
        result = calculate_shapley_values(users, utility_function)
    else:
        result = calculate_shapley_sampling(users, utility_function)

    return json.dumps(result, ensure_ascii=False, indent=2)