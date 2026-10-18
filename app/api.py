"""FastAPI 接口"""
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_travel_crew

app = FastAPI(
    title="TravelCrew API",
    description="多智能体博弈驱动的个性化旅游规划系统",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "TravelCrew"}


@app.post("/plan")
async def create_plan(
        destination: str = Form(...),
        days: int = Form(3),
        users: str = Form(...),  # JSON字符串
        images: List[UploadFile] = File(default=[]),
):
    """
    生成旅游规划

    Args:
        destination: 目的地
        days: 天数
        users: JSON字符串，如 [{"user_id":"u1","text":"..."}]
        images: 参考图片（可选）
    """
    user_inputs = json.loads(users)

    # 保存上传图片
    image_paths = []
    if images:
        os.makedirs("uploads", exist_ok=True)
        for img in images:
            path = f"uploads/{img.filename}"
            with open(path, "wb") as f:
                content = await img.read()
                f.write(content)
            image_paths.append(os.path.abspath(path))

    result = run_travel_crew(
        user_inputs=user_inputs,
        destination=destination,
        days=days,
        image_paths=image_paths if image_paths else None,
    )

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)