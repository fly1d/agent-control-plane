# Quality Gates

The goal is fast feedback with stronger evidence where failure cost is higher. The policy
applies to changes merged into `main`, not to every local edit or experimental commit.

## Gate design

| Lane | Target time | Required evidence | When it runs |
| --- | ---: | --- | --- |
| Local | under 60 seconds | focused tests, formatter | while developing |
| Pull request | under 5 minutes | lint, types, unit tests, PostgreSQL integration, smoke tests, container build | every PR |
| Main | under 15 minutes | clean rebuild and complete current suite | every merge |
| Scheduled | time-boxed | dependency audit and supported Python versions | weekly |
| Release | risk-based | migration, rollback, security, and scenario tests | before release |

Required checks should be deterministic. A flaky required check is treated as a defect; blind
retries must not turn an unreliable result green.

## Change risk

The repository uses team mode when at least two trusted maintainers can review and merge. It uses
solo-maintainer mode when only one person has that authority. A solo maintainer must not use an
alternate account to manufacture independence. Automated or AI-assisted review is useful
evidence, but it is not an independent human approval.

| Risk | Examples | Team mode | Solo-maintainer mode |
| --- | --- | --- | --- |
| Low | documentation, internal refactor, additive tests | one approval and fast CI | recorded owner decision and fast CI |
| Medium | new endpoint, adapter, retry behavior, dependency | domain-owner approval, rollback note, and relevant evidence | recorded owner decision, rollback note, relevant evidence, and a 24-hour cooling period |
| High | auth, tool execution, memory deletion, migration, public schema removal | two approvals, including the relevant security or data owner, plus rehearsal evidence | independent external domain review before production release, plus rehearsal evidence and an explicit rollback plan |

The solo-maintainer cooling period starts after the final material push. A change to behavior,
dependencies, permissions, deployment configuration, public contracts, or risk analysis resets
the period; typo-only or review-metadata updates do not. The pull request records the final
material push time and earliest merge time.

For a high-risk change, an external reviewer can be a trusted open-source maintainer, contractor,
consultant, or customer security/data owner. If no external reviewer is available, the solo
maintainer may merge only when all of the following are true:

- the capability is not deployed to or designated for production and is disabled by default
  where that control is applicable;
- the pull request and user documentation label it experimental and not approved for production;
- rehearsals and rollback evidence pass in an isolated environment;
- the owner decision names the restriction and the evidence required to remove it.

Merging under that exception does not authorize production deployment. Removing the restriction
is itself a high-risk change and requires the independent external review.

## Owner decision record

In solo-maintainer mode, approval is an explicit risk decision rather than a GitHub approval on
the author's own pull request. The pull request must state:

- the risk level and why it is correctly classified;
- the checks, smoke tests, and review performed;
- the failure mode and rollback plan;
- the final material push and earliest merge time for medium-risk work;
- any external review or production restriction required for high-risk work;
- a final `merge` or `hold` decision from the repository owner.

## Smoke test contract

Smoke tests prove that the packaged service starts conceptually, reports readiness, accepts a
valid public contract, and rejects invalid input. They do not replace behavior, integration,
load, recovery, or security tests.

Database changes additionally require upgrade, integration, downgrade, and re-upgrade evidence
against the supported PostgreSQL version. Migration rehearsal uses disposable data only.

## Dependency maintenance

Dependency pull requests must identify a compatibility, security, or reproducibility benefit.
Dependabot may raise a declared minimum version when the existing constraint blocks an update;
it must not create routine pull requests that only replace one compatible lower bound with a
newer one. Major tool upgrades are reviewed separately from routine maintenance.

## Branch protection

Configure a GitHub ruleset for `main` with:

- pull requests required;
- stale approvals dismissed after new code is pushed;
- conversation resolution required;
- `fast-gate` and `container-build` required;
- `postgres-integration` required for database changes;
- force pushes and deletion blocked;
- administrators subject to the same rules.

In team mode, require at least one approving review in GitHub and enforce the additional
high-risk approval through the pull request policy. In solo-maintainer mode, set required
approvals to zero because GitHub does not allow an author to approve their own pull request;
enforce the owner decision record, cooling period, and external production review through the
pull request. Switch the ruleset to team mode as soon as a second trusted maintainer accepts
review responsibility.

Workflow files alone cannot enforce human approvals, cooling periods, or production restrictions.
