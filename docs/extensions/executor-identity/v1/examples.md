---
id: EXT-EXECUTOR-IDENTITY-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Ship- and verify-seat executor-identity/v1 examples.
---

# `executor-identity/v1` examples

## Ship seat

```json
{
  "extensions": {
    "executor-identity/v1": {
      "model": "provider/ship-model",
      "session_ref": "orchestrator-session-42",
      "seat_ref": "ship-thread-1",
      "role": "ship"
    }
  }
}
```

This payload belongs on the ship seat's execution attempt entry and transports to the execution settlement. Its references are provenance claims, not canonical execution or candidate identity.

## Verify seat sharing the orchestrating session

```json
{
  "extensions": {
    "executor-identity/v1": {
      "model": "provider/verify-model",
      "session_ref": "orchestrator-session-42",
      "seat_ref": "verify-thread-2",
      "role": "verify"
    }
  }
}
```

The verify seat shares the ship seat's `session_ref` but has a distinct `seat_ref`, making the seats distinguishable in the journal. This payload belongs alongside the assurance verdict and does not alter it.
