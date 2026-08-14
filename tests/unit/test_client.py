from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from agent_control_plane import ControlPlaneClient as PublicControlPlaneClient
from agent_control_plane.client import (
    ControlPlaneAPIError,
    ControlPlaneClient,
    ControlPlaneResponseError,
    ControlPlaneTransportError,
)
from agent_control_plane.models import (
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentSpec,
    AgentStatusUpdate,
    ApprovalDecision,
    ApprovalDecisionRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    RiskLevel,
)

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")


def spec() -> AgentSpec:
    return AgentSpec(
        agent_id="sdk-agent",
        version="1.0.0",
        display_name="SDK Agent",
        description="Exercises the typed Python client.",
        entrypoint="https://agents.example.test/sdk",
    )


def agent_payload(status: str = "registered", revision: int = 1) -> dict[str, object]:
    return {
        "spec": spec().model_dump(mode="json"),
        "status": status,
        "revision": revision,
        "registered_at": NOW,
        "updated_at": NOW,
    }


def approval_payload(status: str = "pending") -> dict[str, object]:
    payload: dict[str, object] = {
        "request_id": str(REQUEST_ID),
        "agent_id": "sdk-agent",
        "action": "ticket.refund",
        "risk": "high",
        "status": status,
        "requested_by": "sdk-agent",
        "request_reason": "Refund requires review.",
        "created_at": NOW,
        "decided_at": None,
        "decided_by": None,
        "decision_reason": None,
    }
    if status != "pending":
        payload.update(
            decided_at=NOW,
            decided_by="reviewer@example.test",
            decision_reason="Evidence verified.",
        )
    return payload


def test_client_runs_the_complete_typed_governance_flow() -> None:
    assert PublicControlPlaneClient is ControlPlaneClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/health/live" or path == "/health/ready":
            return httpx.Response(
                200,
                json={"status": "ok", "service": "agent-control-plane", "version": "0.1.0"},
            )
        if path == "/v1/agent-specs/validate":
            return httpx.Response(
                200,
                json={"valid": True, "agent_id": "sdk-agent", "schema_version": "v1"},
            )
        if path == "/v1/agents" and request.method == "POST":
            return httpx.Response(201, json=agent_payload())
        if path == "/v1/agents" and request.method == "GET":
            return httpx.Response(200, json=[agent_payload()])
        if path == "/v1/agents/sdk-agent" and request.method == "GET":
            return httpx.Response(200, json=agent_payload())
        if path == "/v1/agents/sdk-agent/status":
            return httpx.Response(200, json=agent_payload("active", 2))
        if path == "/v1/approvals" and request.method == "POST":
            return httpx.Response(201, json=approval_payload())
        if path == f"/v1/approvals/{REQUEST_ID}" and request.method == "GET":
            return httpx.Response(200, json=approval_payload())
        if path == "/v1/approvals" and request.method == "GET":
            return httpx.Response(200, json={"items": [approval_payload()], "count": 1})
        if path == f"/v1/approvals/{REQUEST_ID}/decision":
            return httpx.Response(200, json=approval_payload("approved"))
        if path == "/v1/audit-events":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "event_id": "00000000-0000-0000-0000-000000000002",
                            "event_type": "agent.registered",
                            "agent_id": "sdk-agent",
                            "actor": "operator@example.test",
                            "occurred_at": NOW,
                            "resource_id": "sdk-agent",
                            "summary": "Registered agent version 1.0.0",
                        }
                    ],
                    "count": 1,
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http_client = httpx.Client(
        base_url="https://control.example.test",
        headers={"Authorization": "Bearer secret-token"},
        transport=httpx.MockTransport(handler),
    )
    client = ControlPlaneClient(http_client=http_client)

    assert client.live().status == "ok"
    assert client.ready().status == "ok"
    assert client.validate_agent_spec(spec()).valid is True
    assert (
        client.register_agent(
            AgentRegistrationRequest(spec=spec(), actor="operator@example.test")
        ).revision
        == 1
    )
    assert client.list_agents()[0].spec.agent_id == "sdk-agent"
    assert client.get_agent("sdk-agent").revision == 1
    assert (
        client.update_agent_status(
            "sdk-agent",
            AgentStatusUpdate(
                status=AgentRuntimeStatus.ACTIVE,
                expected_revision=1,
                actor="operator@example.test",
                reason="Ready for traffic.",
            ),
        ).status
        is AgentRuntimeStatus.ACTIVE
    )
    approval = client.create_approval(
        ApprovalRequestCreate(
            agent_id="sdk-agent",
            action="ticket.refund",
            risk=RiskLevel.HIGH,
            actor="sdk-agent",
            reason="Refund requires review.",
        )
    )
    assert client.get_approval(approval.request_id).status is ApprovalStatus.PENDING
    assert (
        client.list_approvals(
            status=ApprovalStatus.PENDING,
            agent_id="sdk-agent",
        ).count
        == 1
    )
    assert (
        client.decide_approval(
            approval.request_id,
            ApprovalDecisionRequest(
                decision=ApprovalDecision.APPROVE,
                actor="reviewer@example.test",
                reason="Evidence verified.",
            ),
        ).status
        is ApprovalStatus.APPROVED
    )
    assert client.list_audit_events(agent_id="sdk-agent", limit=20).count == 1

    assert all(request.headers["authorization"] == "Bearer secret-token" for request in requests)
    approval_query = next(
        request.url.params
        for request in requests
        if request.url.path == "/v1/approvals" and request.method == "GET"
    )
    assert dict(approval_query) == {"status": "pending", "agent_id": "sdk-agent"}
    assert dict(requests[-1].url.params) == {"limit": "20", "agent_id": "sdk-agent"}
    client.close()
    assert http_client.is_closed is False
    http_client.close()


def test_client_adds_bearer_auth_and_owns_its_internal_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.closed = False

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = ControlPlaneClient(
        "https://control.example.test/",
        bearer_token="secret-token",
        timeout=5,
    )

    assert captured == {
        "base_url": "https://control.example.test",
        "headers": {"Authorization": "Bearer secret-token"},
        "timeout": 5,
    }
    client.close()
    assert client._http.closed is True


def test_client_rejects_ambiguous_authentication_configuration() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    with pytest.raises(ValueError, match="cannot be combined"):
        ControlPlaneClient(bearer_token="secret", http_client=http_client)
    http_client.close()


def test_structured_and_unstructured_api_errors_are_stable() -> None:
    responses = iter(
        (
            httpx.Response(
                409,
                json={"detail": {"code": "revision_conflict", "message": "stale revision"}},
            ),
            httpx.Response(502, text="proxy failed"),
            httpx.Response(307, headers={"Location": "https://unexpected.example.test"}),
        )
    )
    http_client = httpx.Client(
        base_url="https://control.example.test",
        transport=httpx.MockTransport(lambda _: next(responses)),
    )
    client = ControlPlaneClient(http_client=http_client)

    with pytest.raises(ControlPlaneAPIError) as structured:
        client.get_agent("sdk-agent")
    assert structured.value.status_code == 409
    assert structured.value.code == "revision_conflict"
    assert structured.value.message == "stale revision"

    with pytest.raises(ControlPlaneAPIError) as fallback:
        client.get_agent("sdk-agent")
    assert fallback.value.status_code == 502
    assert fallback.value.code == "http_error"
    assert fallback.value.message == "control plane returned HTTP 502"

    with pytest.raises(ControlPlaneAPIError) as redirect:
        client.get_agent("sdk-agent")
    assert redirect.value.status_code == 307
    assert redirect.value.code == "http_error"
    http_client.close()


def test_transport_and_invalid_response_failures_are_distinct() -> None:
    def transport_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport_client = httpx.Client(
        base_url="https://control.example.test",
        transport=httpx.MockTransport(transport_failure),
    )
    with pytest.raises(ControlPlaneTransportError, match="request failed"):
        ControlPlaneClient(http_client=transport_client).get_agent("sdk-agent")
    transport_client.close()

    invalid_client = httpx.Client(
        base_url="https://control.example.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": True})),
    )
    with pytest.raises(ControlPlaneResponseError, match="invalid response"):
        ControlPlaneClient(http_client=invalid_client).get_agent("sdk-agent")
    invalid_client.close()
