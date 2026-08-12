import pytest
from fastapi.testclient import TestClient

from agent_control_plane.api import create_app
from examples.refund_approval import DemoConfig, Principal, run_refund_approval_demo


@pytest.mark.smoke
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_event"),
    [
        ("approve", "approved", "approval.approved"),
        ("reject", "rejected", "approval.rejected"),
    ],
)
def test_refund_approval_demo_exercises_governance_and_audit(
    decision: str,
    expected_status: str,
    expected_event: str,
) -> None:
    with TestClient(create_app()) as client:
        result = run_refund_approval_demo(
            client,
            DemoConfig(
                agent_id=f"refund-demo-{decision}",
                operator=Principal("pilot-operator@example.test"),
                agent=Principal(f"refund-demo-{decision}"),
                reviewer=Principal("pilot-reviewer@example.test"),
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
