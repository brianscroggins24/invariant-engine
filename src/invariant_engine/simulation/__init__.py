"""Evaluate caller-ordered synthetic buy scenarios in memory."""

from .evaluator import evaluate_scenario
from .models import (
    CutoffKnowledge,
    CutoffLegResult,
    EventResult,
    HypotheticalPayout,
    LegState,
    PayoutResult,
    ScenarioEvent,
    ScenarioResult,
    ScenarioSpec,
    ScenarioValidationError,
)

__all__ = [
    "CutoffKnowledge",
    "CutoffLegResult",
    "EventResult",
    "HypotheticalPayout",
    "LegState",
    "PayoutResult",
    "ScenarioEvent",
    "ScenarioResult",
    "ScenarioSpec",
    "ScenarioValidationError",
    "evaluate_scenario",
]
