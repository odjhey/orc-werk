---
id: ADAPTER-OMP-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: OMP capability status — no canonical CAP-* advertised (no Port implemented) plus honest, evidence-linked harness-level seat-discipline findings.
---

# OMP capabilities

## Canonical `CAP-*`

OMP advertises **no** canonical `CAP-*` capability. It implements no
`PORT-EXECUTION`, `PORT-ASSURANCE`, `PORT-WORK-GRAPH`, or `PORT-CANDIDATE`
interface for such a capability to describe (`README.md`) — this mirrors
`ADAPTER-GIT-CAPABILITIES` and `ADAPTER-BEADS-CAPABILITIES`, which
likewise advertise none for the Port each does not implement.

## Harness-level seat-discipline findings (informative, not `CAP-*`)

`ADR-0007` claims OMP gives orc-werk stronger enforcement rungs than
prose for seat discipline: model-family tool restrictions, worktree
fencing, strict result-schema rejection, timeout-bounded task lifecycle,
and durable transcripts. None of these is a canonical `CAP-*` guarantee —
they are properties of the *harness*, not of an adapter implementing a
Port — so this section lists them separately, sourced only from
`TASK-M5-001`'s capability-test report, and claims nothing beyond what
that report evidences.

**Status at authoring time: `TASK-M5-001`'s report
(`docs/reports/2026-09-07-omp-capability-test.md`) was still in progress
— probes running against the installed OMP `18.1.12` (not `18.1.11` as
`ADR-0007`'s Context assumed; the installed version advanced between the
ADR and this card). No pass/fail verdict for any of the five points or
the role-identity probe had been recorded as of this writing.** Per this
card's own discipline (an untested capability is a gap, not a pass), this
document claims none of the five as proven and records each as pending
below rather than guessing. Amend this table once the report lands.

| Point | Harness mechanism | Status |
|---|---|---|
| 1. Tool restriction denies `git push` from a non-Anthropic-family verify seat | `tools` restriction + `tool_call` hook | pending `TASK-M5-001` |
| 2. Ship agent creates its own worktree; a hook fences writes outside it | `.omp/extensions/orc-seat.ts` (`TASK-M5-005`, not yet built) | pending `TASK-M5-001` |
| 3. `outputSchema` + `schemaMode: strict` rejects a result missing a required field | OMP's own structured-output validation | pending `TASK-M5-001` |
| 4. `task.maxRuntimeMs` stops a task and its descendants; `history://` survives | OMP task lifecycle | pending `TASK-M5-001` |
| 5. A full transcript reads back from `~/.omp/agent/sessions/...jsonl` after a new session and after a reboot | OMP session storage | pending `TASK-M5-001` |
| Role-identity probe: can a hook/extension learn the running agent's role (name)? | `.omp/extensions/*` hook API | pending `TASK-M5-001` — until answered, `mapping.md`'s `role` field stays agent-supplied, not mechanically derived |

A failing point (or a "no" role-identity answer) does not invalidate this
adapter's documentation: `ADR-0007` and `mapping.md` already state the
named fallback for each (per-role rules move into agent `tools`/system
prompt instead of a hook; `role` stays agent-supplied text). This
document's job is to keep the claimed-vs-evidenced line honest, not to
assume the fallback is never needed.

## Named limitation: the output schema does not prove the ledger write happened

Independent of `TASK-M5-001`'s pending results, one limitation is
structural and does not need a capability test to state: OMP's
`outputSchema`/`schemaMode: strict` validates the *shape* of an agent's
final `yield`, never that the agent actually invoked `orc record` with
matching field values, or at all, before yielding. A ship agent could
yield a schema-valid `{head_sha: "...", recorded: "..."}` describing a
recording that never happened. Closing this gap is exactly `TASK-M5-005`'s
scope (a `tool_call` hook blocking `yield` until a successful `orc record`
was observed in the session) — not built as of this writing. Until it
ships, this remains process discipline (the agent's own body instructs
"record before yield"), enforced no more strongly than
`PLAYBOOK-AGENT-CLI` always required.

## Related

- `TASK-M5-001`
- `ADR-0007`
- `docs/adapters/git/capabilities.md`, `docs/adapters/beads/capabilities.md`
- `docs/contracts/capabilities.md`
