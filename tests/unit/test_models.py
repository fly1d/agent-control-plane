import pytest
from pydantic import ValidationError

from agent_control_plane import __main__ as entrypoint
from agent_control_plane.models import AgentSpec


def valid_spec() -> dict[str, object]:
    return {
        "agent_id": "support-agent",
        "version": "1.0.0",
        "display_name": "Support Agent",
        "description": "Handles support requests with human approval for risky actions.",
        "entrypoint": "https://agents.example.test/support",
        "capabilities": ["ticket.read", "ticket.reply"],
    }


def test_agent_spec_accepts_a_minimal_valid_contract() -> None:
    spec = AgentSpec.model_validate(valid_spec())

    assert spec.schema_version == "v1"
    assert spec.agent_id == "support-agent"
    assert spec.capabilities == ("ticket.read", "ticket.reply")


@pytest.mark.parametrize("agent_id", ["UPPERCASE", "a", "starts_with_underscore"])
def test_agent_spec_rejects_invalid_agent_ids(agent_id: str) -> None:
    payload = valid_spec()
    payload["agent_id"] = agent_id

    with pytest.raises(ValidationError):
        AgentSpec.model_validate(payload)


def test_agent_spec_rejects_duplicate_capabilities() -> None:
    payload = valid_spec()
    payload["capabilities"] = ["ticket.read", "ticket.read"]

    with pytest.raises(ValidationError, match="capabilities must be unique"):
        AgentSpec.model_validate(payload)


def test_agent_spec_rejects_unknown_fields() -> None:
    payload = valid_spec()
    payload["unreviewed_setting"] = True

    with pytest.raises(ValidationError):
        AgentSpec.model_validate(payload)


def test_agent_spec_rejects_empty_capabilities() -> None:
    payload = valid_spec()
    payload["capabilities"] = ["ticket.read", "  "]

    with pytest.raises(ValidationError, match="cannot contain empty"):
        AgentSpec.model_validate(payload)


def test_command_entrypoint_runs_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation: dict[str, object] = {}

    def fake_run(app: str, *, host: str, port: int, factory: bool) -> None:
        invocation.update(app=app, host=host, port=port, factory=factory)

    monkeypatch.setattr(entrypoint.uvicorn, "run", fake_run)

    entrypoint.main()

    assert invocation == {
        "app": "agent_control_plane.api:create_app_from_environment",
        "host": "0.0.0.0",
        "port": 8000,
        "factory": True,
    }
