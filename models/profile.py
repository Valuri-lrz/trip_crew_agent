"""用户画像数据模型"""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class InputModality(Enum):
    TEXT = "text"
    IMAGE = "image"


class EmotionalTone(Enum):
    ESCAPE = "逃离型"
    ADVENTURE = "探索型"
    HEALING = "治愈型"
    SOCIAL = "社交型"
    ACHIEVEMENT = "成就型"


class AestheticStyle(Enum):
    MINIMAL = "极简"
    RUSTIC = "烟火气"
    REFINED = "精致"
    WILD = "野性"
    COZY = "温馨"


class ImplicitPreference(BaseModel):
    """隐性偏好"""
    content: str = Field(description="偏好内容")
    confidence: float = Field(ge=0, le=1, description="置信度")
    reasoning_chain: str = Field(description="推理链")
    source_modality: InputModality = Field(description="来源模态")
    source_detail: str = Field(default="", description="来源细节")


class ExplicitPreference(BaseModel):
    """显式偏好"""
    content: str = Field(description="偏好内容")
    category: str = Field(description="类别：目的地/活动/美食/住宿")
    weight: float = Field(ge=0, le=1, description="权重")
    is_must_have: bool = Field(default=False, description="是否硬性要求")


class UserProfile(BaseModel):
    """增强用户画像"""
    user_id: str
    user_name: str = ""

    # 显式偏好
    explicit_preferences: List[ExplicitPreference] = []

    # 隐性偏好
    implicit_preferences: List[ImplicitPreference] = []

    # 情感与风格
    emotional_tone: EmotionalTone = EmotionalTone.HEALING
    aesthetic_style: AestheticStyle = AestheticStyle.COZY
    social_preference: str = Field(default="小群体", description="独处/小群体/热闹")
    energy_level: str = Field(default="中", description="高/中/低")
    decision_fatigue: str = Field(default="中", description="高(需安排)/中/低(喜自由)")

    # 博弈用
    preference_vector: List[float] = Field(default=[], description="向量化偏好")

    # 元信息
    raw_text_input: str = ""
    image_count: int = 0