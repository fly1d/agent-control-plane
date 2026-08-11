# Roadmap

Roadmap items advance only when tied to a validated user problem and an acceptance metric.

## Foundation

- Versioned AgentSpec and event contracts.
- API health, readiness, and failure conventions.
- Pull request governance and automated quality gates.

## Reliability gateway

- Framework-neutral trace ingestion.
- Run replay and failure classification.
- Tool-call schema validation and risk policy.
- Human approval queue and immutable audit record.
- Offline evaluation datasets and version promotion gates.

## Durable operations

- PostgreSQL system of record.
- Durable workflow adapter for cross-day tasks.
- Idempotency, retry, compensation, and dead-letter handling.
- Backup, restore, tenant isolation, and disaster exercises.

## Governed evolution

- Memory adapter with provenance, consent, TTL, and deletion.
- Prompt candidate generation behind offline evaluation.
- Canary promotion and automatic rollback.
