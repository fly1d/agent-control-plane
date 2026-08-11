# Contributing

## Change flow

1. Create a short-lived branch from `main`.
2. Keep the pull request focused on one behavior or decision.
3. Add or update tests for observable behavior.
4. Run `make check` locally.
5. Complete the pull request risk assessment and request review.
6. Merge only after required checks and approvals pass.

Direct pushes to `main` are not part of the normal workflow. Emergency fixes still use a pull
request, one reviewer, and the smoke suite; any deferred evidence is added within one business
day.

## Review expectations

Reviewers focus on behavior, failure modes, security boundaries, compatibility, operability,
and tests. Formatting and routine static checks belong to automation.

- Low risk: one approval and fast CI.
- Medium risk: one domain-owner approval, rollback notes, and relevant integration evidence.
- High risk: two approvals, including a security or data owner, migration rehearsal, and an
  explicit rollback plan.

High-risk examples include authorization, destructive tools, memory retention, secrets,
database migrations, public schemas, and prompt promotion logic.

## Compatibility

Public contracts are versioned. Removing a field, narrowing accepted input, or changing
meaning requires a new schema version or an approved migration plan.
