---
id: CONTRACT-ERRORS
type: contract
status: current
authority: normative
description: Canonical error taxonomy for ports and adapters.
---

# Canonical errors

| ID | Name | Meaning |
|---|---|---|
| `ERR-VALIDATION` | ValidationError | Caller input violates the canonical contract. |
| `ERR-CONFLICT` | ConflictError | Requested mutation conflicts with current durable state. |
| `ERR-NOT-FOUND` | NotFoundError | Required canonical or provider object does not exist. |
| `ERR-UNSUPPORTED-CAPABILITY` | UnsupportedCapability | Provider cannot guarantee required semantics. |
| `ERR-PROVIDER-UNAVAILABLE` | ProviderUnavailable | Provider cannot currently be reached or used. |
| `ERR-UNSAFE-STATE` | UnsafeState | Observed state cannot be safely interpreted or mutated. |
| `ERR-TEMPORARY` | TemporaryFailure | Operation may succeed if retried according to policy. |
| `ERR-PERMANENT` | PermanentFailure | Operation cannot succeed without changing intent/state/provider. |
| `ERR-BUSY` | Busy | A local storage lock could not be acquired within its bounded timeout. |

Adapters translate provider-native errors into this taxonomy. Core policy MUST NOT branch on provider-native exit codes, HTTP codes, or protocol errors.

`ERR-BUSY` is additive (`CONTRACT-STORAGE-CONCURRENCY`, §11's structured lock-busy requirement). It is distinct from `ERR-TEMPORARY`: `ERR-TEMPORARY` describes a provider-facing operation that may succeed on retry per policy (backoff, budget, a different provider); `ERR-BUSY` describes a purely local, mechanically bounded condition — this process's own storage layer could not acquire an exclusive lock on a resource it owns before a fixed timeout elapsed — with no provider and no retry-budget policy involved. A caller MAY retry an `ERR-BUSY` immediately or after a short local backoff; it MUST NOT be conflated with a provider outage, and a storage adapter MUST NOT fall back to an unlocked write merely because acquiring the lock produced this error (`CONTRACT-STORAGE-CONCURRENCY` §11).
