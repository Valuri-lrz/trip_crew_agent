"""
TravelCrew - 网页端
启动命令：streamlit run app/streamlit_app.py
"""
import streamlit as st
import json
import os
import sys
import time

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# ===== 页面配置 =====
st.set_page_config(
    page_title="TravelCrew - AI旅游规划",
    page_icon="🧳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== 自定义样式 =====
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .result-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #667eea;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ===== 标题 =====
st.markdown('<p class="main-header">🧳 TravelCrew</p>', unsafe_allow_html=True)
st.caption("多智能体博弈驱动的个性化旅游规划 | DeepSeek + CrewAI")

# ===== 侧边栏 =====
with st.sidebar:
    st.header("⚙️ 旅行配置")

    destination = st.text_input("📍 目的地", value="大理", placeholder="输入目的地")
    days = st.slider("📅 旅行天数", 1, 7, 3)

    st.divider()
    st.header("👥 旅行者")
    num_users = st.slider("出行人数", 1, 5, 2)

    st.divider()
    st.markdown("""
    ### 💡 使用提示
    - 描述越具体，推荐越精准
    - 上传图片可推理隐性偏好
    - 多人出行会触发博弈协商
    """)

# ===== 主区域：输入 =====
st.header("📝 输入你的偏好")

# 用户输入区
user_inputs = []
cols = st.columns(min(num_users, 3))

for i in range(num_users):
    with cols[i % 3]:
        st.subheader(f"👤 旅行者 {i+1}")

        text = st.text_area(
            "描述你的偏好",
            placeholder="例：我喜欢安静的地方，想看海，不想太商业化...",
            height=120,
            key=f"user_text_{i}"
        )

        if text.strip():
            user_inputs.append({
                "user_id": f"user_{i+1}",
                "text": text.strip()
            })

# 图片上传
st.divider()
st.header("📸 上传参考图片（可选）")
st.caption("上传你喜欢的风景/美食/氛围图片，AI会推理你的隐性偏好")

uploaded_files = st.file_uploader(
    "选择图片",
    type=["jpg", "jpeg", "png", "webp", "gif"],
    accept_multiple_files=True
)

if uploaded_files:
    img_cols = st.columns(min(len(uploaded_files), 4))
    for i, file in enumerate(uploaded_files):
        with img_cols[i % 4]:
            st.image(file, caption=file.name, use_container_width=True)

# ===== 执行按钮 =====
st.divider()

col_btn, col_status = st.columns([1, 3])

with col_btn:
    run_button = st.button(
        "🚀 开始规划",
        type="primary",
        use_container_width=True,
        disabled=(len(user_inputs) == 0)
    )

with col_status:
    if len(user_inputs) == 0:
        st.warning("⚠️ 请至少填写一位旅行者的偏好描述")

# ===== 执行逻辑 =====
if run_button and user_inputs:

    # 显示进度
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    with st.spinner(""):
        progress_placeholder.progress(10, text="📸 阶段1: 多模态隐性偏好推理中...")

        # 保存上传的图片
        image_paths = []
        if uploaded_files:
            os.makedirs("temp", exist_ok=True)
            for f in uploaded_files:
                path = f"temp/{f.name}"
                with open(path, "wb") as out:
                    out.write(f.getbuffer())
                image_paths.append(os.path.abspath(path))

        progress_placeholder.progress(30, text="🔍 阶段2: 目的地深度研究中...")

        try:
            from main import run_travel_crew

            progress_placeholder.progress(50, text="⚖️ 阶段3: Shapley值博弈协商中...")

            result = run_travel_crew(
                user_inputs=user_inputs,
                destination=destination,
                days=days,
                image_paths=image_paths if image_paths else None,
            )

            progress_placeholder.progress(90, text="🔄 阶段4: 动态调度与备选方案...")

            # 保存结果
            st.session_state["result"] = result
            st.session_state["has_result"] = True

            progress_placeholder.progress(100, text="✅ 规划完成！")
            time.sleep(0.5)
            progress_placeholder.empty()

        except Exception as e:
            progress_placeholder.empty()
            st.error(f"❌ 执行出错: {str(e)}")
            st.exception(e)

# ===== 结果展示 =====
if st.session_state.get("has_result"):
    result = st.session_state["result"]

    st.divider()
    st.header("📋 规划结果")

    # 指标卡片
    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("⏱️ 耗时", f"{result['elapsed_time']}s")
    with metric_cols[1]:
        st.metric("👥 参与人数", f"{result['participants']}人")
    with metric_cols[2]:
        st.metric("📅 天数", f"{result['days']}天")
    with metric_cols[3]:
        st.metric("🤖 模型", result.get('model', 'DeepSeek'))

    st.divider()

    # 结果内容（尝试解析JSON美化展示）
    result_text = result["result"]

    # 尝试解析为JSON
    try:
        # 尝试从结果中提取JSON
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            result_json = json.loads(result_text[json_start:json_end])

            # 分Tab展示
            tab1, tab2, tab3, tab4 = st.tabs([
                "🗓️ 行程", "⚖️ 博弈过程", "📊 公平性报告", "🔄 备选方案"
            ])

            with tab1:
                if "itinerary" in result_json:
                    for day_plan in result_json["itinerary"]:
                        st.subheader(f"Day {day_plan.get('day', '?')} - {day_plan.get('theme', '')}")
                        for item in day_plan.get("items", []):
                            with st.container():
                                st.markdown(f"""
                                **{item.get('time_slot', '')}** | {item.get('activity', '')}  
                                📍 {item.get('location', '')} | 
                                👤 满足: {', '.join(item.get('target_users', []))}
                                """)
                else:
                    st.json(result_json)

            with tab2:
                if "negotiation_rounds" in result_json:
                    for rnd in result_json["negotiation_rounds"]:
                        st.markdown(f"**Round {rnd.get('round', '?')}** - {rnd.get('phase', '')}")
                        st.write(rnd.get("details", ""))
                if "shapley_values" in result_json:
                    st.subheader("Shapley值（话语权）")
                    st.json(result_json["shapley_values"])

            with tab3:
                if "satisfaction_scores" in result_json:
                    st.subheader("满意度评分")
                    for user, score in result_json["satisfaction_scores"].items():
                        st.progress(score, text=f"{user}: {score:.2f}")

                    st.metric("公平性指数", f"{result_json.get('fairness_index', 0):.4f}")

                if "compensation_plans" in result_json:
                    st.subheader("补偿方案")
                    for plan in result_json["compensation_plans"]:
                        st.info(f"👤 {plan.get('user_id', '')} → {plan.get('compensation', '')}")

            with tab4:
                if "backup_plans" in result_json:
                    for bp in result_json["backup_plans"]:
                        st.markdown(f"""
                        **原活动**: {bp.get('original_activity', '')}  
                        **触发条件**: {bp.get('trigger', '')}  
                        **备选**: {bp.get('backup_activity', '')}
                        """)
                else:
                    st.info("暂无备选方案数据")
        else:
            # 无法解析JSON，直接展示
            st.markdown(result_text)

    except (json.JSONDecodeError, KeyError):
        # JSON解析失败，直接展示原文
        st.markdown("### 原始输出")
        st.code(result_text, language="markdown")

    # 下载按钮
    st.divider()
    st.download_button(
        label="📥 下载完整结果（JSON）",
        data=json.dumps(result, ensure_ascii=False, indent=2),
        file_name=f"travel_plan_{destination}_{days}days.json",
        mime="application/json"
    )