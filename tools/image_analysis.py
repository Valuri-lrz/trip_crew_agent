"""多模态图片分析工具 - 统一使用 DeepSeek 多模态模型"""
import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv
from crewai.tools import tool

load_dotenv()

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1"
        )
    return _client


def get_model() -> str:
    """统一模型名"""
    return os.getenv("MODEL_NAME", "deepseek-v4.1-flash")


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_mime_type(image_path: str) -> str:
    """根据文件头判断实际格式（DeepSeek按内容判断，不看文件名）"""
    with open(image_path, "rb") as f:
        header = f.read(16)
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif header[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return "image/webp"
    elif header[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    return "image/jpeg"


def call_model_with_image(image_path: str, prompt: str) -> str:
    """调用多模态模型（图片+文本）"""
    client = get_client()
    b64 = encode_image_to_base64(image_path)
    mime = detect_mime_type(image_path)

    response = client.chat.completions.create(
        model=get_model(),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }],
        temperature=0.3,
        max_tokens=2048
    )
    return response.choices[0].message.content


def call_model_text_only(prompt: str) -> str:
    """调用同一模型（纯文本，不传图片）"""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048
    )
    return response.choices[0].message.content


IMAGE_ANALYSIS_PROMPT = """你是一位视觉心理学家。请分析这张图片，推理用户为什么会被它吸引。

⚠️ 不要描述图片内容，而是推理"吸引力背后的心理需求"。

分析维度：
1. 空间感：开阔/封闭 → 推断自由度需求
2. 人物关系：独处/群体 → 推断社交偏好
3. 色调温度：暖色/冷色 → 推断情绪需求
4. 场景秩序：精致/粗犷 → 推断审美调性
5. 时间暗示：黄昏/正午/深夜 → 推断生活节奏偏好

严格按以下JSON格式输出：
{
    "implicit_preferences": [
        {"content": "偏好描述", "confidence": 0.85, "reasoning": "推理过程"}
    ],
    "emotional_tone": "逃离型/探索型/治愈型/社交型/成就型",
    "aesthetic_style": "极简/烟火气/精致/野性/温馨",
    "social_preference": "独处/小群体/热闹",
    "overall_reasoning": "综合分析"
}"""


@tool("analyze_reference_image")
def analyze_reference_image(image_path: str) -> str:
    """
    分析用户上传的参考图片，推理其隐性偏好。
    输入：图片文件的绝对路径
    输出：隐性偏好推理结果（JSON）
    """
    if not os.path.exists(image_path):
        return json.dumps({"error": f"文件不存在: {image_path}"}, ensure_ascii=False)
    try:
        return call_model_with_image(image_path, IMAGE_ANALYSIS_PROMPT)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("analyze_multiple_images")
def analyze_multiple_images(image_paths: str) -> str:
    """
    分析多张参考图片，提取共性偏好模式。
    输入：逗号分隔的图片路径
    输出：综合偏好分析（JSON）
    """
    paths = [p.strip() for p in image_paths.split(",") if p.strip()]
    if not paths:
        return json.dumps({"error": "未提供有效图片路径"}, ensure_ascii=False)

    # 逐张简要分析（同一模型）
    briefs = []
    for i, path in enumerate(paths):
        if not os.path.exists(path):
            continue
        try:
            brief = call_model_with_image(
                path,
                "用50字以内概括这张图反映的审美偏好和情绪需求。只输出概括。"
            )
            briefs.append(f"图片{i + 1}: {brief}")
        except Exception:
            continue

    if not briefs:
        return json.dumps({"error": "所有图片分析失败"}, ensure_ascii=False)

    # 综合分析（同一模型，纯文本调用）
    combined_prompt = f"""以下是{len(briefs)}张参考图片的单独分析：

{chr(10).join(briefs)}

请综合分析共性，推理用户深层偏好模式。

输出JSON：
{{
    "common_theme": "共同主题",
    "implicit_preferences": [
        {{"content": "...", "confidence": 0.85, "reasoning": "..."}}
    ],
    "emotional_tone": "...",
    "aesthetic_style": "...",
    "social_preference": "...",
    "deep_insight": "用户内心可能在寻找什么"
}}"""

    try:
        return call_model_text_only(combined_prompt)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)