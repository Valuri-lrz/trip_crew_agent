"""博弈效用函数"""
from typing import List, Dict, Callable
from models.emotion_score import ExperienceEmotionScore, get_user_weights


def build_utility_function(
        user_profiles: Dict[str, dict],
        activities: List[dict]
) -> Callable[[List[str]], float]:
    """
    构建博弈效用函数

    核心思想：
    - 每个活动有多维情感评分
    - 每个用户有不同权重（由画像决定）
    - 效用 = Σ(用户个性化效用) + 协同效应

    Args:
        user_profiles: {user_id: profile_dict}
        activities: [{"name": "...", "emotion_score": {...}, ...}]

    Returns:
        utility_function(subset) -> float
    """

    def utility_function(user_subset: List[str]) -> float:
        if not user_subset:
            return 0.0

        total_utility = 0.0

        for user_id in user_subset:
            profile = user_profiles.get(user_id, {})
            weights = get_user_weights_from_dict(profile)

            # 找对该用户效用最高的活动
            best_utility = 0.0
            for activity in activities:
                score_dict = activity.get("emotion_score", {})
                score = ExperienceEmotionScore(**score_dict) if score_dict else ExperienceEmotionScore()
                u = score.utility(weights)
                best_utility = max(best_utility, u)

            total_utility += best_utility

        # 协同效应
        synergy = calculate_synergy(user_subset, activities)

        return total_utility + synergy

    return utility_function


def get_user_weights_from_dict(profile: dict) -> Dict[str, float]:
    """从字典格式的画像中提取权重"""
    tone = profile.get("emotional_tone", "治愈型")

    base = {
        "excitement": 0.20,
        "relaxation": 0.20,
        "novelty": 0.20,
        "social_fulfillment": 0.15,
        "aesthetic_pleasure": 0.15,
        "fatigue_penalty": 0.10,
    }

    adjustments = {
        "逃离型": {"relaxation": +0.15, "excitement": -0.10},
        "探索型": {"novelty": +0.15, "excitement": +0.10, "relaxation": -0.10},
        "治愈型": {"relaxation": +0.20, "aesthetic_pleasure": +0.10, "excitement": -0.15},
        "社交型": {"social_fulfillment": +0.20, "excitement": +0.05},
        "成就型": {"excitement": +0.15, "novelty": +0.10},
    }

    adj = adjustments.get(tone, {})
    weights = base.copy()
    for k, v in adj.items():
        weights[k] = max(0.05, weights.get(k, 0) + v)

    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def calculate_synergy(users: List[str], activities: List[dict]) -> float:
    """
    协同效应：某些活动多人一起体验效用更高
    如：火锅一个人吃没意思，4个人吃效用翻倍
    """
    synergy = 0.0
    for activity in activities:
        social_mult = activity.get("social_multiplier", 0)
        min_group = activity.get("min_group_size", 1)

        if social_mult > 0 and len(users) >= min_group:
            synergy += social_mult * (len(users) - min_group + 1) * 0.1

    return synergy