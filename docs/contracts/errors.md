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

Adapters translate provider-native errors into this taxonomy. Core policy MUST NOT branch on provider-native exit codes, HTTP codes, or protocol errors.
