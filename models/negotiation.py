"""博弈协商数据模型"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class NegotiationRound(BaseModel):
    """单轮博弈记录"""
    round_number: int
    phase: str = Field(description="proposal/concession/compensation")
    proposals: Dict[str, str] = Field(default={}, description="各用户提案")
    concessions: Dict[str, str] = Field(default={}, description="各用户让步")
    shapley_values: Dict[str, float] = Field(default={})
    status: str = Field(default="ongoing", description="ongoing/converged/deadlock")
    notes: str = ""


class CompensationPlan(BaseModel):
    """补偿方案"""
    user_id: str
    reason: str = Field(description="为什么需要补偿")
    compensation: str = Field(description="补偿内容")
    scheduled_day: int = Field(description="安排在第几天")


class NegotiationResult(BaseModel):
    """博弈最终结果"""
    # 行程
    itinerary: List[dict] = []

    # 博弈过程
    rounds: List[NegotiationRound] = []
    total_rounds: int = 0

    # 公平性指标
    shapley_values: Dict[str, float] = {}
    satisfaction_scores: Dict[str, float] = {}
    fairness_index: float = Field(default=0.0, ge=0, le=1)
    pareto_optimal: bool = False

    # 补偿
    compensation_plans: List[CompensationPlan] = []

    # 情感曲线
    emotion_curves: Dict[str, List[float]] = {}

    # 元信息
    destination: str = ""
    total_days: int = 0
    participants: List[str] = []