# Changelog

All notable changes will be documented in this file. The project follows semantic versioning
for public contracts once they are declared stable.

## [Unreleased]

### Added

- Initial FastAPI service with liveness, readiness, and `AgentSpec` validation.
- Unit, smoke, lint, type, dependency audit, and container build automation.
- Risk-based review and delivery policy.
- Agent registration and lifecycle status APIs with optimistic revision checks.
- Human approval queue with single-decision enforcement and append-only audit events.
- PostgreSQL system of record with transactional audit writes, Alembic migrations, readiness
  checks, and database-level audit mutation protection.
- Bearer-token authentication adapter with scoped permissions, fail-closed durable startup, and
  authenticated actor binding for audit-producing writes.
