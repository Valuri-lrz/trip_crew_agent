"""行程数据模型"""
from pydantic import BaseModel, Field
from typing import List, Optional
from models.emotion_score import ExperienceEmotionScore


class ItineraryItem(BaseModel):
    """单个行程项"""
    time_slot: str = Field(description="时间段，如 09:00-11:00")
    activity: str = Field(description="活动名称")
    location: str = Field(description="地点")
    description: str = Field(default="", description="详细描述")
    emotion_score: Optional[ExperienceEmotionScore] = None
    target_users: List[str] = Field(default=[], description="主要满足谁")
    is_backup: bool = Field(default=False, description="是否为备选方案")
    backup_for: str = Field(default="", description="替代哪个活动")
    weather_dependency: str = Field(default="any", description="indoor/outdoor/any")


class DayPlan(BaseModel):
    """单日行程"""
    day: int
    date: str = ""
    items: List[ItineraryItem] = []
    emotion_curve: List[float] = Field(default=[], description="当日情感曲线")
    overall_intensity: str = Field(default="中", description="高/中/低")
    narrative_theme: str = Field(default="", description="当日叙事主题")


class Itinerary(BaseModel):
    """完整行程"""
    destination: str
    total_days: int
    days: List[DayPlan] = []
    participants: List[str] = []

    # 元信息
    generated_by: str = "TravelCrew"
    version: int = 1
    adjustment_history: List[str] = []