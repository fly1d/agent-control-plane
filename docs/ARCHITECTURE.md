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
    |- agent lifecycle and optimistic revision checks
    |- human approval queue and append-only audit events
    |- trace and replay       (planned)
    |- evaluation gates       (planned)
    `- version promotion      (planned)
```

The current code implements the API shell, the first versioned contract, and an in-memory
governance loop. The storage protocol is owned by the control plane so PostgreSQL can replace
the development adapter without leaking database types into the public API. PostgreSQL becomes
the source of truth when persistence is introduced. Vector databases remain derived indexes,
not authoritative stores.

State changes use an expected revision to reject stale writers. Approval requests are
single-decision records: an approved or rejected request cannot be overwritten. Audit events
are append-only within the store and returned newest first. Authentication and durable audit
retention are required before production use.

## Adapter policy

Temporal, Mem0, DSPy, LangSmith, and other providers must sit behind owned interfaces. A vendor
integration may implement a capability, but vendor-specific data types must not become the
public control-plane contract.

## Deferred decisions

- Durable workflow engine: require a validated cross-process or cross-day workflow first.
- Long-term memory: define provenance, consent, confidence, TTL, and deletion semantics first.
- Prompt optimization: require a stable evaluation set and guarded promotion workflow first.
- Kubernetes: require measured scaling, tenancy, or isolation pressure first.
