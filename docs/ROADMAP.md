# Roadmap

Roadmap items advance only when tied to a validated user problem and an acceptance metric.

## Foundation

- [x] Versioned AgentSpec and event contracts.
- [x] API health, readiness, and failure conventions.
- [x] Pull request governance and automated quality gates.

## Reliability gateway

- Framework-neutral trace ingestion.
- Run replay and failure classification.
- Tool-call schema validation and risk policy.
- [x] In-memory human approval queue and append-only audit contract.
- [x] PostgreSQL-backed approval and immutable audit persistence.
- Offline evaluation datasets and version promotion gates.

## Durable operations

- [x] PostgreSQL system of record with reversible migrations.
- Durable workflow adapter for cross-day tasks.
- Idempotency, retry, compensation, and dead-letter handling.
- Backup, restore, tenant isolation, and disaster exercises.

## Governed evolution

- Memory adapter with provenance, consent, TTL, and deletion.
- Prompt candidate generation behind offline evaluation.
- Canary promotion and automatic rollback.
