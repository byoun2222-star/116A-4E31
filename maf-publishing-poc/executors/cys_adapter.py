# Copyright (c) tree and fruits. PoC only.
"""cys CLI subprocess adapter — DEFERRED, not wired into workflow.py in Phase 1.

Per the Phase 1 task instruction item (4): "CYSJavis 연결은 아직 하지 말고 EPUB_BUILD 등은
mock Function Executor로 대체한다." This file exists only to match the folder layout
proposed in CYSJAVIS-MAF-PUBLISHING-INTEGRATION-PHASE0.md §18-20; none of its functions are
imported or called anywhere in Phase 1's workflow.py or tests/. It is intentionally inert.

Real wiring (subprocess.run(["cys", "send", "--to", "worker", ...]) + polling `cys status --json`)
is Phase 2+ work and requires separate owner approval before any cys command is executed from
inside a MAF executor, per the task's "기존 CYSJavis 절대 불가침" constraint for this phase.
"""
from __future__ import annotations

raise NotImplementedError(
    "cys_adapter is a Phase-2+ placeholder. Do not import or call this module in Phase 1 — "
    "no MAF executor may invoke the cys CLI yet."
)
