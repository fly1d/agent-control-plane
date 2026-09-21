import secrets
from collections.abc import AsyncIterator

import httpx
import pytest

from agent_control_plane.api import create_app
from agent_control_plane.auth import (
    AuthenticationConfig,
    Permission,
    StaticBearerAuthenticator,
    TokenPrincipalConfig,
    hash_bearer_token,
)
from agent_control_plane.store import InMemoryControlPlaneStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.smoke
@pytest.mark.anyio
async def test_service_is_live_and_ready(client: httpx.AsyncClient) -> None:
    live_response = await client.get("/health/live")
    ready_response = await client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "ok"
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ok"


@pytest.mark.smoke
@pytest.mark.anyio
async def test_readiness_fails_when_the_store_is_unavailable() -> None:
    class UnavailableStore(InMemoryControlPlaneStore):
        def is_ready(self) -> bool:
            return False

    transport = httpx.ASGITransport(app=create_app(UnavailableStore()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        live_response = await test_client.get("/health/live")
        ready_response = await test_client.get("/health/ready")

    assert live_response.status_code == 200
    assert ready_response.status_code == 503
    assert ready_response.json()["detail"]["code"] == "store_unavailable"


@pytest.mark.smoke
@pytest.mark.anyio
async def test_protected_api_enforces_credentials_permissions_and_actor_binding() -> None:
    reader_token = secrets.token_urlsafe(32)
    operator_token = secrets.token_urlsafe(32)
    authenticator = StaticBearerAuthenticator(
        AuthenticationConfig(
            principals=(
                TokenPrincipalConfig(
                    subject="reader@example.test",
                    token_sha256=hash_bearer_token(reader_token),
                    permissions=frozenset({Permission.AGENTS_READ}),
                ),
                TokenPrincipalConfig(
                    subject="operator@example.test",
                    token_sha256=hash_bearer_token(operator_token),
                    permissions=frozenset({Permission.ALL}),
                ),
            )
        )
    )
    transport = httpx.ASGITransport(app=create_app(authenticator=authenticator))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        assert (await test_client.get("/health/live")).status_code == 200

        missing = await test_client.get("/v1/agents")
        invalid = await test_client.get(
            "/v1/agents",
            headers={"Authorization": f"Bearer {secrets.token_urlsafe(32)}"},
        )
        wrong_scheme = await test_client.get(
            "/v1/agents",
            headers={"Authorization": "Basic ignored"},
        )
        assert missing.status_code == invalid.status_code == wrong_scheme.status_code == 401
        assert missing.json() == invalid.json() == wrong_scheme.json()
        for response in (missing, invalid, wrong_scheme):
            assert response.headers["www-authenticate"] == "Bearer"

        insufficient = await test_client.post(
            "/v1/agents",
            json=registration_payload(),
            headers={"Authorization": f"Bearer {reader_token}"},
        )
        assert insufficient.status_code == 403
        assert insufficient.json()["detail"]["code"] == "permission_denied"

        mismatch_payload = registration_payload()
        mismatch_payload["actor"] = "impersonated@example.test"
        mismatch = await test_client.post(
            "/v1/agents",
            json=mismatch_payload,
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert mismatch.status_code == 403
        assert mismatch.json()["detail"]["code"] == "actor_mismatch"

        registered = await test_client.post(
            "/v1/agents",
            json=registration_payload(),
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert registered.status_code == 201

        audit = await test_client.get(
            "/v1/audit-events",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert audit.json()["items"][0]["actor"] == "operator@example.test"


@pytest.mark.smoke
def test_every_versioned_operation_declares_bearer_authentication() -> None:
    schema = create_app().openapi()

    for path, operations in schema["paths"].items():
        for operation in operations.values():
            if path.startswith("/v1"):
                assert {"HTTPBearer": []} in operation["security"]
            else:
                assert "security" not in operation


@pytest.mark.smoke
@pytest.mark.anyio
async def test_agent_spec_contract_is_reachable(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/agent-specs/validate",
        json={
            "agent_id": "support-agent",
            "version": "1.0.0",
            "display_name": "Support Agent",
            "description": "Handles support requests with approval for risky actions.",
            "entrypoint": "https://agents.example.test/support",
            "capabilities": ["ticket.read", "ticket.reply"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "agent_id": "support-agent",
        "schema_version": "v1",
    }


@pytest.mark.smoke
@pytest.mark.anyio
async def test_invalid_contract_fails_closed(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/agent-specs/validate",
        json={"agent_id": "INVALID", "version": "latest"},
    )

    assert response.status_code == 422


def registration_payload() -> dict[str, object]:
    return {
        "spec": {
            "agent_id": "support-agent",
            "version": "1.0.0",
            "display_name": "Support Agent",
            "description": "Handles support requests with governed actions.",
            "entrypoint": "https://agents.example.test/support",
            "capabilities": ["ticket.read", "ticket.refund"],
        },
        "actor": "operator@example.test",
    }


@pytest.mark.smoke
@pytest.mark.anyio
async def test_registration_approval_and_audit_loop(client: httpx.AsyncClient) -> None:
    registration = await client.post("/v1/agents", json=registration_payload())
    assert registration.status_code == 201
    assert registration.json()["status"] == "registered"
    assert registration.json()["revision"] == 1
    assert (await client.get("/v1/agents/support-agent")).status_code == 200
    agents = await client.get("/v1/agents")
    assert [item["spec"]["agent_id"] for item in agents.json()] == ["support-agent"]

    activation = await client.patch(
        "/v1/agents/support-agent/status",
        json={
            "status": "active",
            "expected_revision": 1,
            "actor": "operator@example.test",
            "reason": "Readiness checks passed.",
        },
    )
    assert activation.status_code == 200
    assert activation.json()["revision"] == 2

    approval = await client.post(
        "/v1/approvals",
        json={
            "agent_id": "support-agent",
            "action": "ticket.refund",
            "risk": "high",
            "actor": "support-agent",
            "reason": "Refund exceeds the automatic threshold.",
        },
    )
    assert approval.status_code == 201
    request_id = approval.json()["request_id"]
    assert (await client.get(f"/v1/approvals/{request_id}")).status_code == 200

    queue = await client.get("/v1/approvals", params={"status": "pending"})
    assert queue.json()["count"] == 1

    decision = await client.post(
        f"/v1/approvals/{request_id}/decision",
        json={
            "decision": "approve",
            "actor": "reviewer@example.test",
            "reason": "Evidence verified.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    audit = await client.get("/v1/audit-events", params={"agent_id": "support-agent", "limit": 4})
    assert audit.status_code == 200
    assert [item["event_type"] for item in audit.json()["items"]] == [
        "approval.approved",
        "approval.requested",
        "agent.status_changed",
        "agent.registered",
    ]


@pytest.mark.smoke
@pytest.mark.anyio
async def test_governance_conflicts_fail_closed(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/agents", json=registration_payload())).status_code == 201

    duplicate = await client.post("/v1/agents", json=registration_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "agent_already_exists"

    missing_agent = await client.get("/v1/agents/missing-agent")
    assert missing_agent.status_code == 404
    assert missing_agent.json()["detail"]["code"] == "agent_not_found"

    stale = await client.patch(
        "/v1/agents/support-agent/status",
        json={
            "status": "active",
            "expected_revision": 2,
            "actor": "operator@example.test",
            "reason": "Stale client state.",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    inactive_approval = await client.post(
        "/v1/approvals",
        json={
            "agent_id": "support-agent",
            "action": "ticket.refund",
            "risk": "high",
            "actor": "support-agent",
            "reason": "The agent has not been activated.",
        },
    )
    assert inactive_approval.status_code == 409
    assert inactive_approval.json()["detail"]["code"] == "agent_not_active"

    missing_status = await client.patch(
        "/v1/agents/missing-agent/status",
        json={
            "status": "active",
            "expected_revision": 1,
            "actor": "operator@example.test",
            "reason": "Unknown agent.",
        },
    )
    assert missing_status.status_code == 404
    assert missing_status.json()["detail"]["code"] == "agent_not_found"

    activated = await client.patch(
        "/v1/agents/support-agent/status",
        json={
            "status": "active",
            "expected_revision": 1,
            "actor": "operator@example.test",
            "reason": "Readiness checks passed.",
        },
    )
    assert activated.status_code == 200

    invalid_transition = await client.patch(
        "/v1/agents/support-agent/status",
        json={
            "status": "active",
            "expected_revision": 2,
            "actor": "operator@example.test",
            "reason": "No-op transition.",
        },
    )
    assert invalid_transition.status_code == 409
    assert invalid_transition.json()["detail"]["code"] == "invalid_status_transition"

    unknown_agent = await client.post(
        "/v1/approvals",
        json={
            "agent_id": "missing-agent",
            "action": "ticket.refund",
            "risk": "high",
            "actor": "missing-agent",
            "reason": "This agent is not registered.",
        },
    )
    assert unknown_agent.status_code == 404
    assert unknown_agent.json()["detail"]["code"] == "agent_not_found"

    missing_request_id = "00000000-0000-0000-0000-000000000000"
    missing_approval = await client.get(f"/v1/approvals/{missing_request_id}")
    assert missing_approval.status_code == 404
    assert missing_approval.json()["detail"]["code"] == "approval_not_found"

    approval = await client.post(
        "/v1/approvals",
        json={
            "agent_id": "support-agent",
            "action": "ticket.refund",
            "risk": "high",
            "actor": "support-agent",
            "reason": "Refund exceeds the automatic threshold.",
        },
    )
    request_id = approval.json()["request_id"]
    decision_payload = {
        "decision": "reject",
        "actor": "reviewer@example.test",
        "reason": "Evidence is missing.",
    }
    assert (
        await client.post(f"/v1/approvals/{request_id}/decision", json=decision_payload)
    ).status_code == 200
    repeated = await client.post(f"/v1/approvals/{request_id}/decision", json=decision_payload)
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "approval_already_decided"

    missing_decision = await client.post(
        f"/v1/approvals/{missing_request_id}/decision", json=decision_payload
    )
    assert missing_decision.status_code == 404
    assert missing_decision.json()["detail"]["code"] == "approval_not_found"
