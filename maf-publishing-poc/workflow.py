# Copyright (c) tree and fruits. PoC only.
"""MAF-PUBLISHING-POC workflow entrypoint.

MANUSCRIPT_RECEIVED -> EDITING -> OWNER_APPROVAL(HITL) -> EPUB_BUILD -> EPUB_VALIDATE -> REVIEW
-> READY_FOR_PUBLICATION

Uses ONLY: WorkflowBuilder / Executor / FunctionExecutor / WorkflowContext.state /
FileCheckpointStorage / ctx.request_info (HITL). Never imports agent_framework's
Agent or any model-client submodule (openai/anthropic/foundry/gemini/ollama/...).
No network call, no API key, no Azure/Foundry resource — CLI-local only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent_framework import FileCheckpointStorage, WorkflowBuilder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from executors import db_writer as db
from executors.steps import (
    ApprovalResponse,
    BookMessage,
    EditingExecutor,
    EpubBuildExecutor,
    EpubValidateExecutor,
    ManuscriptReceivedExecutor,
    OwnerApprovalExecutor,
    ReadyForPublicationExecutor,
    ReviewExecutor,
)

WORKFLOW_NAME = "maf-publishing-poc"
CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"

# FileCheckpointStorage's restricted unpickler blocks unknown application types by default
# (agent_framework security note, PHASE0 §4) — our own dataclasses must be explicitly allowlisted.
ALLOWED_CHECKPOINT_TYPES = [
    "executors.steps:BookMessage",
    "executors.steps:ApprovalRequest",
    "executors.steps:ApprovalResponse",
]


def make_storage() -> FileCheckpointStorage:
    return FileCheckpointStorage(str(CHECKPOINT_DIR), allowed_checkpoint_types=ALLOWED_CHECKPOINT_TYPES)


def build_workflow(checkpoint_storage: FileCheckpointStorage):
    manuscript_received = ManuscriptReceivedExecutor()
    editing = EditingExecutor()
    owner_approval = OwnerApprovalExecutor()
    epub_build = EpubBuildExecutor()
    epub_validate = EpubValidateExecutor()
    review = ReviewExecutor()
    ready = ReadyForPublicationExecutor()

    return (
        WorkflowBuilder(
            name=WORKFLOW_NAME,
            start_executor=manuscript_received,
            checkpoint_storage=checkpoint_storage,
        )
        .add_edge(manuscript_received, editing)
        .add_edge(editing, owner_approval)
        .add_edge(owner_approval, epub_build)
        .add_edge(epub_build, epub_validate)
        .add_edge(epub_validate, review)
        .add_edge(review, ready)
        .build()
    )


def _report(result) -> dict:
    outputs = result.get_outputs()
    pending = result.get_request_info_events()
    pending_info = [{"request_id": e.request_id, "data": vars(e.data)} for e in pending]
    return {
        "outputs": [str(o) for o in outputs],
        "pending_requests": pending_info,
        "db_status": None,  # filled by caller once book_id known
    }


async def cmd_start(args: argparse.Namespace) -> None:
    storage = make_storage()
    workflow = build_workflow(storage)
    message = BookMessage(
        book_id=args.book_id,
        title=args.title,
        fail_at=args.fail_at,
        editing_delay_seconds=args.editing_delay,
    )
    result = await workflow.run(message)
    report = _report(result)
    report["db_status"] = db.get_status(args.book_id)
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
    report["db_status"] = db.get_status(args.book_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


async def cmd_approve(args: argparse.Namespace) -> None:
    storage = make_storage()
    latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
    if latest is None:
        print(json.dumps({"error": "no checkpoint found for workflow " + WORKFLOW_NAME}))
        return
    workflow = build_workflow(storage)
    request_id = f"approval-{args.book_id}"
    response = ApprovalResponse(approved=(args.decision == "approve"), approved_by=args.approved_by)
    result = await workflow.run(
        checkpoint_id=latest.checkpoint_id,
        responses={request_id: response},
        checkpoint_storage=storage,
    )
    report = _report(result)
    report["resumed_from_checkpoint_id"] = latest.checkpoint_id
    report["db_status"] = db.get_status(args.book_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="MAF-PUBLISHING-POC workflow CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--book-id", required=True)
    p_start.add_argument("--title", required=True)
    p_start.add_argument("--fail-at", default=None)
    p_start.add_argument("--editing-delay", type=float, default=0.0)
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
