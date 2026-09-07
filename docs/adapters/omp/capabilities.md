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

**Status: `TASK-M5-001`'s report
(`docs/reports/2026-09-07-omp-capability-test.md`) landed 2026-09-07 (PR
#277) against the installed OMP `18.1.12` (not `18.1.11` as `ADR-0007`'s
Context assumed; the installed version advanced between the ADR and this
card), and records a PASS/FAIL verdict for all five points plus the
role-identity probe.** The table below is sourced from that report's own
§8 consequence summary and nothing else. The report has been amended
twice on `master`: a role-identity correction (PR #286, informed by
findings from `task-m5-005`'s rejected attempt in PR #284) and a hook
capability-bound amendment (PR #292, merged 2026-09-07T08:02:32Z, commit
`eea2319`) — both landed, not in-flight. A further amendment, recording
the `tool_call` hook's final abandonment (report §9; `ADR-0007`'s
2026-09-07 hook-retirement amendment), lands alongside this table update;
this table reflects the report's content at this repo's current commit.

| Point | Harness mechanism | Status |
|---|---|---|
| 1. Tool restriction denies `git push` from a non-Anthropic-family verify seat | GitHub branch protection on `master` (not a `tool_call` hook — a hook can read the calling agent's role structurally (`session_init.agent`, role-identity row below) but the escaped-command probes established it cannot reliably decide whether a given, possibly-obscured command *is* a `git push`; per-role push denial needs an action-decidable rung, per the 2026-09-07 operator ruling) | PASS against an unescaped probe, both via a custom hook and native `bash.patterns` (report §1); superseded as the guard mechanism by the 2026-09-07 ruling — see Mechanism. Re-verified against the final ruling: still accurate — no hook rung was ever a candidate for this row past 2026-09-07, and none exists now (`ADR-0007`'s 2026-09-07 hook-retirement amendment; report §9). |
| 2. Ship agent creates its own worktree; a write outside it is visible after the fact | No hook — the 2026-09-07 `docs-hook-capability-limit` ruling's one surviving guard (guard 4, structural cwd-derived fencing) was itself defeated on 2026-09-07 by two further escape classes (path canonicalization, issues #296/#297; scheme adjudication, issue #298), across `task-m5-005-guards` and `task-m5-005-sensor`'s remaining attempts. `.omp/extensions/orc-seat.ts` never existed in this repository; the branch that carried it (`task-m5-005-orc-seat-hook`, `TASK-M5-005`, `gh-pr:284`) was closed unmerged at final head `69e482988736bb48ed9fb3e3301a8ab694a4cdfd` without a fourth attempt. The mechanism now: ship's own worktree-creation protocol (`ship.md` §Boundaries) plus after-the-fact ledger/PR audit — the same mechanism that caught all three escape classes. | Superseded 2026-09-07 (`ADR-0007`'s hook-retirement amendment; report §9). The guard-4 fencing PASS from report §2 held only for the shape tested 2026-09-06 and does not survive the two later escape classes; no hook mechanism remains to report a verdict on. |
| 3. `outputSchema` + `schemaMode: strict` rejects a result missing a required field | OMP's own structured-output validation | PASS (report §3) |
| 4. `task.maxRuntimeMs` stops a task and its descendants; `history://` survives | OMP task lifecycle | PASS (report §4): the underlying process is actually killed, not merely abandoned, and `history://` still reads back after the abort |
| 5. A full transcript reads back from `~/.omp/agent/sessions/...jsonl` after a new session and after a reboot | OMP session storage | PASS (report §5), with a nuance: `--export` requires the transcript's actual path, not a bare session id |
| Role-identity probe: can a hook/extension learn the running agent's role (name)? | `ctx.sessionManager.getEntries()`/`getBranch()` → `session_init.agent` | **Yes** — corrected 2026-09-07 (`docs/reports/2026-09-07-omp-capability-test.md` §6 Correction; run `task-m5-005` seq 16, PR #284). `TASK-M5-001`'s original probe missed this: it walked `ctx.sessionManager`'s enumerable keys but never called `getEntries()`/`getBranch()`. `mapping.md`'s `role` field can now be read structurally off the running session's own `session_init.agent` entry from within a hook, not only supplied by the operator's dispatch choice. |

A failing point does not invalidate this adapter's documentation:
`ADR-0007` and `mapping.md` already state a named fallback for a
capability that turns out unavailable (per-role rules move into agent
`tools`/system prompt instead of a hook). The role-identity probe is not
such a case — its initial "no" was corrected to "yes" above — but this
document's job remains to keep the claimed-vs-evidenced line honest, not
to assume every capability holds.

## Named limitation: the output schema does not prove the ledger write happened

One limitation is structural and does not need a capability test to
state: OMP's `outputSchema`/`schemaMode: strict` validates the *shape* of
an agent's final `yield`, never that the agent actually invoked `orc
record` with matching field values, or at all, before yielding. A ship
agent could yield a schema-valid `{head_sha: "...", recorded: "..."}`
describing a recording that never happened. Per the 2026-09-07 operator
ruling, this gap is **not** closed by a `tool_call` hook: a hook sees only
the bare command string, never proof that a prior `bash` call actually
invoked `orc record` and exited `0`/`3`, so `TASK-M5-005` dropped this
guard from its scope (the same command-string limitation that defeated
`task-m5-005`'s other text-matching guards). The gap is closed one rung up
instead: the orc ledger's own state machine closes the gap for the paths
that reach `ACCEPTED`/`BLOCKED` through bound assurance — those paths
never treat a Work as settled unless `orc record` actually ran, whatever
an agent's `yield` claims; the cancellation path is a disclosed,
unenforced escape from that rung (issue #293). Short of the
assurance-bearing rung, it remains process discipline (the agent's own
body instructs "record before yield"), enforced no more strongly than
`PLAYBOOK-AGENT-CLI` always required.

## Related

- `TASK-M5-001`
- `ADR-0007`
- `docs/adapters/git/capabilities.md`, `docs/adapters/beads/capabilities.md`
- `docs/contracts/capabilities.md`
