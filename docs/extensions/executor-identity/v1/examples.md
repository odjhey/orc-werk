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

## OMP-sourced example (real journal, distinct sessions per seat)

Ship and verify payloads actually recorded by an OMP-run ship/verify pair
for this repository's own `adopt-270-attempt-binding` run
(`.orc/adopt-270-attempt-binding/journal.jsonl`, `FACT-EXEC-SETTLED` and
`FACT-ASSURE-SETTLED`):

```json
{
  "extensions": {
    "executor-identity/v1": {
      "model": "xai-oauth/grok-4.6",
      "session_ref": "omp:watchtower",
      "seat_ref": "ship-adopt-b50a335",
      "role": "ship"
    }
  }
}
```

```json
{
  "extensions": {
    "executor-identity/v1": {
      "model": "google-antigravity/gemini-3.8-flash",
      "session_ref": "VerifyAdopt270",
      "seat_ref": "verify-adopt-b50a335",
      "role": "verify"
    }
  }
}
```

Unlike the two idealized examples above, these two payloads do **not**
share a `session_ref` — the ship seat ran under an orchestrating session
labeled `omp:watchtower` while the independent verify seat recorded its
own `VerifyAdopt270` label. This is still a valid pair: `EXT-EXECUTOR-
IDENTITY-V1-SEMANTICS` only requires each seat's `seat_ref` to be
distinct, never that `session_ref` be shared. Both `seat_ref` values
follow the `<role>-<work_id>-<sha7-of-candidate-head>` convention
documented in `docs/adapters/omp/mapping.md` — `b50a335` is the first
seven hex characters of the candidate's `head_sha`
(`b50a3356913e8525fd30ed8ebf8bce45b0ebc676`), giving both seats a value
that is reproducible from the candidate alone and distinguishable from
each other.
