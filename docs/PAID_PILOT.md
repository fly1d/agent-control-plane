# Paid Pilot: Governed Refund Approvals

This document defines a commercial hypothesis to test, not a claim that the current project is
production-ready or that demand has already been proven.

## Buyer and problem

The initial buyer is the engineering or risk owner of a customer-support agent that can propose
refunds or credits. Their problem is not generating another answer. It is proving that a risky
action waited for the right human decision, preserving who decided it and why, and recovering
when an agent version behaves badly.

The qualifying scenario has all of these properties:

- an agent already runs in a test or production workflow;
- at least one action can create financial, compliance, or customer harm;
- humans review some of those actions today, even if the process is manual;
- the team cannot reconstruct decisions quickly from its current logs;
- a named owner has budget or authority to sponsor an operational pilot.

## Offer

The starting commercial hypothesis is a three-week, CNY 30,000 paid pilot in an isolated or
staging environment. Taxes, travel, custom infrastructure, and production support are outside
that price. Any quote to a real buyer must state the exact deployment boundary and data policy.

The pilot covers:

- one existing customer-support agent;
- one high-risk refund or credit action;
- registration, pause/activate, approval, decision, and audit integration;
- one policy workshop and one operator handoff session;
- a final evidence report against the agreed metrics.

The customer continues to own agent reasoning and execution. The control plane records and
governs the action request; it does not move money. No custom dashboard, compliance
certification, 24/7 SLA, model hosting, Mem0, DSPy, or autonomous prompt changes are included.

## Acceptance metrics

Before integration, both parties choose a representative set of at least 20 synthetic or
sanitized refund cases. The pilot succeeds technically when:

- every above-threshold test action is held until an explicit decision;
- every sampled decision can be reconstructed from actor, reason, status, and audit events;
- stale lifecycle writes and repeated decisions fail closed;
- the customer can pause the integrated agent and observe the state change;
- the integration requires no more than five customer engineering days.

Commercial validation is separate from technical success. Continue investing after the pilot
only if a named buyer agrees the problem is material, uses the workflow with real operators, and
offers a paid production next step. Do not treat repository stars, compliments, or an unpaid
demo as purchase evidence.

## Readiness boundary

The current `main` branch is suitable for local and isolated evaluation. A pilot using
customer-accessible infrastructure must wait for authentication in issue #15 and pull request
#16 to receive the required independent security reviews. Production use additionally requires
idempotency, backup and restore rehearsal, tenant/resource authorization, token rotation or
OIDC, rate limiting, and an agreed operational owner.

## Demo

Start the development API and run the reproducible scenario from another shell:

```bash
make run
python examples/refund_approval.py
```

The script registers a uniquely named support agent, activates it, requests approval for a CNY
1,280 refund, verifies that the request is pending, records a human decision, and checks the four
audit events. It does not call a payment or refund system.

For an authenticated environment, configure a bearer token for each principal:

```bash
export ACP_DEMO_OPERATOR_TOKEN='<operator-token>'
export ACP_DEMO_AGENT_TOKEN='<agent-token>'
export ACP_DEMO_REVIEWER_TOKEN='<reviewer-token>'
python examples/refund_approval.py
```

The subjects configured for those tokens must match `ACP_DEMO_OPERATOR_ACTOR`,
`ACP_DEMO_AGENT_ACTOR`, and `ACP_DEMO_REVIEWER_ACTOR`. `ACP_DEMO_TOKEN` is a convenience fallback
only when all three actor variables are also set to that token's subject. Separate
least-privilege identities are required for a real pilot.
