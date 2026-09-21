# Contributing

## Change flow

1. Create a short-lived branch from `main`.
2. Keep the pull request focused on one behavior or decision.
3. Add or update tests for observable behavior.
4. Run `make check` locally.
5. Complete the pull request risk assessment and select team or solo-maintainer review mode.
6. Record the required approval or owner decision.
7. Merge only after the applicable checks, review evidence, and waiting period pass.

Direct pushes to `main` are not part of the normal workflow. Emergency fixes still use a pull
request and the smoke suite. A solo maintainer may waive only the cooling period for an active
incident, must explain why in the owner decision, and adds any deferred evidence within one
business day. A cooling-period waiver does not waive a high-risk production review.

## Review expectations

Reviewers and solo-maintainer self-review focus on behavior, failure modes, security boundaries,
compatibility, operability, and tests. Formatting and routine static checks belong to
automation.

- Team mode requires one approval for low and medium risk and two relevant approvals for high
  risk.
- Solo-maintainer mode allows low-risk merge after recorded owner review and passing CI.
- Solo-maintainer medium-risk work also requires rollback evidence and 24 hours after the final
  material push.
- Solo-maintainer high-risk work requires independent external review before production release.
  Without it, merge is allowed only under the experimental restrictions in
  `docs/QUALITY_GATES.md`.

High-risk examples include authorization, destructive tools, memory retention, secrets,
database migrations, public schemas, and prompt promotion logic.

An AI review or a second account controlled by the author is not an independent approval. An
external reviewer does not need to be an employee, but must have relevant expertise and no
authorship conflict for the reviewed change.

## Compatibility

Public contracts are versioned. Removing a field, narrowing accepted input, or changing
meaning requires a new schema version or an approved migration plan.
