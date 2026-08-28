---
id: EXT-CREW-REPORT-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example crew-report/v1 payloads.
---

# `crew-report/v1` examples

## In-progress turn, artifact and pending work reported

```json
{
  "turn": 3,
  "claimed_verdict": "waiting",
  "reason": "opened a draft PR, waiting on review sign-off before continuing",
  "did": "implemented the migration script and opened the draft PR",
  "pending": "review sign-off",
  "artifact_refs": ["opaque-pr-ref-482"]
}
```

`claimed_verdict = "waiting"` is not a failure — it is a crew narrating that it is resting on an outcome not yet observed, the same shape `SCN-007`'s pending semantics describe at the canonical layer for execution settlement.

## Needs-action turn, blocked on an external input

```json
{
  "turn": 5,
  "claimed_verdict": "needs-action",
  "reason": "cannot proceed without the target environment's credentials",
  "inputs_needed": ["opaque-input-ref-env-creds"]
}
```

`inputs_needed` names the input by opaque reference only; it does not carry the credential value itself.

## Claimed-done turn — a claim, not acceptance

```json
{
  "turn": 8,
  "claimed_verdict": "done",
  "did": "completed the requested change and opened the PR for review",
  "artifact_refs": ["opaque-pr-ref-482"]
}
```

This is a claim only. It has no effect on canonical state: Work acceptance still requires an independent, candidate-bound assurance verdict per `INV-003` and `INV-005` through `INV-010`. A core reducer test holding canonical facts fixed while varying this payload (including flipping `claimed_verdict` to any other value) MUST show no change in canonical transitions or decisions (`CONF-EXT-006`).

## Minimal report, no optional fields

```json
{
  "turn": 1,
  "claimed_verdict": "waiting"
}
```

`reason`, `did`, `pending`, `inputs_needed`, and `artifact_refs` are all independently optional; a producer with nothing further to say for a turn reports only the two required fields.

## Producer violation: `verdict` field present instead of `claimed_verdict`

```json
{
  "turn": 2,
  "verdict": "done"
}
```

A producer MUST NOT emit `verdict` — the reserved field is `claimed_verdict`, precisely so this payload cannot be mistaken for a canonical assurance verdict (`EXT-003`, `INV-003`). This payload is missing its required `claimed_verdict` field and a validator MAY reject it. A component promising lossless round-trip nevertheless preserves the unknown `verdict` key unchanged per `EXT-005`/`CONF-EXT-003`.
