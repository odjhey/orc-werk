---
id: REPORT-2026-09-07-M5-PILOT-RETROSPECTIVE
type: report
status: current
authority: informative
description: TASK-M5-008's pilot write-up — whether TASK-M5-001's capability-test predictions and ADR-0007's design held under the real seat traffic of m5-omp-harness-pilot and the ten deliveries that followed it on 2026-09-06/07, drawn only from the orc ledger, the PRs, and the landed capability report.
---

# M5 OMP-first delivery — pilot write-up (`TASK-M5-008`)

This is the second half of `TASK-M5-008`. `docs/delivery/seat-reliability.md`'s
format and first four entries landed early in `fix-verify-seat-fallback`
(PR #268); this report is the pilot write-up that card left open, plus two
newly observed reliability events appended to that log the same day they
were found (below).

**Sources**, all read directly, none paraphrased from memory: `orc --limit 0`;
`orc history <run> --limit 0` and the raw `.orc/<run>/journal.jsonl` +
`times.jsonl` for `m5-omp-harness-pilot`, `fix-verify-seat-fallback`,
`adopt-270-attempt-binding`, `docs-external-candidate-lane`,
`fix-262-docs-polish`, `task-m5-003`, `fix-254-active-filter`, `task-m5-006`,
`fix-266-reobservation`, `task-m5-001`, and `chore-verify-followups`;
`gh pr view` for PRs #267, #268, #270, #271, #277, #278; `ADR-0007`;
`M5-OMP-FIRST-DELIVERY`; `docs/reports/2026-09-07-omp-capability-test.md`
(`TASK-M5-001`'s report, PR #277, accepted `ran-real-code`).

Every claim below cites a run id + seq or a PR number. Where the ledger is
silent, this says so — that is the `T5`/`T6` rule this card itself imposes,
not an omission.

## 1. Did `TASK-M5-001`'s capability predictions hold?

`ADR-0007`'s Context named five specific OMP rungs it was betting the whole
migration on: "agent frontmatter (`model`, `tools`, `output`), `outputSchema`
with `schemaMode: strict`, `tool_call` hooks that can block (not merely
advise), `task.maxRuntimeMs`, and durable `history://` transcripts." The
capability report (`docs/reports/2026-09-07-omp-capability-test.md`, landed
PR #277, `orc history task-m5-001` seq 16 verdict `accepted`) tested each one
fresh against the installed `omp/18.1.12` and recorded a real pass/fail per
`nother-guide`'s "an untested capability is a gap, not a pass":

| Prediction (`ADR-0007` / `M5-OMP-FIRST-DELIVERY` Phase 0) | Report result | Citation |
|---|---|---|
| A blocking hook can deny `git push` from a non-Anthropic model | **HELD** — denied via both a custom hook and the native `bash.patterns` key, against a disposable local remote, reproduced inside a `task`-spawned subagent too | report §1 |
| "Give a task item no `cwd`; confirm the ship agent creates its own worktree and a hook fences writes outside it" | **PARTLY WRONG, PARTLY HELD** — the card's own premise (OMP auto-creates a worktree for a no-`cwd` spawn) is empirically false: a non-isolated `task` spawn inherits the parent's own cwd verbatim (`{"pwd": "/tmp/omp-cap-probe/repo"}`); the *fencing mechanism itself* still works red-then-green once the hook is told a path by convention | report §2 |
| `outputSchema` + `schemaMode: strict` rejects a result missing a required field | **HELD** — `schema_violation` / `"verdict: is required"`, independent of model cooperation (a hook forcibly stripped the field to make this true regardless of model behavior) | report §3 |
| `task.maxRuntimeMs` stops a task; descendant dies; `history://` survives | **HELD** — process actually killed (marker file never created), `history://timeoutProbe` readable post-abort | report §4 |
| A transcript survives a fresh process / "after a reboot" | **HELD**, with a footgun noted: `--export` needs the real `.jsonl` path, not a bare session id, or it silently creates an empty session instead of erroring | report §5 |
| (open probe) Can a hook learn which named role — `ship`/`verify`/`scout` — is running? | **NO** — confirmed twice independently; `ctx`'s only own-enumerable key is `ui`; no `role`/`agentName` field exists on `event` or `ctx`; the only proxy is string-matching the agent's own system-prompt prose, which `TASK-M5-004`'s wording is free to change | report §6 |

Two findings the five-point test did not ask for, but which land squarely on
this milestone's own risk register:

- **§7a — concurrent `omp -p` processes silently no-op under load.** At N=3
  same-repo, same-account concurrent invocations, 1/3 printed only
  `Working...`, exited `rc=0`, produced no task output and no error; at N=4,
  4/4 did. Reproduced across four different providers including a lone
  `anthropic/claude-sonnet-5` process dying the same way — ruling out a
  single-provider quota ceiling as the sole cause. **FAIL** as a directly
  relevant, reproduced gap: `rc=0` alone is not proof a parallel `omp -p`
  batch completed.
- **§7b — the executing model can silently differ from the requested one.**
  `retry.fallbackChains` (rung-1 config) substituted `xai-oauth/grok-4.6` for
  a requested `google-antigravity/gemini-3.8-flash` invocation mid-probe,
  with no error and no visible notice in text mode. Consequence for
  `executor-identity/v1`: the `model` a seat types into `orc record --model`
  can differ from the model that actually generated the output, and neither
  the hook surface nor the ledger extension can detect that divergence from
  the journal alone — "their presence is provenance, not proof" is not a
  hedge, it is load-bearing.

**Net:** every one of the five gating predictions held at the mechanism
level. The one that did not hold as *written* was a premise inside the
`TASK-M5-001` task card itself (not `ADR-0007`), and the report corrected it
rather than silently building around it — exactly the discipline
`nother-guide`'s `harness-capabilities.md` asks for. The still-open
consequence is `TASK-M5-005` (the actual `.omp/extensions/orc-seat.ts` hook):
its per-role rules (deny push from verify, fence writes to ship's own
worktree) cannot branch on a structural role field — they must be encoded
per-agent (`tools:`/`output:`/system prompt, already how `ship.md`/`verify.md`
restrict `write`/`edit` today) or as session-wide rules, per report §6/§8.
`TASK-M5-005` was still `EXECUTING` (not yet `ACCEPTED`) in the ledger at the
time of this write-up (`orc --limit 0`: `task-m5-005: states=EXECUTING:1
flags=pending`) — this consequence is a design constraint for that card, not
something this write-up can confirm was built correctly, because it has not
shipped yet.

## 2. Did seat discipline hold under real traffic?

Eleven runs carry ledger evidence for this question: the pilot itself, its
same-day follow-up, two external-candidate-lane adoptions, and the
2026-09-07 wave of seven further deliveries, all now settled.

| Run (PR) | Ship model / session | Verify model / session | Verdict (attempts) |
|---|---|---|---|
| `m5-omp-harness-pilot` (#267) | `anthropic/claude-sonnet-5` / `ShipM5Pilot` | `google-antigravity/gemini-3.8-flash` / `VerifyM5PilotC` | accepted (1) |
| `fix-verify-seat-fallback` (#268) | `anthropic/claude-sonnet-5` / `ShipVerifyFallback` | `google-antigravity/gemini-3.8-flash` / `VerifyFallback` | accepted (1) |
| `adopt-270-attempt-binding` (#270, adopted external PR) | `xai-oauth/grok-4.6` / `omp:watchtower` | `google-antigravity/gemini-3.8-flash` / `VerifyAdopt270` | accepted (1) |
| `docs-external-candidate-lane` (#271) | `xai-oauth/grok-4.6` / `omp:watchtower` | `google-antigravity/gemini-3.8-flash` / `VerifyLaneDoc` | accepted (1) |
| `fix-262-docs-polish` (#272) | `anthropic/claude-sonnet-5` → `claude-sonnet-5` / `ShipFix262` → `ShipFix262R2` | `google-antigravity/gemini-3.8-flash` / `VerifyFix262` → `VerifyFix262R2` | **rejected, then accepted (2)** |
| `task-m5-003` (#273) | `claude-sonnet-5` / `ShipM5003` | `google-antigravity/gemini-3.8-flash` / `VerifyM5003` | accepted (1) |
| `fix-254-active-filter` (#274) | `claude-sonnet-5` / `ShipFix254` | `google-antigravity/gemini-3.8-flash` / `VerifyFix254` | accepted (1) |
| `task-m5-006` (#275) | `anthropic/claude-sonnet-5` / `ShipM5006` | `google-antigravity/gemini-3.8-flash` / `VerifyM5006` | accepted (1) |
| `fix-266-reobservation` (#276) | `claude-sonnet-5` / `ShipFix266` | `google-antigravity/gemini-3.8-flash` / `VerifyFix266` | accepted (1) |
| `task-m5-001` (#277) | `anthropic/claude-sonnet-5:medium` / `ShipM5001` | `google-antigravity/gemini-3.8-flash` / `VerifyM5001` | accepted (1) |
| `chore-verify-followups` (#278) | `anthropic/claude-sonnet-5` / `ShipCleanup` | `google-antigravity/gemini-3.8-flash` / `VerifyCleanup` | accepted (1) |

(Citation for each row: `.orc/<run>/journal.jsonl` `FACT-EXEC-SETTLED` /
`FACT-ASSURE-SETTLED` `extensions."executor-identity/v1"`, seq 10/16 for
single-attempt runs, seq 10/16/20/26 for `fix-262-docs-polish`.)

### The rejection cycle (`fix-262-docs-polish`) is discipline working, not failing

Attempt 1's verify seat (`VerifyFix262`, `google-antigravity/gemini-3.8-flash`)
recorded `rejected` (seq 16) with a specific, falsifiable defect: the PR's
`examples.md` claimed its JSON examples matched the *nested* shape of
`.orc/docs-pstack-assurance-depth/journal.jsonl` seq 16, when the real seq 16
bytes put `verdict`/`evidence_refs` under `data` and `extensions` as a
sibling of `data`, not of `verdict` — a genuine grounding error, not a taste
call. Attempt 2 (`ShipFix262R2`) fixed exactly that claim and nothing else
(`git diff` confined to the one file per seq 26's findings); `VerifyFix262R2`
re-verified the correction against the real seq-16 bytes and accepted. Total
wall clock from first dispatch to final accept: 37m1s (00:34:40→01:11:41,
`times.jsonl`). This is `nother-guide`'s verification working as designed —
an independent seat caught a real defect before it reached `master`, and the
next attempt closed it — not a discipline failure to report as a black mark.

### `V7` held in principle for every delivery; `ADR-0007`'s literal text did not

Every verify seat in this table ran on `google-antigravity/gemini-3.8-flash`
— zero occurrences of `openai-codex` anywhere in any of these runs' journals
(checked directly: `jq` over every run's `executor-identity/v1.model` for a
match on `openai-codex` returns nothing). Ship ran on the `anthropic` family
(or, for the two external-candidate-lane adoptions, on `xai-oauth/grok-4.6`
via the watchtower's own session — see below). So `V7`'s actual risk-control
purpose — verify on a materially different model family than ship, so a
shared failure mode can't slip both seats — held for every one of these eleven
settled deliveries.

But `ADR-0007`'s `V7` ruling is not written as "any non-Anthropic family": it
names `openai-codex` (`gpt-5.6-sol`) specifically as "a `contract`-layer
requirement... enforced by the agent definition itself... because the two
families genuinely differ" (`ADR-0007` §`V7` ruling). That pairing broke on
day one: `fix-verify-seat-fallback`'s own seat-reliability entries
(`docs/delivery/seat-reliability.md`, 2026-09-06) record two Codex spawns
dying at `usage_limit_reached` within the pilot's own run, and
`.omp/agents/verify.md`'s `model:` list was reordered same-day to lead with
`google-antigravity/gemini-3.8-flash` — logged there as "a recorded
deviation, not an amendment: revisit once Codex quota is restored." It was
not revisited: within the ten named deliveries this write-up tracks, all ten
now carry a settled verify verdict — `chore-verify-followups` was the last to
settle, at `01:37:18Z` — and every one ran on `google-antigravity` with no
`openai-codex` fallback ever observed firing. A one-day hand substitution has
become the standing practice across two calendar days and ten deliveries, while `ADR-0007`'s own
text still names `openai-codex` as the contract-layer pairing. Per
`AGENTS.md` rule 4 ("update/propose the canonical contract first when
behavior is ambiguous"), this is no longer a live, time-boxed deviation with
a trigger — it needs a formal `ADR-0007` amendment recording
`google-antigravity` (or "any non-Anthropic family") as the actual `V7`
pairing, not a second week of the ledger quietly deviating from its own
governing decision. This write-up flags it; amending the ADR is out of this
card's scope and is named under Ambiguities below.

### A live ledger during a live write-up: counts are snapshots, not totals

This section's own settled-verdict counts moved three times while this card
was in flight — worth recording as a property of auditing a ledger the
write-up itself contributes to, not an error to average away. Scoped to the
ten named deliveries in the table above: this write-up's first attempt
(commit `0584a66`, 2026-09-07T01:47:30Z) said nine settled verify verdicts,
because it missed that `chore-verify-followups` had already settled
(`.orc/chore-verify-followups/journal.jsonl` `FACT-ASSURE-SETTLED` seq 16,
`01:37:18Z` — ten minutes before that commit); the verify seat that rejected
the attempt recounted correctly to ten. Separately, and outside this scope: a
whole-ledger join of every run's `FACT-ASSURE-SETTLED` fact against its own
`times.jsonl` `observed_at` (not limited to the ten named deliveries) finds
**eleven** settled verify verdicts on 2026-09-07 and **thirteen** across
2026-09-06/07 combined, as of `2026-09-07T02:07:16Z` (this correction's own
recount, captured immediately before committing it). The eleventh-for-
2026-09-07 is `task-m5-002`/`playbook` (`gh-pr:279`,
`.orc/task-m5-002/journal.jsonl` seq 16, `google-antigravity/gemini-3.8-flash`,
settled `01:54:14Z`) — a delivery outside this card's own named Sources list,
which settled after the rejecting verify seat's recount and before this
correction's. Every count above states its scope (the ten named deliveries,
or the whole ledger) and its cutoff, because an integer against a ledger
still being written to is unfalsifiable without both.

What does not move with any of this: across the entire ledger (71 top-level
`FACT-ASSURE-SETTLED` facts, every run directory, all-time — not just
2026-09-06/07), zero recorded `openai-codex` as the verify model, checked
directly against each fact's own `executor-identity/v1.model` (top-level
facts only; a `DEC-*` entry's `basis` array embeds a duplicate copy of the
fact it cites, which a naive text search double-counts). Every 2026-09-06/07
settled verify verdict — all thirteen of them — ran on
`google-antigravity/gemini-3.8-flash`. That is the fact the `ADR-0007` `V7`
amendment argument below rests on; the day-count is illustration, not load.

### The two external-candidate-lane runs are not evidence about `.omp/agents/ship.md`

`adopt-270-attempt-binding` and `docs-external-candidate-lane` both record
`role: ship` with `session_ref: omp:watchtower` and `model:
xai-oauth/grok-4.6` — the watchtower's own session filing the ship-seat
attestation for a PR (#270) that "arrived without a ledger run, from an
adopter session" (run intent text, `FACT-INTENT-SUBMITTED` seq 1), per the
external-candidate lane `docs-external-candidate-lane` itself documents.
Neither run went through `.omp/agents/ship.md`. This is the documented
fallback path (`orc history docs-external-candidate-lane` seq 16's own
findings confirm the lane's five rules, including "ship-seat adoption onto a
current base precedes judgment"), not a seat-discipline lapse — but it means
these two rows say nothing about whether the real `ship.md` agent stays on
`anthropic` in practice; only the eight rows that ran an actual
`.omp/agents/ship.md`-driven `task` spawn do. All eight of those ran
`anthropic/claude-sonnet-5` (in full or bare form — see below). No
self-assurance was observed in either adopted run: the independent verify
seats (`VerifyAdopt270`, `VerifyLaneDoc`) ran in separate sessions from
`omp:watchtower` and derived their own sha per `PLAYBOOK-AGENT-CLI`.

### Hook guards did not exist yet; discipline held by agent definition and convention only

`ADR-0007`'s Costs section is explicit: "the hook-enforced rules
(`TASK-M5-005`) are only as strong as OMP's own `tool_call` guard mechanism...
before any rule is trusted to fire." `TASK-M5-005` (`.omp/extensions/
orc-seat.ts`) was `EXECUTING`, not `ACCEPTED`, in the ledger throughout every
run in the table above (`orc --limit 0`), and `master`'s tree has no
`.omp/extensions/` path at all (`git ls-tree -r master --name-only | grep
omp/extensions` — no output). Every seat-discipline observation above —
verify-cannot-push, no self-assurance, ship-in-its-own-worktree, record-
before-yield — held because the agent definitions (`ship.md`/`verify.md`)
and the seats' own compliance said so, not because a blocking hook enforced
it. Say this plainly: nothing in this wave tests whether `TASK-M5-005`'s
hook will actually fire correctly once it exists; that is still an open,
undelivered card with its own red-then-green obligation.

### A self-report format inconsistency, tying into the report's §7b finding

The recorded `model` string for the ship seat is not consistent across runs
that should be identical: `m5-omp-harness-pilot`, `fix-verify-seat-fallback`,
`task-m5-006`, and `task-m5-001` recorded the full `anthropic/claude-sonnet-5`
(or `:medium`), while `task-m5-003`, `fix-254-active-filter`,
`fix-266-reobservation`, and `fix-262-docs-polish`'s second attempt recorded
the bare `claude-sonnet-5` with no provider prefix. Nothing in the ledger
resolves whether this is the same model reported two ways or a genuine
difference — this is exactly the gap the capability report's §7b names:
`executor-identity/v1.model` is "provenance, not proof," self-typed by the
seat, not derived or verified by the harness. Recorded here as record-silent
on which it is, not resolved.

## 3. What it cost

| Run | Ship wall time | Verify wall time | Attempts |
|---|---|---|---|
| `m5-omp-harness-pilot` | 12m24s | 8m2s | 1 |
| `fix-verify-seat-fallback` | 8m38s | 4m30s | 1 |
| `adopt-270-attempt-binding` | 20m1s | 9m29s | 1 |
| `docs-external-candidate-lane` | 22m38s | 6m44s | 1 |
| `fix-262-docs-polish` | 16m55s + 5m32s | 8m29s + 6m5s | 2 |
| `task-m5-003` | 26m53s | 1m52s | 1 |
| `fix-254-active-filter` | 17m50s | 7m25s | 1 |
| `task-m5-006` | 30m46s | 44s | 1 |
| `fix-266-reobservation` | 36m20s | 47s | 1 |
| `task-m5-001` | 56m29s | 1m36s | 1 |
| `chore-verify-followups` | 20m10s | 1m8s | 1 |

(Computed from each run's `times.jsonl` `observed_at` against
`FACT-EXEC-STARTED`/`FACT-EXEC-SETTLED`/`FACT-ASSURE-STARTED`/
`FACT-ASSURE-SETTLED` seq numbers. `task-m5-006` and `fix-266-reobservation`'s
sub-minute verify times are the ledger's own timestamps, not an estimate —
see the flake note below for what actually ran inside that window.)

`task-m5-001`, `fix-262-docs-polish`, `task-m5-003`, `fix-254-active-filter`,
`task-m5-006`, and `fix-266-reobservation` were all dispatched (`DEC-DISPATCH`)
within the same wall-clock second, `2026-09-07T00:34:40Z` — six ship works
fired by one kernel decision batch. All six show a real `FACT-EXEC-SETTLED`
with a genuine PR artifact; none silently died at `rc=0`. This does not
contradict the capability report's §7a finding (concurrent `omp -p`
processes can silently no-op under load): a shared dispatch-decision
timestamp is the kernel's decision to allow six works to proceed, not proof
that six OMP processes were literally executing concurrently against the
same account at that instant — the ledger cannot distinguish "dispatched
together, run sequentially soon after" from "true process concurrency," so
this is an absence of the failure mode in the recorded outcomes, not a
retest of §7a.

`chore-verify-followups` (PR #278, merged, head
`7b0e789288654c5e6ebf0b2ba2a888122e089df1`) has a real `FACT-EXEC-SETTLED`
(`01:36:10Z`, seq 10) and `FACT-ASSURE-SETTLED` (`01:37:18Z`, seq 16,
accepted, `google-antigravity/gemini-3.8-flash`) — ship wall 20m10s
(`01:16:00`→`01:36:10`), verify wall 1m8s (`01:36:10`→`01:37:18`).
`gh pr view 278` confirms `mergedAt 2026-09-07T01:40:20Z`.

## 4. Newly observed reliability events

Appended to `docs/delivery/seat-reliability.md` under `## 2026-09-07`, same
day as observed, per `T5`/`T6`:

- The `V7` pairing described above (`google-antigravity/gemini-3.8-flash`
  became the standing verify practice across the whole 2026-09-07 wave,
  not a one-off substitution).
- A live, independent hit of the `test_hung_observer` flake (open issue
  #232) by `VerifyM5006` during PR #275's audit — a first full-suite
  `bash scripts/check.sh` run failed on it before a second run passed.

No other model hang, rate-limit, or hook misfire is evidenced in any journal
read for this write-up beyond the four entries `fix-verify-seat-fallback`
already logged on 2026-09-06.

## Ambiguities encountered

- `ADR-0007`'s `V7` ruling names `openai-codex` specifically as the verify
  family; observed practice across the entire 2026-09-07 wave is
  `google-antigravity`. This looks like it has crossed from a named,
  time-boxed deviation into a de facto contract change that has not been
  formally amended. Amending `ADR-0007` itself is outside this card's scope
  (`TASK-M5-008` — the log and the write-up only); flagged here per
  `AGENTS.md` rule 4 rather than silently deviating further.
- Whether `claude-sonnet-5` (bare) and `anthropic/claude-sonnet-5` (prefixed)
  recorded across different runs denote the same model is not resolvable
  from the ledger alone.

## Not covered

- `TASK-M5-005`'s hook guards firing correctly: the card has not shipped as
  of this write-up (`EXECUTING`, not `ACCEPTED`); nothing here tests it.
- A formal amendment to `ADR-0007`'s `V7` wording: named above as needed, not
  performed by this card.
- Any run outside the eleven listed above; this write-up does not claim to
  characterize the entire M5 migration, only the pilot and the wave that
  followed it, per this card's own scope.
