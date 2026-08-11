# Security Policy

Do not report suspected vulnerabilities through a public issue. Until a dedicated security
contact is configured, keep the GitHub repository private and report findings directly to the
repository owner.

Security-sensitive changes include authentication, authorization, tool policies, sandboxing,
secrets, audit records, memory retention, tenant isolation, and dependency provenance. These
changes require the high-risk review path described in `docs/QUALITY_GATES.md`.

Never place API keys, customer traces, prompts, memories, production data, or credentials in
the repository or test fixtures.

The credentials in `compose.yaml` are fixed development-only values. Production deployments
must inject a separate database URL through secret management, restrict the application role,
encrypt connections, and run backup/restore exercises before storing customer data.
