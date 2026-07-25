"""
Reinforcement Learning portları ve şemaları.
"""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


class RLAgentType(StrEnum):
    PPO = "ppo"
    A2C = "a2c"
    DQN = "dqn"
    SAC = "sac"
    TD3 = "td3"

class ActionType(StrEnum):
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"
    HOLD = "hold"

class RLState(BaseModel):
    symbol: str
    feature_vector: dict[str, float]
    position: dict[str, Any] | None = None
    portfolio: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

class RLAction(BaseModel):
    action_type: ActionType
    size: float = 0.0
    leverage: float = 1.0
    confidence: float = 0.0

class RLReward(BaseModel):
    trade_id: UUID | None = None
    pnl: float
    sharpe_contribution: float
    drawdown_penalty: float
    risk_adjusted_return: float
    total: float

class RLTrajectory(BaseModel):
    id: UUID
    agent_id: UUID
    agent_type: RLAgentType
    states: list[RLState]
    actions: list[RLAction]
    rewards: list[RLReward]
    total_pnl: float
    total_reward: float
    start_time: datetime
    end_time: datetime

class LearningUpdateEvent(BaseModel):
    agent_id: UUID
    trajectory_id: UUID
    new_weights: dict[str, Any] | None = None
    updated_metrics: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

class RLAgentMetadata(BaseModel):
    id: UUID
    agent_type: RLAgentType
    version: str
    hyperparameters: dict[str, Any]
    checkpoint_path: str | None = None
    trained_at: datetime | None = None
    total_episodes: int = 0
    cumulative_reward: float = 0.0

class LearningPort(Protocol):
    @abstractmethod
    async def create_agent(self, agent_type: RLAgentType, hyperparameters: dict[str, Any]) -> RLAgentMetadata: ...

    @abstractmethod
    async def select_action(self, agent_id: UUID, state: RLState) -> RLAction: ...

    @abstractmethod
    async def store_experience(self, trajectory: RLTrajectory) -> None: ...

    @abstractmethod
    async def update_policy(self, agent_id: UUID) -> LearningUpdateEvent: ...

    @abstractmethod
    async def analyze_trade(self, trajectory: RLTrajectory) -> dict[str, Any]: ...

    @abstractmethod
    async def get_agent(self, agent_id: UUID) -> RLAgentMetadata: ...
