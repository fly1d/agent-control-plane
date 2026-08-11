# Security Policy

Do not report suspected vulnerabilities through a public issue. Until a dedicated security
contact is configured, keep the GitHub repository private and report findings directly to the
repository owner.

Security-sensitive changes include authentication, authorization, tool policies, sandboxing,
secrets, audit records, memory retention, tenant isolation, and dependency provenance. These
changes require the high-risk review path described in `docs/QUALITY_GATES.md`.

Never place API keys, customer traces, prompts, memories, production data, or credentials in
the repository or test fixtures.

The PostgreSQL credentials in `compose.yaml` and bearer token documented for local Compose are
fixed development-only values. Production deployments must inject a separate database URL
through secret management, restrict the application role, encrypt connections, and run
backup/restore exercises before storing customer data.

Durable deployments fail startup unless `ACP_AUTH_CONFIG` defines authenticated principals.
The configuration contains only SHA-256 fingerprints of high-entropy bearer tokens; raw tokens
must remain in the caller's secret manager, must be sent only over TLS, and must never appear in
logs. Grant explicit permissions and avoid the `*` administrator permission for routine agent
or reviewer identities. The static-token adapter is an initial bootstrap mechanism, not a
replacement for centrally managed identity, short-lived credentials, or token rotation.
