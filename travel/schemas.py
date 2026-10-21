"""契约：全项目共享的数据形状。改这里 = 改所有层。

隐性偏好分三层，都用同一种方式落地：
  审美   Taste   —— 和目的地/POI 用同一组维度，能算相似度
  情绪   Emotion —— 6 种需求的强度，决定"排多满、留多少白"
  社交   Social  —— 独处还是结伴、看还是参与、怕不怕人多
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Taste(BaseModel):
    """5 维审美空间，[-1, 1]，0 = 无所谓。用户、目的地、POI 共用。

      quiet_lively   -1 安静      +1 热闹
      nature_urban   -1 自然野趣  +1 城市人造
      minimal_ornate -1 极简      +1 繁复
      warm_cool      -1 温暖      +1 冷冽
      classic_trendy -1 经典老派  +1 新潮
    """

    quiet_lively: float = 0.0
    nature_urban: float = 0.0
    minimal_ornate: float = 0.0
    warm_cool: float = 0.0
    classic_trendy: float = 0.0

    def vec(self) -> list[float]:
        return list(self.model_dump().values())


class Emotion(BaseModel):
    """情绪需求强度，[0, 1]。0 = 不需要，1 = 非常需要。"""

    restore: float = Field(default=0.4, description="想松下来、恢复")
    novelty: float = Field(default=0.4, description="想找点新鲜的")
    control: float = Field(default=0.5, description="希望被安排清楚 / 喜欢自由")
    belong: float = Field(default=0.4, description="想和人在一起")
    beauty: float = Field(default=0.4, description="想看好看的东西")
    achieve: float = Field(default=0.3, description="想走点难的、有点成就")

    def vec(self) -> list[float]:
        return list(self.model_dump().values())


class Social(BaseModel):
    """社交风格。"""

    together: float = Field(default=0.2, ge=-1, le=1, description="-1 独处 +1 结伴")
    participate: float = Field(default=0.0, ge=-1, le=1, description="-1 看 +1 动手参与")
    crowd_tolerance: float = Field(default=0.65, ge=0, le=1, description="0 怕人多 1 喜欢人气")


class Profile(BaseModel):
    """一个人。tags 是给人看的三个词，三层向量是给算法用的。"""

    user_id: str
    name: str = ""
    tags: list[str] = Field(default_factory=list, description="3 个感受词")
    summary: str = Field(default="", description="一句话：他想要的是一次什么样的旅行")
    aesthetic: Taste = Field(default_factory=Taste)
    emotion: Emotion = Field(default_factory=Emotion)
    social: Social = Field(default_factory=Social)
    interests: list[str] = Field(default_factory=list)
    must_haves: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list, description="依据，给用户看")
    scene: dict = Field(default_factory=dict, description="图片拆出来的场景维度")
    far: bool = Field(default=False, description="国内库对不上的地方")
    place_guess: str = Field(default="", description="认出来的地名")


class Destination(BaseModel):
    id: str
    name: str
    region: str = ""
    adcode: str = ""
    tags: list[str] = Field(default_factory=list)
    blurb: str = ""
    best_days: int = 3
    taste: Taste = Field(default_factory=Taste)


class POI(BaseModel):
    id: str
    dest_id: str
    name: str
    category: str
    tags: list[str] = Field(default_factory=list)
    taste: Taste = Field(default_factory=Taste)
    crowd: float = Field(default=0.5, ge=0, le=1)
    duration_min: int = 120
    cost: float = 0.0
    facts: dict = Field(default_factory=dict, description="高德核实过的评分/营业时间/地址")
    indoor: bool = False
    best_slot: Literal["morning", "afternoon", "evening", "any"] = "any"
    lat: float = 0.0
    lng: float = 0.0
    note: str = ""


class PlanItem(BaseModel):
    poi_id: str
    name: str
    slot: str
    duration_min: int
    utility: float = 0.0
    why: str = ""
    highlight: str = Field(default="", description="一句话亮点，攻略感")
    tip: str = Field(default="", description="避坑 / 注意")
    cost: float = 0.0
    start_time: str = Field(default="", description="几点到")
    travel_min: int = Field(default=0, description="从上一个点过来要多久")
    facts: dict = Field(default_factory=dict, description="高德核实过的事实")
    indoor: bool = False


class DayPlan(BaseModel):
    day: int
    items: list[PlanItem] = Field(default_factory=list)
    total_min: int = 0
    weather: str = ""
    note: str = ""
    story: str = Field(default="", description="这一天怎么过，一段话")


class Itinerary(BaseModel):
    dest: Destination
    days: list[DayPlan] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    ledger: list[dict] = Field(default_factory=list, description="让步账本")


class DestinationCard(BaseModel):
    id: str
    name: str
    region: str = ""
    tags: list[str] = Field(default_factory=list)
    reason: str = ""
    score: float = 0.0
    days: int = 3


class Reply(BaseModel):
    """一次对话的返回。前端只认这几个字段。"""

    session_id: str
    stage: int
    text: str = ""
    cards: list[DestinationCard] = Field(default_factory=list)
    itinerary: Itinerary | None = None
    profiles: list[Profile] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    mode: str = "demo"


class Session(BaseModel):
    id: str
    stage: int = 0
    text_input: str = ""
    people: int = 1
    days: int = 3
    month: str = ""
    profiles: list[Profile] = Field(default_factory=list)
    cards: list[DestinationCard] = Field(default_factory=list)
    dest: str = ""
    itinerary: Itinerary | None = None
    answers: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    pois: list[POI] = Field(default_factory=list, description="这次行程的点位池")
    dest_name: str = Field(default="", description="选定的城市")
    domestic_forced: bool = Field(default=False, description="用户说就在国内找")
