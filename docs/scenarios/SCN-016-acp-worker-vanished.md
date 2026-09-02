---
id: SCN-016
type: scenario
status: superseded
authority: normative
description: ACP worker disappearance fails only after prompted current-turn activity corroborates no-session.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter this scenario describes was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` (ruling A6); push-shaped pending-settlement semantics now live in `docs/scenarios/SCN-007-pending-settlement.md` and `docs/scenarios/SCN-017-wait-resting-point.md`. Retained as historical reference only.

# SCN-016 — ACP worker vanished mid-turn

## Given

- An ACP execution has no terminal result for its outstanding turn.
- Its durable session record shows that it was prompted.

## Then

1. If `status -s <session>` reports exactly `no-session` and the outstanding
   turn's stream contains `agent_message_chunk`, `agent_thought_chunk`, or
   `tool_call*` activity, inspection settles `failed` (`CONF-EXEC-005`).
2. The observation records `acp-settlement/v1.unobservability` with reason
   `worker-vanished-mid-turn`, status `no-session`, and true prompted/activity
   corroboration.
3. If the stream is empty or has no substantive activity, inspection remains
   `running`: this is an ambiguous startup transient and MUST NOT false-fail
   (issue #157 precedent).
4. A terminal result remains authoritative, and the existing nonzero exit,
   signal, and `dead` plus `pidAlive == false` branches remain unchanged.
5. No timeout or retry count can produce this failure.

## Mutation check

Removing prompted evidence, accepting old-turn activity, treating an empty
startup stream as death, or settling without exact `no-session` makes this
scenario fail.

Verifies: `CONF-EXEC-003`, `CONF-EXEC-005`, `PORT-EXEC-002`,
`EXT-ACP-SETTLEMENT-V1`.
