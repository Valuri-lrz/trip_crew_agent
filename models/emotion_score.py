"""多维情感评分模型"""
from pydantic import BaseModel, Field
from typing import Dict, Optional


class ExperienceEmotionScore(BaseModel):
    """
    多维情感评分 - 作为博弈的效用函数

    每个维度 0-1，fatigue_cost 为负向指标
    """
    excitement: float = Field(default=0.5, ge=0, le=1, description="兴奋度")
    relaxation: float = Field(default=0.5, ge=0, le=1, description="放松度")
    novelty: float = Field(default=0.5, ge=0, le=1, description="新鲜感")
    social_fulfillment: float = Field(default=0.5, ge=0, le=1, description="社交满足")
    aesthetic_pleasure: float = Field(default=0.5, ge=0, le=1, description="审美愉悦")
    fatigue_cost: float = Field(default=0.3, ge=0, le=1, description="体力消耗(负向)")

    def utility(self, user_weights: Dict[str, float]) -> float:
        """
        根据用户个性化权重计算效用值

        Args:
            user_weights: 用户画像决定的各维度权重
                {"excitement": 0.2, "relaxation": 0.3, ...}

        Returns:
            效用值（越高越好）
        """
        return (
                user_weights.get('excitement', 0.2) * self.excitement +
                user_weights.get('relaxation', 0.2) * self.relaxation +
                user_weights.get('novelty', 0.2) * self.novelty +
                user_weights.get('social_fulfillment', 0.15) * self.social_fulfillment +
                user_weights.get('aesthetic_pleasure', 0.15) * self.aesthetic_pleasure -
                user_weights.get('fatigue_penalty', 0.1) * self.fatigue_cost
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "excitement": self.excitement,
            "relaxation": self.relaxation,
            "novelty": self.novelty,
            "social_fulfillment": self.social_fulfillment,
            "aesthetic_pleasure": self.aesthetic_pleasure,
            "fatigue_cost": self.fatigue_cost,
        }


def get_user_weights(profile) -> Dict[str, float]:
    """
    根据用户画像动态生成情感评分权重

    不同情感基调 → 不同权重分配
    """
    base_weights = {
        "excitement": 0.20,
        "relaxation": 0.20,
        "novelty": 0.20,
        "social_fulfillment": 0.15,
        "aesthetic_pleasure": 0.15,
        "fatigue_penalty": 0.10,
    }

    tone = getattr(profile, 'emotional_tone', None)
    if tone is None:
        return base_weights

    tone_str = tone.value if hasattr(tone, 'value') else str(tone)

    adjustments = {
        "逃离型": {"relaxation": +0.15, "excitement": -0.10, "fatigue_penalty": +0.05},
        "探索型": {"novelty": +0.15, "excitement": +0.10, "relaxation": -0.10},
        "治愈型": {"relaxation": +0.20, "aesthetic_pleasure": +0.10, "excitement": -0.15},
        "社交型": {"social_fulfillment": +0.20, "excitement": +0.05, "relaxation": -0.10},
        "成就型": {"excitement": +0.15, "novelty": +0.10, "relaxation": -0.10},
    }

    adj = adjustments.get(tone_str, {})
    weights = base_weights.copy()
    for k, v in adj.items():
        weights[k] = max(0.05, weights.get(k, 0) + v)

    # 归一化
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    return weights