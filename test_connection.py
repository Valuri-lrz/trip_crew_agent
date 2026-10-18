"""验证 DeepSeek 多模态模型（统一模型）"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("MODEL_NAME", "deepseek-v4-flash-vision-exp")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

print(f"统一模型: {MODEL}")
print("=" * 50)

# 测试1：纯文本
print("\n1️⃣  纯文本能力")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "用一句话解释什么是Shapley值"}],
        max_tokens=200
    )
    print(f"✅ {resp.choices[0].message.content}")
except Exception as e:
    print(f"❌ {e}")

# 测试2：图片理解
print("\n2️⃣  图片理解能力")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/320px-Camponotus_flavomarginatus_ant.jpg"
                    }
                },
                {"type": "text", "text": "这张图里是什么？一句话。"}
            ]
        }],
        max_tokens=100
    )
    print(f"✅ {resp.choices[0].message.content}")
except Exception as e:
    print(f"❌ {e}")

# 测试3：本地图片（base64）
print("\n3️⃣  本地图片（Base64）")
import base64
test_img = "test_images/sample.jpg"
if os.path.exists(test_img):
    with open(test_img, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "这张图给人什么感觉？"}
                ]
            }],
            max_tokens=100
        )
        print(f"✅ {resp.choices[0].message.content}")
    except Exception as e:
        print(f"❌ {e}")
else:
    print(f"⚠️  未找到 {test_img}，跳过")

print("\n" + "=" * 50)
print("✅ 测试完成")