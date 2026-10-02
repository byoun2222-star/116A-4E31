# Copyright (c) tree and fruits. PoC only — PHASE 2A workflow CLI.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent_framework import FileCheckpointStorage, WorkflowBuilder

PHASE2A_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2A_ROOT))

from db import publishing_db as db  # noqa: E402
from workflow.phase2a_steps import (  # noqa: E402
    ApprovalResponse,
    CostGuardExecutor,
    FinalizeExecutor,
    OwnerApprovalExecutor,
    Phase2AMessage,
    RegisterProvidersExecutor,
    RouterDecisionExecutor,
    SyncCysStateExecutor,
)

WORKFLOW_NAME = "maf-publishing-poc-phase2a"
CHECKPOINT_DIR = PHASE2A_ROOT / "data" / "checkpoints"
ALLOWED_CHECKPOINT_TYPES = [
    "workflow.phase2a_steps:Phase2AMessage",
    "workflow.phase2a_steps:ApprovalRequest",
    "workflow.phase2a_steps:ApprovalResponse",
]


def make_storage() -> FileCheckpointStorage:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return FileCheckpointStorage(str(CHECKPOINT_DIR), allowed_checkpoint_types=ALLOWED_CHECKPOINT_TYPES)


def build_workflow(checkpoint_storage: FileCheckpointStorage):
    sync = SyncCysStateExecutor()
    register = RegisterProvidersExecutor()
    router = RouterDecisionExecutor()
    cost_guard = CostGuardExecutor()
    approval = OwnerApprovalExecutor()
    finalize = FinalizeExecutor()

    return (
        WorkflowBuilder(name=WORKFLOW_NAME, start_executor=sync, checkpoint_storage=checkpoint_storage)
        .add_edge(sync, register)
        .add_edge(register, router)
        .add_edge(router, cost_guard)
        .add_edge(cost_guard, approval)
        .add_edge(approval, finalize)
        .build()
    )


def _report(result) -> dict:
    outputs = result.get_outputs()
    pending = result.get_request_info_events()
    pending_info = [{"request_id": e.request_id, "data": vars(e.data)} for e in pending]
    return {"outputs": [str(o) for o in outputs], "pending_requests": pending_info}


async def cmd_start(args: argparse.Namespace) -> None:
    storage = make_storage()
    workflow = build_workflow(storage)
    db.ensure_book(args.book_id, args.title, actor="cli")
    workflow_run_id = f"run-{args.book_id}"
    db.create_workflow_run(workflow_run_id, args.book_id, WORKFLOW_NAME, actor="cli")
    mock_health = json.loads(args.mock_health) if args.mock_health else None
    message = Phase2AMessage(
        book_id=args.book_id, title=args.title, workflow_run_id=workflow_run_id,
        mock_provider_health=mock_health, requires_paid_api=args.requires_paid_api,
    )
    result = await workflow.run(message)
    report = _report(result)
    report["db_status"] = db.get_book_status(args.book_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def cmd_resume(args: argparse.Namespace) -> None:
    storage = make_storage()
    latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
    if latest is None:
        print(json.dumps({"error": "no checkpoint found for workflow " + WORKFLOW_NAME}))
        return
    workflow = build_workflow(storage)
    result = await workflow.run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=storage)
    report = _report(result)
    report["resumed_from_checkpoint_id"] = latest.checkpoint_id
    report["db_status"] = db.get_book_status(args.book_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def cmd_approve(args: argparse.Namespace) -> None:
    storage = make_storage()
    latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
    if latest is None:
        print(json.dumps({"error": "no checkpoint found for workflow " + WORKFLOW_NAME}))
        return
    workflow = build_workflow(storage)
    request_id = f"approval2a-{args.book_id}"
    response = ApprovalResponse(approved=(args.decision == "approve"), approved_by=args.approved_by)
    result = await workflow.run(
        checkpoint_id=latest.checkpoint_id, responses={request_id: response}, checkpoint_storage=storage,
    )
    report = _report(result)
    report["resumed_from_checkpoint_id"] = latest.checkpoint_id
    report["db_status"] = db.get_book_status(args.book_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="PHASE 2A workflow CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--book-id", required=True)
    p_start.add_argument("--title", required=True)
    p_start.add_argument("--mock-health", default=None, help='JSON e.g. \'{"CLAUDE":"RATE_LIMITED","CODEX":"AVAILABLE","GEMINI":"UNKNOWN"}\'')
    p_start.add_argument("--requires-paid-api", action="store_true")
    p_start.set_defaults(func=cmd_start)

    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--book-id", required=True)
    p_resume.set_defaults(func=cmd_resume)

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--book-id", required=True)
    p_approve.add_argument("--decision", choices=["approve", "reject"], required=True)
    p_approve.add_argument("--approved-by", default="owner")
    p_approve.set_defaults(func=cmd_approve)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
