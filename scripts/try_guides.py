"""用假摘要验证"抽事实 + 报冲突"这套逻辑。

真跑要 Tavily key；没有 key 也要能证明：矛盾会被保留，而不是被抹平。
"""
import json

from travel import guides

SNIPPETS = [
    {"title": "沙溪古镇旅游攻略 2022", "content":
        "门票：古镇免费，兴教寺单独收 20 元。从大理古城出发车程约 2 小时，"
        "建议早上到，中午后旅行团多。", "url": "https://example.com/a"},
    {"title": "沙溪 2024 最新", "content":
        "现在进古镇要收 50 元维护费，兴教寺包含在内。停车场离古镇 1 公里，"
        "需要走进去。周末人多。", "url": "https://example.com/b"},
    {"title": "本地人说的沙溪", "content":
        "寺登街早上八点前基本没人，适合拍照。古镇里吃饭选择少，最好在镇上吃。",
        "url": "https://example.com/c"},
]

if __name__ == "__main__":
    got = guides.summarize("沙溪古镇", "大理", SNIPPETS)
    if not got:
        print("抽取失败")
        raise SystemExit(1)
    print("=== 事实 ===")
    for f in got.facts:
        print(f"[{f.source}] {f.field}：{f.value}  {('(' + f.year_hint + ')') if f.year_hint else ''}")
    print("\n=== 矛盾 ===")
    for c in got.conflicts:
        print("·", c)
    print("\nJSON:", json.dumps(got.model_dump(), ensure_ascii=False)[:200])
