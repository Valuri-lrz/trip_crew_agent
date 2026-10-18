"""评估指标"""
import numpy as np
from typing import Dict, List, Optional


def evaluate_result(
        satisfaction_scores: Dict[str, float],
        preference_coverage: float,
        fairness_index: float,
        response_time: float = 0.0,
        implicit_hit_rate: float = 0.0,
) -> Dict[str, float]:
    """
    综合评估

    Returns:
        评估指标字典
    """
    metrics = {
        "fairness_index": fairness_index,
        "preference_coverage": preference_coverage,
        "avg_satisfaction": np.mean(list(satisfaction_scores.values())) if satisfaction_scores else 0,
        "satisfaction_std": np.std(list(satisfaction_scores.values())) if satisfaction_scores else 0,
        "implicit_hit_rate": implicit_hit_rate,
        "response_time_seconds": response_time,
    }

    # 综合得分（加权）
    metrics["overall_score"] = (
            0.3 * fairness_index +
            0.3 * preference_coverage +
            0.2 * metrics["avg_satisfaction"] +
            0.2 * implicit_hit_rate
    )

    return metrics


def print_evaluation_report(metrics: Dict[str, float]):
    """打印评估报告"""
    print("\n" + "=" * 50)
    print("📊 评估报告")
    print("=" * 50)
    print(f"  公平性指数:       {metrics['fairness_index']:.4f}")
    print(f"  偏好覆盖率:       {metrics['preference_coverage']:.2%}")
    print(f"  平均满意度:       {metrics['avg_satisfaction']:.4f}")
    print(f"  满意度标准差:     {metrics['satisfaction_std']:.4f}")
    print(f"  隐性偏好命中率:   {metrics['implicit_hit_rate']:.2%}")
    print(f"  响应时间:         {metrics['response_time_seconds']:.1f}s")
    print(f"  ─────────────────────────────")
    print(f"  综合得分:         {metrics['overall_score']:.4f}")
    print("=" * 50)