"""Run a governed customer-support refund scenario against a control-plane API."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Literal
from uuid import uuid4

import httpx

QueryParameter = str | int | float | bool | None


@dataclass(frozen=True)
class Principal:
    actor: str
    token: str | None = None


@dataclass(frozen=True)
class DemoConfig:
    agent_id: str
    operator: Principal
    agent: Principal
    reviewer: Principal
    decision: Literal["approve", "reject"] = "approve"


@dataclass(frozen=True)
class DemoResult:
    agent_id: str
    approval_request_id: str
    decision: str
    pending_request_observed: bool
    audit_event_types: tuple[str, ...]


def _headers(principal: Principal) -> dict[str, str] | None:
    if principal.token is None:
        return None
    return {"Authorization": f"Bearer {principal.token}"}


def _call(
    client: httpx.Client,
    method: str,
    path: str,
    principal: Principal,
    *,
    payload: dict[str, object] | None = None,
    params: dict[str, QueryParameter] | None = None,
) -> dict[str, object]:
    response = client.request(
        method,
        path,
        json=payload,
        params=params,
        headers=_headers(principal),
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise RuntimeError(
            f"control-plane request failed: {method} {path} returned "
            f"HTTP {response.status_code}: {response.text}"
        ) from error
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"control-plane request returned a non-object body: {method} {path}")
    return body


def run_refund_approval_demo(client: httpx.Client, config: DemoConfig) -> DemoResult:
    """Register an agent, govern one refund, and verify its audit evidence."""

    registered = _call(
        client,
        "POST",
        "/v1/agents",
        config.operator,
        payload={
            "spec": {
                "agent_id": config.agent_id,
                "version": "1.0.0",
                "display_name": "Support Refund Agent",
                "description": "Proposes customer refunds with approval for high-risk amounts.",
                "entrypoint": "https://agents.example.test/support-refund",
                "capabilities": ["ticket.read", "refund.propose"],
                "default_risk": "medium",
            },
            "actor": config.operator.actor,
        },
    )
    if registered.get("status") != "registered" or registered.get("revision") != 1:
        raise RuntimeError("registered agent did not satisfy the expected lifecycle contract")

    activated = _call(
        client,
        "PATCH",
        f"/v1/agents/{config.agent_id}/status",
        config.operator,
        payload={
            "status": "active",
            "expected_revision": 1,
            "actor": config.operator.actor,
            "reason": "Pilot readiness checks passed in the isolated environment.",
        },
    )
    if activated.get("status") != "active":
        raise RuntimeError("agent activation was not reflected by the control plane")

    approval = _call(
        client,
        "POST",
        "/v1/approvals",
        config.agent,
        payload={
            "agent_id": config.agent_id,
            "action": "refund.issue",
            "risk": "high",
            "actor": config.agent.actor,
            "reason": "Order DEMO-1042 requests a CNY 1,280 refund above the CNY 500 limit.",
        },
    )
    request_id = approval.get("request_id")
    if not isinstance(request_id, str) or approval.get("status") != "pending":
        raise RuntimeError("approval request did not enter the pending queue")

    queue = _call(
        client,
        "GET",
        "/v1/approvals",
        config.reviewer,
        params={"status": "pending", "agent_id": config.agent_id},
    )
    queue_items = queue.get("items")
    pending_request_observed = isinstance(queue_items, list) and any(
        isinstance(item, dict) and item.get("request_id") == request_id for item in queue_items
    )
    if not pending_request_observed:
        raise RuntimeError("new approval request was not visible in the pending queue")

    decision_reason = (
        "Order ownership and refund evidence were verified for the pilot."
        if config.decision == "approve"
        else "Required order evidence is incomplete; refund must remain blocked."
    )
    decided = _call(
        client,
        "POST",
        f"/v1/approvals/{request_id}/decision",
        config.reviewer,
        payload={
            "decision": config.decision,
            "actor": config.reviewer.actor,
            "reason": decision_reason,
        },
    )
    expected_status = "approved" if config.decision == "approve" else "rejected"
    if decided.get("status") != expected_status:
        raise RuntimeError("approval decision was not reflected by the control plane")

    audit = _call(
        client,
        "GET",
        "/v1/audit-events",
        config.reviewer,
        params={"agent_id": config.agent_id, "limit": 4},
    )
    audit_items = audit.get("items")
    if not isinstance(audit_items, list):
        raise RuntimeError("audit response did not contain an event list")
    event_types = tuple(
        str(item["event_type"])
        for item in audit_items
        if isinstance(item, dict) and "event_type" in item
    )
    expected_events = (
        f"approval.{expected_status}",
        "approval.requested",
        "agent.status_changed",
        "agent.registered",
    )
    if event_types != expected_events:
        raise RuntimeError(f"unexpected audit sequence: {event_types!r}")

    return DemoResult(
        agent_id=config.agent_id,
        approval_request_id=request_id,
        decision=expected_status,
        pending_request_observed=pending_request_observed,
        audit_event_types=event_types,
    )


def _environment_token(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else os.getenv("ACP_DEMO_TOKEN")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("ACP_DEMO_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--agent-id", default=f"support-refund-{uuid4().hex[:12]}")
    parser.add_argument("--decision", choices=("approve", "reject"), default="approve")
    parser.add_argument(
        "--operator-actor",
        default=os.getenv("ACP_DEMO_OPERATOR_ACTOR", "pilot-operator@example.test"),
    )
    parser.add_argument(
        "--agent-actor",
        default=os.getenv("ACP_DEMO_AGENT_ACTOR", "support-refund-agent"),
    )
    parser.add_argument(
        "--reviewer-actor",
        default=os.getenv("ACP_DEMO_REVIEWER_ACTOR", "pilot-reviewer@example.test"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = DemoConfig(
        agent_id=args.agent_id,
        operator=Principal(args.operator_actor, _environment_token("ACP_DEMO_OPERATOR_TOKEN")),
        agent=Principal(args.agent_actor, _environment_token("ACP_DEMO_AGENT_TOKEN")),
        reviewer=Principal(args.reviewer_actor, _environment_token("ACP_DEMO_REVIEWER_TOKEN")),
        decision=args.decision,
    )
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        result = run_refund_approval_demo(client, config)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
