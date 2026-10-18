# TravelCrew B 档 MVP（CrewAI + 多模态）

目标：用 CrewAI 跑通“文字 + 图片偏好 → 可执行行程”的端到端体验，先看使用感，再决定是否加博弈。

## 范围

做：

- 文本 + 参考图片，1～5 位旅行者
- 3 个 Agent：偏好分析师、目的地研究员、行程规划师
- DeepSeek Vision 图片分析（每人最多 3 张，8MB/张）
- 搜索 / 高德天气工具
- JSON 输出 + Pydantic guardrail（人数、活动数、天数、非空白天）
- Streamlit 页面 + 主题 + 耗时 trace + 反馈下载

不做：

- 每用户独立 Agent / 多轮协商
- Shapley / 公平性 / 补偿
- FastAPI / 任务队列
- 记忆 / RAG

## 目录

```text
app/
  mvp_crew.py          # 3 Agent + 3 Task + guardrails
  multimodal.py        # DeepSeek Vision 图片分析
  settings.py          # 模型/Key 单一配置
  crewai_bootstrap.py  # 修复 CrewAI 在 Windows 的路径探测卡死
  streamlit_mvp.py     # 前端
tools/
  search_tool.py       # Tavily SDK / REST 回退
  weather_tool.py      # 高德天气 + timeout + 错误状态
test/
  test_mvp_contracts.py
.streamlit/config.toml # 主题
```

已删除旧版 `agents/`、`game/`、`models/`、`evaluation/`、`app/main.py`、
`app/api.py`、`app/streamlit.py`、`tools/image_analysis.py`、
`tools/shapley_calculator.py`、`test_connection.py`、`_probe.py`、
旧的 `requirements` 和 `config.yaml`。这些文件都在 git 历史里，需要时可恢复。

## 环境

当前机器上 **系统 Python 3.13** 已带 `crewai==1.15.28` 和 `streamlit==1.66`：

```bash
py -3.13 -m streamlit run app\streamlit_mvp.py --server.port 8502
```

命令行冒烟：

```bash
py -3.13 -m app.mvp_crew
```

如需独立环境：

```bash
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-mvp.txt
.venv\Scripts\streamlit.exe run app\streamlit_mvp.py
```

`.env` 至少需要：

```text
DEEPSEEK_API_KEY=...
MODEL_NAME=deepseek-flash
TAVILY_API_KEY=...
AMAP_API_KEY=...
```

> 如果 `import crewai` 卡住，是 CrewAI 1.15 在探测 `~/.config` / `%LOCALAPPDATA%`。
> `app/crewai_bootstrap.py` 已把 settings/DB 路径重定向到 `.data/crewai`，
> 必须在 `import crewai` 之前调用。`app/mvp_crew.py` 已经处理。

## 实测（2026-10-18）

| 场景 | 耗时 | 结果 |
|---|---:|---|
| 1 人 / 1 天 / 大理 + 1 张海边图 | 24.2s | 图片线索进入画像；JSON 有效；4 个活动 |
| 1 人 / 1 天 / 大理，纯文本 | 22.5s | JSON 有效；5 个活动 |
| 2 人 / 2 天 / 大理，纯文本 | 22.5s | 2 份画像；7 个活动；两人偏好均被覆盖 |

对比：开启 DeepSeek thinking 时同样 3 个 Agent 要 40～100s，且偶尔把 JSON 截断。
现在统一 `thinking=disabled`，延迟明显下降。

工具状态：

- Tavily：当前 `TAVILY_API_KEY` 返回 401，已降级为“搜索不可用，需核实”
- 高德：当前 `AMAP_API_KEY` 返回 `INVALID_USER_KEY`，已降级为“天气需核实”
- 两者都没有让流程崩，也没有让模型假装知道天气/搜索事实

> 当前结果是在两个工具 key 都失效时跑出来的，属于“下限”。换有效 key 后
> 再用同一组场景跑一遍，才能判断工具的实际提升。

## 使用感评分

用同一组 5 个场景，找 3～5 个人试：

| 场景 | 总耗时 | JSON 有效 | 个性化 1-5 | 可执行 1-5 | 愿意再用 1-5 | 最大问题 |
|---|---:|---|---:|---:|---:|---|
| 单人轻松 3 天 | | | | | | |
| 情侣冲突 3 天 | | | | | | |
| 3 个朋友 4 天 | | | | | | |
| 带娃家庭 3 天 | | | | | | |
| 雨天/高温 2 天 | | | | | | |

决策门槛：

- 耗时 > 120s：先优化模型/`max_iter`/工具缓存，不加博弈
- 输出很泛：先补搜索/天气/目的地知识
- 多人冲突被忽略：再加每用户画像 + 公平分配
- 行程太满：改 Planner 约束
- 编造地点：加来源 + guardrail

## 已知限制

- Profiler 一次输出所有用户画像；多人冲突只做“提示”，没有真正协商
- Researcher 依赖工具 key；无 key 时只能靠模型知识，必须标注“需核实”
- 同步请求，一次只能跑一个行程；上 API 时需要后台任务
- 没有缓存，重复场景会重复计费
- 图片分析失败会降级为文本，不阻塞行程
