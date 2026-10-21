"""大模型连通性探针：分三层定位，别把"key 不对"和"CrewAI 不认"混在一起。

用法：
    py -3.13 -m scripts.probe_llm

它会依次试：
  1) 直连 OpenAI 兼容接口（只用 openai 库，不经过 CrewAI）—— 验 key 和模型名
  2) 用 CrewAI 的 LLM + 一个只有 1 个 Agent 的 Crew —— 验框架这层认不认
  3) 视觉接口（如果有图）—— 验多模态
任何一层失败都会打印它自己那层的报错，不会混在一起。
"""
from __future__ import annotations

import sys
import time

from travel.config import get_settings


def line(title: str) -> None:
    print("\n" + "─" * 56)
    print(title)
    print("─" * 56)


def probe_direct(s) -> bool:
    line("1) 直连 OpenAI 兼容接口")
    print(f"   base_url : {s.base_url}")
    print(f"   model    : {s.model}")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=30)
        t = time.time()
        resp = client.chat.completions.create(
            model=s.model,
            messages=[{"role": "user", "content": "只回四个字：连接成功"}],
            max_tokens=64,
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
        text = (resp.choices[0].message.content or "").strip()
        print(f"   ✅ {round(time.time() - t, 2)}s  →  {text!r}")
        if not text:
            print("   ⚠️ 接口通了但返回空内容——通常是 thinking 吃掉了 max_tokens。")
            print("      本项目所有调用都带 thinking:disabled，若仍为空就调大 max_tokens。")
            return False
        return True
    except Exception as exc:
        print(f"   ❌ {type(exc).__name__}: {exc}")
        if "model" in str(exc).lower() or "404" in str(exc):
            print("   提示：模型名可能不对。官方 api.deepseek.com 用 deepseek-chat / deepseek-reasoner；")
            print("        如果你走的是别的网关，把 MODEL_NAME 改成网关文档里的名字。")
        if "401" in str(exc) or "authentication" in str(exc).lower():
            print("   提示：key 不对或没生效，检查 .env 里的 DEEPSEEK_API_KEY。")
        return False


def probe_crewai(s) -> bool:
    line("2) 经 CrewAI（LLM + 单 Agent Crew）")
    try:
        from crewai import Agent, Crew, Process, Task

        from travel.agents import _llm

        agent = Agent(
            role="连通性测试员",
            goal="回答一个问题",
            backstory="你只做一件事：证明自己能说话。",
            llm=_llm(0.0),
            allow_delegation=False,
            max_iter=2,
            verbose=False,
        )
        task = Task(
            description="只回四个字：框架正常",
            expected_output="四个字",
            agent=agent,
        )
        t = time.time()
        out = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                   verbose=False, memory=False).kickoff()
        print(f"   ✅ {round(time.time() - t, 2)}s  →  {(out.raw or '')[:60]!r}")
        return True
    except Exception as exc:
        print(f"   ❌ {type(exc).__name__}: {exc}")
        print("   这层失败但第 1 层成功 → 问题在 CrewAI/LiteLLM 的适配，不在 key。")
        return False


def probe_vision(s, image: str | None) -> bool:
    line("3) 视觉接口")
    if not image:
        print("   跳过：没有给测试图。传一张试试：")
        print("   py -3.13 -m scripts.probe_llm path\\to\\photo.jpg")
        return False
    try:
        from travel import vision

        t = time.time()
        got = vision.analyze([image], "测试")
        if got is None:
            print("   ❌ 返回 None（接口报错或没有 key），看上面的日志")
            return False
        print(f"   ✅ {round(time.time() - t, 2)}s  →  tags={got.get('tags')}")
        return True
    except Exception as exc:
        print(f"   ❌ {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    s = get_settings()
    print(f"demo_mode={s.demo_mode}  llm_ready={s.llm_ready}  amap_ready={s.amap_ready}")

    if not s.api_key:
        line("没有 DEEPSEEK_API_KEY")
        print("  所以这三层我都没法验。")
        print("  系统此刻跑的是「规则兜底」：画像、推荐、排程全部由代码算，")
        print("  模型只在有 key 时接管。要验，先在 .env 里填上 key，再跑这条命令。")
        return 2

    ok1 = probe_direct(s)
    if not ok1:
        print("\n第 1 层就不通，先别管 CrewAI。修好 key / base_url / model 再来。")
        return 1
    ok2 = probe_crewai(s)
    probe_vision(s, sys.argv[1] if len(sys.argv) > 1 else None)

    if ok1 and ok2:
        print("\n结论：模型和框架都通，可以把 DEMO_MODE 设成 0 正式用了。")
        return 0
    print("\n结论：模型通，但 CrewAI 那层有问题，把上面第 2 段的报错发我。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
