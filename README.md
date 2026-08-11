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

## Quick start

Requirements: Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
make install
make check
make run
```

The API is then available at `http://127.0.0.1:8000`. Important endpoints:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/agent-specs/validate`
- `GET /docs`

Container execution:

```bash
docker compose up --build
```

## Delivery policy

Every change merged to `main` goes through a pull request, review, and required fast checks.
Experiments remain cheap on feature branches. Riskier changes require additional evidence;
long-running checks run after merge and on a schedule. See
[`docs/QUALITY_GATES.md`](docs/QUALITY_GATES.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Project status

The repository is in foundation stage. Public API compatibility starts with the `v1` schema;
runtime, storage, and workflow adapters are not yet production-ready.

## License

No license has been selected yet. Publishing this repository does not by itself grant reuse
rights. Choose an open-source or commercial license before making the GitHub repository public.
