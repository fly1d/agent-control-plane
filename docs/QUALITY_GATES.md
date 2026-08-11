# Quality Gates

The goal is fast feedback with stronger evidence where failure cost is higher. The policy
applies to changes merged into `main`, not to every local edit or experimental commit.

## Gate design

| Lane | Target time | Required evidence | When it runs |
| --- | ---: | --- | --- |
| Local | under 60 seconds | focused tests, formatter | while developing |
| Pull request | under 5 minutes | lint, types, unit tests, smoke tests, container build | every PR |
| Main | under 15 minutes | clean rebuild and complete current suite | every merge |
| Scheduled | time-boxed | dependency audit and supported Python versions | weekly |
| Release | risk-based | migration, rollback, security, and scenario tests | before release |

Required checks should be deterministic. A flaky required check is treated as a defect; blind
retries must not turn an unreliable result green.

## Change risk

| Risk | Examples | Review requirement |
| --- | --- | --- |
| Low | documentation, internal refactor, additive tests | one approval |
| Medium | new endpoint, adapter, retry behavior, dependency | owner approval and rollback note |
| High | auth, tool execution, memory deletion, migration, public schema removal | two approvals and rehearsal evidence |

## Smoke test contract

Smoke tests prove that the packaged service starts conceptually, reports readiness, accepts a
valid public contract, and rejects invalid input. They do not replace behavior, integration,
load, recovery, or security tests.

## Branch protection

Configure a GitHub ruleset for `main` with:

- pull requests required;
- at least one approval;
- stale approvals dismissed after new code is pushed;
- conversation resolution required;
- `fast-gate` and `container-build` required;
- force pushes and deletion blocked;
- administrators subject to the same rules.

Repository rules must be configured after the GitHub remote and owner are known; workflow files
alone cannot enforce approvals.
