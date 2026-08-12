# Agent Control Plane

Agent Control Plane is a reliability and governance layer for production AI agents. The
project starts with stable contracts, observability-friendly APIs, policy enforcement,
evaluation, approvals, and rollback. Durable workflows and long-term memory are added only
when validated customer scenarios require them.

## Product boundary

This project is intended to sit above existing agents rather than force teams to rewrite them.
The planned integration surfaces are HTTP, OpenTelemetry, MCP/A2A adapters, and a small SDK.

Initial scope:

- versioned `AgentSpec` contracts;
- health and readiness contracts;
- trace and replay foundations;
- policy checks and human approval;
- evaluation gates and version rollback.

Not in the initial scope:

- a new LLM or general-purpose agent framework;
- autonomous production prompt mutation;
- a replacement for Temporal, Mem0, LangSmith, or DSPy;
- Kubernetes before workload and isolation requirements justify it.

## First validation scenario

The initial commercial hypothesis is governed refund approval for an existing customer-support
agent. The repository includes a reproducible end-to-end demo, a bounded paid-pilot offer, and a
customer-discovery guide:

- [`examples/refund_approval.py`](examples/refund_approval.py)
- [`docs/PAID_PILOT.md`](docs/PAID_PILOT.md)
- [`docs/CUSTOMER_DISCOVERY.md`](docs/CUSTOMER_DISCOVERY.md)

These are validation materials, not a production-readiness claim. Major provider integrations
remain deferred until customer evidence identifies a concrete blocker.

## Quick start

Requirements: Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
make install
make check
make run
```

Without `ACP_DATABASE_URL`, the service uses its process-local in-memory adapter. The API is
then available at `http://127.0.0.1:8000`. Important endpoints:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/agent-specs/validate`
- `POST /v1/agents` and `PATCH /v1/agents/{agent_id}/status`
- `GET` and `POST /v1/approvals`
- `POST /v1/approvals/{request_id}/decision`
- `GET /v1/audit-events`
- `GET /docs`

Persistent local execution starts PostgreSQL, runs migrations, and then starts the API:

```bash
docker compose up --build
```

For an externally managed PostgreSQL database, set a `postgresql+psycopg://` URL and migrate
before starting the service:

```bash
export ACP_DATABASE_URL='postgresql+psycopg://user:password@host/database'
make migrate
make run
```

## Python SDK

The package includes a typed synchronous client for the complete current governance workflow:

```python
from agent_control_plane import ControlPlaneClient
from agent_control_plane.models import (
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentSpec,
    AgentStatusUpdate,
)

with ControlPlaneClient(
    "http://127.0.0.1:8000",
    bearer_token="replace-with-a-secret-token",  # Omit unless the deployment requires it.
) as control_plane:
    registered = control_plane.register_agent(
        AgentRegistrationRequest(
            spec=AgentSpec(
                agent_id="support-agent",
                version="1.0.0",
                display_name="Support Agent",
                description="Handles support cases with governed actions.",
                entrypoint="https://agents.example.test/support",
            ),
            actor="operator@example.test",
        )
    )
    active = control_plane.update_agent_status(
        registered.spec.agent_id,
        AgentStatusUpdate(
            status=AgentRuntimeStatus.ACTIVE,
            expected_revision=registered.revision,
            actor="operator@example.test",
            reason="Readiness checks passed.",
        ),
    )
```

Methods return the same Pydantic models used by the versioned API contract. Structured API
failures raise `ControlPlaneAPIError`; connection failures and invalid server responses use
separate exception types. The client deliberately does not retry writes. Until server-side
idempotency is available, inspect current state after an ambiguous timeout before deciding
whether an operation is safe to send again.

## Delivery policy

Every change merged to `main` goes through a pull request, review, and required fast checks.
Experiments remain cheap on feature branches. Riskier changes require additional evidence;
long-running checks run after merge and on a schedule. See
[`docs/QUALITY_GATES.md`](docs/QUALITY_GATES.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Project status

The first governance loop is available: register an agent, activate or pause it with optimistic
revision checks, request and decide human approval, and inspect the resulting audit events.
Public API compatibility starts with the `v1` schema.

PostgreSQL is available as the durable system of record. Agent changes, approval changes, and
their audit events commit atomically; a database trigger rejects audit updates, deletion, and
truncation. Readiness fails when the configured database is unavailable or not migrated.

The in-memory adapter remains available for development and evaluation only. A typed Python SDK
is available for integration. Authenticated actor identity, request idempotency, backup
automation, and durable workflows remain planned.

## License

Licensed under the [MIT License](LICENSE).
