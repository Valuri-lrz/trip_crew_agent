"""TravelCrew B 档 MVP 前端。

启动：
    py -3.13 -m streamlit run app/streamlit_mvp.py --server.port 8502

设计原则：
- 原生 Streamlit 组件 + `.streamlit/config.toml` 主题，不靠私有 CSS
- 真实等待，不做假进度
- 结构化渲染，不解析 LLM 字符串 JSON
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import streamlit as st

try:
    from app.mvp_crew import run_trip
except ImportError:  # streamlit run app/streamlit_mvp.py puts app/ on sys.path
    from mvp_crew import run_trip

UPLOAD_DIR = Path(".data/uploads")
MAX_IMAGES = 3
MAX_IMAGE_MB = 8
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

st.set_page_config(
    page_title="TravelCrew · 多智能体旅行规划",
    page_icon=":material/route:",
    layout="wide",
)


def cleanup_uploads(max_age_hours: int = 24) -> None:
    if not UPLOAD_DIR.exists():
        return
    cutoff = time.time() - max_age_hours * 3600
    for path in UPLOAD_DIR.glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def save_uploads(files, user_id: str) -> list[str]:
    if not files:
        return []
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for file in list(files)[:MAX_IMAGES]:
        suffix = Path(file.name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            st.warning(f"{file.name} 不是支持的图片格式，已跳过。")
            continue
        if file.size > MAX_IMAGE_MB * 1024 * 1024:
            st.warning(f"{file.name} 超过 {MAX_IMAGE_MB}MB，已跳过。")
            continue
        target = UPLOAD_DIR / f"{user_id}_{uuid.uuid4().hex}{suffix}"
        target.write_bytes(file.getbuffer())
        paths.append(str(target.resolve()))
    return paths


def badges(items: list[str], color: str = "blue") -> str:
    safe = [str(x).replace("[", "(").replace("]", ")").strip() for x in items if str(x).strip()]
    return " ".join(f":{color}-badge[{x}]" for x in safe)


def itinerary_markdown(result: dict) -> str:
    itinerary = result["itinerary"]
    lines = [f"# {itinerary.get('destination', '')} 行程", "", itinerary.get("summary", ""), ""]
    for day in itinerary.get("days", []):
        lines.append(f"## Day {day['day']} · {day.get('theme', '')}")
        for item in day.get("items", []):
            lines.append(f"- **{item.get('time_slot', '')}** {item.get('name', '')}")
            if item.get("location"):
                lines.append(f"  - 地点：{item['location']}")
            if item.get("why"):
                lines.append(f"  - 理由：{item['why']}")
        lines.append("")
    if itinerary.get("tips"):
        lines.append("## 实用提示")
        lines.extend(f"- {tip}" for tip in itinerary["tips"])
    return "\n".join(lines)


cleanup_uploads()

with st.sidebar:
    st.markdown("### TravelCrew")
    st.caption("多智能体旅行规划 · B 档")
    st.badge("CrewAI 3 agents", icon=":material/hub:", color="green")
    st.space("small")

    destination = st.text_input("目的地", "大理", icon=":material/location_on:")
    days = st.slider("天数", 1, 7, 3)
    num_users = st.slider("同行人数", 1, 5, 2)

    st.space("small")
    st.caption("图片用于推断隐性偏好；搜索/天气不可用时会标注“需核实”。")
    st.caption("当前版本不含 Shapley、公平性、记忆和多轮协商。")

st.title("把一群人的偏好，变成一条能走的路线", icon=":material/route:")
st.caption("TravelCrew 用 3 个 CrewAI Agent 完成偏好分析、目的地研究和行程编排。")

badge_cols = st.columns(3)
with badge_cols[0]:
    st.badge("多模态偏好", icon=":material/image:", color="violet")
with badge_cols[1]:
    st.badge("结构化输出", icon=":material/schema:", color="blue")
with badge_cols[2]:
    st.badge("真实工具调用", icon=":material/build:", color="orange")

st.space("medium")

with st.container(border=True):
    st.subheader("旅行者", icon=":material/group:")
    st.caption("每人最多 3 张参考图；图片只用于偏好推理，不会出现在行程里。")

    texts: list[str] = [""] * num_users
    uploads: list[list] = [[] for _ in range(num_users)]

    for row_start in range(0, num_users, 3):
        row_count = min(3, num_users - row_start)
        cols = st.columns(row_count, gap="medium")
        for offset in range(row_count):
            index = row_start + offset
            with cols[offset]:
                with st.container(border=True):
                    st.markdown(f"**旅行者 {index + 1}**")
                    texts[index] = st.text_area(
                        "偏好",
                        key=f"user_text_{index}",
                        height=120,
                        placeholder="例：想安静看海，不想太商业化；必须有一天博物馆",
                        label_visibility="collapsed",
                    )
                    files = st.file_uploader(
                        "参考图片",
                        type=["jpg", "jpeg", "png", "webp"],
                        accept_multiple_files=True,
                        key=f"user_images_{index}",
                        max_upload_size=MAX_IMAGE_MB,
                        label_visibility="visible",
                    )
                    uploads[index] = list(files or [])[:MAX_IMAGES]
                    if uploads[index]:
                        preview_cols = st.columns(len(uploads[index]))
                        for i, file in enumerate(uploads[index]):
                            with preview_cols[i]:
                                st.image(file, width=88, alt=file.name)

    submitted = st.button(
        "生成行程",
        type="primary",
        icon=":material/auto_awesome:",
        width="stretch",
    )

if submitted:
    users = [
        {
            "user_id": f"u{i + 1}",
            "text": texts[i].strip(),
            "image_paths": save_uploads(uploads[i], f"u{i + 1}"),
        }
        for i in range(num_users)
        if texts[i].strip()
    ]
    if not users:
        st.error("至少填写一位旅行者的偏好")
        st.stop()

    with st.status("正在生成行程", expanded=True) as status:
        st.write(":material/check_circle: 读取文字与图片偏好")
        st.write(":material/pending: 研究目的地与天气")
        st.write(":material/pending: 编排每日行程")
        started = time.time()
        try:
            result = run_trip(destination, days, users)
        except Exception as exc:
            status.update(label="生成失败", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            with st.expander("错误详情"):
                st.exception(exc)
            st.stop()
        elapsed = time.time() - started
        status.update(
            label=f"完成 · {elapsed:.1f}s",
            state="complete",
            expanded=False,
        )

    st.session_state["result"] = result
    st.session_state["inputs"] = {
        "destination": destination,
        "days": days,
        "users": users,
    }
    st.toast("行程已生成", icon=":material/check_circle:")

result = st.session_state.get("result")
if result:
    itinerary = result["itinerary"]
    profiles = result.get("profiles", [])
    metrics = st.columns(4)
    with metrics[0]:
        st.metric("耗时", f"{result['elapsed_seconds']}s", border=True, icon=":material/timer:")
    with metrics[1]:
        st.metric("人数", result["participants"], border=True, icon=":material/group:")
    with metrics[2]:
        st.metric("天数", len(itinerary.get("days", [])), border=True, icon=":material/calendar_month:")
    with metrics[3]:
        st.metric("模型", result["model"], border=True, icon=":material/memory:")

    st.space("small")
    tab_plan, tab_profiles, tab_debug = st.tabs([
        "行程",
        "旅行者画像",
        "运行详情",
    ])

    with tab_plan:
        if itinerary.get("summary"):
            st.markdown(f"#### {itinerary['summary']}")

        for day in itinerary.get("days", []):
            with st.container(border=True):
                st.markdown(f"### Day {day['day']} · {day.get('theme', '')}")
                for item in day.get("items", []):
                    with st.container(horizontal=True, vertical_alignment="top", gap="medium"):
                        st.markdown(f"**{item.get('time_slot', '')}**")
                        with st.container():
                            st.markdown(f"**{item.get('name', '')}**")
                            if item.get("location"):
                                st.caption(f":material/location_on: {item['location']}")
                            if item.get("why"):
                                st.markdown(item["why"])
                            tag_text = badges(item.get("tags", []), "blue")
                            weather = item.get("weather_dependency", "any")
                            weather_text = {
                                "indoor": ":green-badge[室内]",
                                "outdoor": ":orange-badge[室外]",
                                "any": "",
                            }.get(weather, "")
                            if tag_text or weather_text:
                                st.markdown(f"{weather_text} {tag_text}".strip())
                            if item.get("source"):
                                st.caption(f"来源：{item['source']}")

        if itinerary.get("tips"):
            with st.container(border=True):
                st.markdown("#### 实用提示")
                for tip in itinerary["tips"]:
                    st.markdown(f"- {tip}")
        if itinerary.get("assumptions"):
            st.warning("\n".join(f"- {a}" for a in itinerary["assumptions"]))

    with tab_profiles:
        if not profiles:
            st.info("这次没有拿到结构化画像，可以查看运行详情里的原始输出。")
        for profile in profiles:
            with st.container(border=True):
                head = st.columns([0.7, 0.3])
                with head[0]:
                    st.markdown(f"#### {profile.get('user_id', '')}")
                with head[1]:
                    st.badge(profile.get("pace", "适中"), icon=":material/speed:", color="green")
                st.markdown(profile.get("summary", ""))

                if profile.get("interests"):
                    st.markdown("**兴趣** " + badges(profile["interests"], "blue"))
                if profile.get("must_haves"):
                    st.markdown("**Must-have** " + badges(profile["must_haves"], "orange"))
                if profile.get("avoid"):
                    st.markdown("**想避开** " + badges(profile["avoid"], "red"))

                visual_summary = profile.get("visual_summary", "")
                if visual_summary:
                    st.markdown(
                        f":material/image: **图片线索** {visual_summary}"
                        + (f"（{profile['visual_mood']}）" if profile.get("visual_mood") else "")
                    )

                image_paths = result.get("images", {}).get(profile.get("user_id", ""), [])
                existing = [p for p in image_paths if Path(p).exists()]
                if existing:
                    image_cols = st.columns(min(len(existing), 3))
                    for i, path in enumerate(existing[:3]):
                        with image_cols[i]:
                            st.image(path, width="stretch", alt=f"{profile.get('user_id')} 的参考图")

        for user_id, error in result.get("visual_errors", {}).items():
            st.warning(f"{user_id} 的图片分析失败，已降级为文本：{error}")

    with tab_debug:
        trace = result.get("trace", [])
        if trace:
            st.dataframe(
                [
                    {
                        "Agent": item.get("agent", ""),
                        "阶段": item.get("task", ""),
                        "耗时 (s)": item.get("seconds", 0),
                    }
                    for item in trace
                ],
                hide_index=True,
                width="stretch",
            )
        with st.expander("原始 JSON"):
            st.json(result)

    st.space("small")
    saved_inputs = st.session_state.get("inputs", {})
    saved_destination = saved_inputs.get("destination", destination)
    saved_days = saved_inputs.get("days", days)
    download_cols = st.columns(2)
    with download_cols[0]:
        st.download_button(
            "下载 JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"travelcrew_{saved_destination}_{saved_days}d.json",
            mime="application/json",
            icon=":material/download:",
            width="stretch",
        )
    with download_cols[1]:
        st.download_button(
            "下载 Markdown",
            data=itinerary_markdown(result),
            file_name=f"travelcrew_{saved_destination}_{saved_days}d.md",
            mime="text/markdown",
            icon=":material/description:",
            width="stretch",
        )

    st.space("medium")
    with st.form("feedback", border=True):
        st.subheader("这次结果怎么样？", icon=":material/rate_review:")
        st.caption("反馈会随结果一起下载，用来决定下一轮先修什么。")
        score = st.slider("整体可用性", 1, 5, 3)
        personalization = st.slider("个性化程度", 1, 5, 3)
        executable = st.slider("可执行性", 1, 5, 3)
        problem = st.text_area(
            "最大问题",
            placeholder="太泛 / 太满 / 忽略人 / 编地点 / 太慢 / 其他",
            height=80,
        )
        feedback_submitted = st.form_submit_button(
            "保存反馈",
            icon=":material/save:",
            width="stretch",
        )

    if feedback_submitted:
        st.session_state["feedback"] = {
            "inputs": st.session_state.get("inputs"),
            "result": result,
            "rating": {
                "overall": score,
                "personalization": personalization,
                "executable": executable,
                "problem": problem.strip(),
            },
        }
        st.success("反馈已生成。")

    if st.session_state.get("feedback"):
        st.download_button(
            "下载反馈 JSON",
            data=json.dumps(st.session_state["feedback"], ensure_ascii=False, indent=2),
            file_name="travelcrew_feedback.json",
            mime="application/json",
            icon=":material/download:",
            width="stretch",
        )
