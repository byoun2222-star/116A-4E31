# Copyright (c) tree and fruits. PoC only — PHASE 2A Multi-Provider Router (MOCK / decision-only).
"""Router selects a provider based on HEALTH state only, in PHASE 2A.

★PHASE 2A scope discipline (owner §4, §7, §24): this module makes a DECISION and returns it.
It never calls Claude/Codex/Gemini, never calls agent_framework's Agent/model-client classes,
never sends a `cys` command to actually assign work. "Routing" in Phase 2A means: given a
health snapshot, which provider WOULD be chosen — nothing is dispatched.

No provider is hard-coded as preferred for any task type (owner §7 explicit instruction —
"코딩은 무조건 Codex" 같은 규칙 없음). The only ordering rule is health-based availability;
ties are broken by a stable, arbitrary-but-deterministic provider order so results are
reproducible for testing, not because one provider is judged "better".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


# Health states usable to route work TO a provider. UNKNOWN and UNAVAILABLE are explicitly
# excluded — owner §5: "UNKNOWN을 정상으로 간주하지 않는다."
ROUTABLE_HEALTH = {ProviderHealth.AVAILABLE, ProviderHealth.DEGRADED}

# Stable tie-break order ONLY (not a quality/capability ranking — owner §7).
STABLE_ORDER = ["CLAUDE", "CODEX", "GEMINI"]


@dataclass
class ProviderState:
    name: str  # "CLAUDE" | "CODEX" | "GEMINI"
    health: ProviderHealth
    usage_pct_5h: float | None = None  # None = not observed (do not assume 0)
    usage_reliability: str = "UNKNOWN"  # e.g. "hook-verified" | "heuristic" | "UNKNOWN"


@dataclass
class RoutingDecision:
    selected_provider: str | None
    reason: str
    candidates_considered: list[str]
    excluded: dict[str, str]  # provider -> exclusion reason


def route(states: list[ProviderState]) -> RoutingDecision:
    """Pure function: given provider health states, decide which provider a NEW task-boundary
    task WOULD go to. Does not dispatch anything. Health-based only — no task-type preference
    table exists in Phase 2A (owner §7)."""
    by_name = {s.name: s for s in states}
    excluded: dict[str, str] = {}
    candidates: list[str] = []

    for name in STABLE_ORDER:
        state = by_name.get(name)
        if state is None:
            excluded[name] = "not present in registry"
            continue
        if state.health in ROUTABLE_HEALTH:
            candidates.append(name)
        else:
            excluded[name] = f"health={state.health.value}"

    if not candidates:
        return RoutingDecision(
            selected_provider=None,
            reason="no provider currently routable (all RATE_LIMITED/UNAVAILABLE/UNKNOWN)",
            candidates_considered=[],
            excluded=excluded,
        )

    selected = candidates[0]  # first in STABLE_ORDER among routable ones — tie-break only
    return RoutingDecision(
        selected_provider=selected,
        reason=f"first routable provider in stable order (health={by_name[selected].health.value})",
        candidates_considered=candidates,
        excluded=excluded,
    )
