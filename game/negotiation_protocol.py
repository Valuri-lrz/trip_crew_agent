"""协商协议"""
from typing import List, Dict
from dataclasses import dataclass, field


@dataclass
class NegotiationState:
    """协商状态"""
    current_round: int = 0
    max_rounds: int = 5
    status: str = "ongoing"  # ongoing / converged / deadlock
    history: List[dict] = field(default_factory=list)


class NegotiationProtocol:
    """
    3轮协商协议：提案 → 让步 → 补偿

    Round 1 - 提案：每个用户代理提出最理想方案
    Round 2 - 让步：根据Shapley值确定让步优先级
    Round 3 - 补偿：对让步最多者设计补偿
    """

    def __init__(self, max_rounds: int = 5, fairness_threshold: float = 0.75):
        self.max_rounds = max_rounds
        self.fairness_threshold = fairness_threshold
        self.state = NegotiationState(max_rounds=max_rounds)

    def should_continue(self, fairness_index: float) -> bool:
        """判断是否需要继续协商"""
        if fairness_index >= self.fairness_threshold:
            self.state.status = "converged"
            return False
        if self.state.current_round >= self.max_rounds:
            self.state.status = "deadlock"
            return False
        return True

    def get_concession_priority(
            self, shapley_values: Dict[str, float]
    ) -> List[str]:
        """
        确定让步优先级
        Shapley值低的用户优先让步（其偏好更容易在其他地方被满足）
        """
        sorted_users = sorted(shapley_values.items(), key=lambda x: x[1])
        return [user for user, _ in sorted_users]

    def record_round(self, round_data: dict):
        """记录一轮协商"""
        self.state.current_round += 1
        self.state.history.append(round_data)

    def get_protocol_prompt(self, shapley_values: Dict[str, float]) -> str:
        """生成协商协议的prompt（给Agent用）"""
        concession_order = self.get_concession_priority(shapley_values)

        return f"""
【协商协议】

当前状态：第 {self.state.current_round + 1} 轮 / 最多 {self.max_rounds} 轮
公平性阈值：{self.fairness_threshold}

Shapley值（话语权）：
{self._format_shapley(shapley_values)}

让步优先级（从先到后）：
{self._format_order(concession_order)}

协商规则：
1. must_have 偏好不可让步
2. Shapley值低的用户优先在非核心偏好上让步
3. 让步最多的用户必须获得次日补偿
4. 每人每天至少1个高满意度活动（效用 > 0.6）
5. 情感曲线需有节奏：不能连续安排高强度活动

终止条件：
- 公平性指数 ≥ {self.fairness_threshold} → 协商成功
- 达到最大轮次 → 取当前最优解
"""

    def _format_shapley(self, values: Dict[str, float]) -> str:
        lines = []
        for user, val in sorted(values.items(), key=lambda x: -x[1]):
            bar = "█" * int(val * 20)
            lines.append(f"  {user}: {val:.3f} {bar}")
        return "\n".join(lines)

    def _format_order(self, order: List[str]) -> str:
        return " → ".join([f"{i + 1}.{u}" for i, u in enumerate(order)])