"""同一件事问两遍，看数字稳不稳。

用法：py -3.13 -m scripts.precision_probe "问题"
"""
import sys

from openai import OpenAI

from travel.config import get_settings


def ask(q: str, temp: float) -> str:
    s = get_settings()
    c = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=60)
    r = c.chat.completions.create(
        model=s.model,
        messages=[{"role": "user", "content": q}],
        temperature=temp,
        max_tokens=160,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return (r.choices[0].message.content or "").strip()


def main() -> int:
    q = sys.argv[1] if len(sys.argv) > 1 else "大理喜洲严家大院：门票多少钱？几点开门、几点关门？"
    print("Q:", q)
    for i, t in enumerate((0.0, 0.7), 1):
        print(f"\n--- 第 {i} 次 (temperature={t}) ---")
        try:
            print(ask(q, t))
        except Exception as e:
            print("FAIL", type(e).__name__, e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
