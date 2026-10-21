"""点位"气质"：从已有的 category / tags / crowd 推导出情绪与社交属性。

为什么不给每个 POI 手写这些数字：
- 审美是"这地方长什么样"，必须人工标（5 个维度，和用户对齐）
- 情绪/社交是"这地方能提供什么"，可以从品类和标签推导，而且推导规则可解释

推导出来的结果在 [0,1]，含义：
  restore     能不能让人松下来
  novelty     新不新鲜
  belong      适不适合一群人一起
  beauty      好不好看
  achieve     有没有点挑战/成就感
  together    适不适合结伴去
  participate 是看还是参与
"""
from __future__ import annotations

from functools import lru_cache

from travel.schemas import POI

DIMS = ["restore", "novelty", "belong", "beauty", "achieve", "together", "participate"]

TAG_RULES: dict[str, dict[str, float]] = {
    "海": {"beauty": 0.30, "restore": 0.15},
    "视野": {"beauty": 0.25, "achieve": 0.15},
    "拍照": {"beauty": 0.35},
    "出片": {"beauty": 0.35},
    "老房子": {"beauty": 0.20, "novelty": 0.10},
    "老建筑": {"beauty": 0.25},
    "老城": {"beauty": 0.15, "belong": 0.15},
    "古建": {"beauty": 0.25},
    "安静": {"restore": 0.35},
    "人少": {"restore": 0.30},
    "发呆": {"restore": 0.40},
    "慢": {"restore": 0.30},
    "喝茶": {"restore": 0.30, "participate": 0.20},
    "咖啡": {"restore": 0.20, "beauty": 0.10},
    "散步": {"restore": 0.20},
    "骑行": {"participate": 0.35, "achieve": 0.20},
    "徒步": {"achieve": 0.40, "participate": 0.20},
    "爬山": {"achieve": 0.35},
    "山": {"achieve": 0.25, "restore": 0.15},
    "小吃": {"belong": 0.20, "novelty": 0.15},
    "夜市": {"belong": 0.35, "novelty": 0.20},
    "热闹": {"belong": 0.30},
    "市井": {"belong": 0.25, "novelty": 0.10},
    "海鲜": {"belong": 0.20, "beauty": 0.10},
    "非遗": {"novelty": 0.25, "beauty": 0.15},
    "动手": {"participate": 0.40},
    "逛街": {"belong": 0.15, "participate": 0.15},
    "小店": {"novelty": 0.15},
    "梯田": {"beauty": 0.30},
    "晒秋": {"beauty": 0.25, "novelty": 0.15},
}

CATEGORY_RULES: dict[str, dict[str, float]] = {
    "餐饮": {"belong": 0.25, "participate": 0.15},
    "茶馆": {"restore": 0.25, "participate": 0.10},
    "街区": {"belong": 0.20},
    "市集": {"belong": 0.25, "novelty": 0.20},
    "演艺": {"belong": 0.30, "beauty": 0.20},
    "自然": {"achieve": 0.15, "restore": 0.15},
    "古迹": {"achieve": 0.15, "beauty": 0.20},
    "展馆": {"beauty": 0.15, "novelty": 0.15},
    "海岛": {"beauty": 0.30},
    "村落": {"restore": 0.15, "beauty": 0.10},
    "古镇": {"beauty": 0.20, "belong": 0.10},
    "文创": {"novelty": 0.25},
    "海边": {"beauty": 0.30, "restore": 0.15},
}


@lru_cache(maxsize=512)
def _affinity_cached(poi_id: str, category: str, tags: tuple[str, ...], crowd: float,
                     duration_min: int, indoor: bool) -> tuple[tuple[str, float], ...]:
    v = {k: 0.32 for k in DIMS}
    for tag in tags:
        for k, d in TAG_RULES.get(tag, {}).items():
            v[k] += d
    for k, d in CATEGORY_RULES.get(category, {}).items():
        v[k] += d

    # 人多：不适合放松，适合"凑热闹"
    v["restore"] -= crowd * 0.35
    v["belong"] += crowd * 0.25
    # 待得久、在室内：更能恢复
    if duration_min >= 150:
        v["restore"] += 0.10
    if indoor:
        v["restore"] += 0.08

    v["together"] = 0.30 + v["belong"] * 0.60
    v["participate"] = v["participate"] + (0.15 if duration_min >= 180 else 0.0)
    return tuple((k, round(max(0.0, min(1.0, v[k])), 3)) for k in DIMS)


def affinity(poi: POI) -> dict[str, float]:
    return dict(_affinity_cached(poi.id, poi.category, tuple(poi.tags), poi.crowd,
                                 poi.duration_min, poi.indoor))
