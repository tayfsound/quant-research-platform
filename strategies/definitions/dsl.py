"""Strateji tanım DSL'i."""

from pydantic import BaseModel


class StrategyDSL(BaseModel):
    name: str
    symbols: list[str]
    timeframe: str = "1h"
    entry_rules: list[str] = []
    exit_rules: list[str] = []
    risk_limits: dict[str, float] = {}
    agents: list[str] = []
