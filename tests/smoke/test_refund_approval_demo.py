import secrets

import pytest
from fastapi.testclient import TestClient

from agent_control_plane.api import create_app
from agent_control_plane.auth import (
    AuthenticationConfig,
    Permission,
    StaticBearerAuthenticator,
    TokenPrincipalConfig,
    hash_bearer_token,
)
from examples.refund_approval import DemoConfig, Principal, run_refund_approval_demo


@pytest.mark.smoke
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_event"),
    [
        ("approve", "approved", "approval.approved"),
        ("reject", "rejected", "approval.rejected"),
    ],
)
def test_refund_approval_demo_exercises_governance_and_audit(
    authenticated: bool,
    decision: str,
    expected_status: str,
    expected_event: str,
) -> None:
    operator = Principal("pilot-operator@example.test", secrets.token_urlsafe(32))
    agent = Principal(f"refund-demo-{decision}", secrets.token_urlsafe(32))
    reviewer = Principal("pilot-reviewer@example.test", secrets.token_urlsafe(32))
    authenticator = None
    if authenticated:
        roles = (
            (operator, {Permission.AGENTS_WRITE}),
            (agent, {Permission.APPROVALS_REQUEST}),
            (
                reviewer,
                {Permission.APPROVALS_READ, Permission.APPROVALS_DECIDE, Permission.AUDIT_READ},
            ),
        )
        authenticator = StaticBearerAuthenticator(
            AuthenticationConfig(
                principals=tuple(
                    TokenPrincipalConfig(
                        subject=principal.actor,
                        token_sha256=hash_bearer_token(principal.token),
                        permissions=frozenset(permissions),
                    )
                    for principal, permissions in roles
                    if principal.token is not None
                )
            )
        )
    else:
        operator = Principal(operator.actor)
        agent = Principal(agent.actor)
        reviewer = Principal(reviewer.actor)

    with TestClient(create_app(authenticator=authenticator)) as client:
        result = run_refund_approval_demo(
            client,
            DemoConfig(
                agent_id=f"refund-demo-{decision}",
                operator=operator,
                agent=agent,
                reviewer=reviewer,
                decision=decision,
            ),
        )

    assert result.decision == expected_status
    assert result.pending_request_observed is True
    assert result.audit_event_types == (
        expected_event,
        "approval.requested",
        "agent.status_changed",
        "agent.registered",
    )
