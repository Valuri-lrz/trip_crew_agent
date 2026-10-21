"""冲突处理：按最新的来，旧说法保留但降级。

规则（用户定的）：
1. 同一字段有多个说法 → 取年份最新的那个
2. 没有年份的，按来源顺序靠前的算，并标注"无年份"
3. 旧说法不删，挂在该字段下面，标"旧"
4. 最后永远补一句：具体信息还得自己核实
"""

from __future__ import annotations

from travel.guides import GuideBundle, GuideFact

TAIL = "以上是网上攻略和模型整理的，门票、营业时间、预约这些，出发前自己再核一遍。"


def _year(f: GuideFact) -> int:
    y = (f.year_hint or "").strip()
    return int(y) if y.isdigit() else 0


def resolve(bundle: GuideBundle) -> dict:
    """按字段归组，每组取最新。返回给接口用的字典。"""
    by_field: dict[str, list[GuideFact]] = {}
    for f in bundle.facts:
        by_field.setdefault(f.field, []).append(f)

    latest: list[dict] = []
    old: list[dict] = []
    for field, items in by_field.items():
        ranked = sorted(items, key=_year, reverse=True)
        head = ranked[0]
        latest.append({
            "field": field,
            "value": head.value,
            "year": head.year_hint or "无年份",
            "source": head.source,
        })
        for f in ranked[1:]:
            old.append({
                "field": field,
                "value": f.value,
                "year": f.year_hint or "无年份",
                "source": f.source,
            })

    return {
        "latest": latest,
        "old": old,
        "conflicts": bundle.conflicts,
        "tail": TAIL,
    }


def one_liner(bundle: GuideBundle, limit: int = 3) -> str:
    """拼成一句话，用在回复里。"""
    got = resolve(bundle)
    if not got["latest"]:
        return ""
    parts = [f"{x['field']} {x['value']}（{x['year']}）" for x in got["latest"][:limit]]
    return "；".join(parts)
