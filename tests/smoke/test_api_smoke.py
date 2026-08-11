from collections.abc import AsyncIterator

import httpx
import pytest

from agent_control_plane.api import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
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
