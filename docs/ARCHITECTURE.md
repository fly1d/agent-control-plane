# Architecture

## Product principle

The control plane accepts existing agents and adds reliability and governance around them. It
does not own business-specific agent reasoning unless an adapter explicitly delegates that
responsibility.

## Initial boundaries

```text
Existing Agent
    |
    | HTTP / SDK / telemetry adapter
    v
Control Plane API
    |- AgentSpec validation
    |- authenticated principals and scoped permissions
    |- agent lifecycle and optimistic revision checks
    |- human approval queue and append-only audit events
    |- trace and replay       (planned)
    |- evaluation gates       (planned)
    `- version promotion      (planned)
```

The current code implements the API shell, the first versioned contract, and a governance loop
with in-memory and PostgreSQL adapters. The storage protocol is owned by the control plane, so
database types do not leak into the public API. PostgreSQL is the durable source of truth;
vector databases remain derived indexes, not authoritative stores.

State changes use an expected revision to reject stale writers. Only active agents can request
approval. Approval requests are single-decision records: an approved or rejected request cannot
be overwritten. State changes and their audit events share one database transaction. PostgreSQL
row locks serialize competing status and decision operations, while conditional updates provide
a second conflict check. A database trigger blocks audit mutation and removal. Events are
returned newest first.

Alembic owns schema versioning. Deployments run migrations as a separate step before the API;
readiness stays unavailable when the schema is missing.

Authentication is an owned adapter boundary. The initial adapter maps opaque bearer-token
fingerprints to subjects and permissions. Protected writes bind the request actor to the
authenticated subject before state reaches the store, so audit identity cannot be selected by
an untrusted request body. Durable mode fails closed without authentication; the unauthenticated
in-memory mode requires an explicit development switch. OIDC remains a future adapter rather
than a route-level dependency. Backup policy and retention enforcement are still required
before production use.

## Adapter policy

Temporal, Mem0, DSPy, LangSmith, and other providers must sit behind owned interfaces. A vendor
integration may implement a capability, but vendor-specific data types must not become the
public control-plane contract.

## Deferred decisions

- Durable workflow engine: require a validated cross-process or cross-day workflow first.
- Long-term memory: define provenance, consent, confidence, TTL, and deletion semantics first.
- Prompt optimization: require a stable evaluation set and guarded promotion workflow first.
- Kubernetes: require measured scaling, tenancy, or isolation pressure first.
