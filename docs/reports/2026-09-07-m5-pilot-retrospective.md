---
id: REPORT-2026-09-07-M5-PILOT-RETROSPECTIVE
type: report
status: current
authority: informative
description: Pilot write-up for the M5 OMP-first delivery migration — whether TASK-M5-001's capability predictions held, whether seat discipline held under real traffic, what the seat-hook capability cycle cost, and the counting lesson (issue #285) the milestone produced. Every figure is anchored to a stated commit and instant.
---

# M5 OMP-first delivery — pilot write-up

This is the second half of `TASK-M5-008`. It answers, for a reader with no
prior context, whether the M5 migration to Oh My Pi (OMP) as the primary
delivery harness (`ADR-0007`) is worth adopting further.

## Cutoff anchor

**Every count in this document is as-of `master` commit `692c543a85f8137d305920245e963baed692ae07`, observed at `2026-09-07T12:11:25Z`**, unless a narrower instant or a different commit is stated inline next to that individual figure. The `.orc` ledger is a live, append-only log that several other runs write to concurrently; a count taken from it is only meaningful with the anchor it was taken against, and it is expected to differ — usually grow — if re-run later. That expectation is itself the subject of §4.

Two classes of number appear here:

- **Terminal facts** — a run/attempt that has reached a terminal ledger state (`ACCEPTED`, or `BLOCKED` with `retry-budget-exhausted`) cannot be further mutated by that run. Counts built only from terminal rows are durable and will not change on re-derivation, regardless of when you run the command, because the source rows themselves are frozen. These are marked **(terminal)**.
- **Live-population snapshots** — a whole-ledger join across every run directory, several of which are non-terminal at the anchor. These are marked **(as-of anchor)** and given with the exact command that reproduces them, so a reader re-derives rather than re-trusts.

This document does not narrate its own delivery run's attempt count, verdict, or state; that would be exactly the self-referential defect described in §4.

## 1. Did `TASK-M5-001`'s capability predictions hold?

`TASK-M5-001` (`docs/reports/2026-09-07-omp-capability-test.md`, report `REPORT-2026-09-07-OMP-CAPABILITY-TEST`) ran a five-point capability probe against the installed OMP harness before any seat machinery depended on it, and it named a mechanism list up front (`docs/reports/2026-09-07-omp-capability-test.md:16-19`):

> "OMP enforces seat discipline with native mechanisms (schema rejection, blocking hooks). ... Every one of those mechanisms is an assumption about the installed OMP and observed — an untested capability is not a capability."

The probe's own five-point table (`docs/reports/2026-09-07-omp-capability-test.md:267-299`) recorded: `maxRecursionDepth` and `config.yml` block a nested subagent from spawning its own further subagent (points 4–5, **PASS**), and a killed subagent's `history` remains readable post-abort — supporting an after-the-fact ledger audit (point 3, **PASS**). Point 6 (§ "Correction") found the harness exposes real role identity through `ctx.sessionManager.getBranch()/getEntries()`, reversing an earlier draft's claim that role identity was unreachable from a tool call.

Two predictions from that report were subsequently **falsified by the seat-hook capability cycle** (`TASK-M5-005`, detailed in §3), and the report itself flags this as the open question rather than a settled one (`docs/reports/2026-09-07-omp-capability-test.md:791-794`):

> "The capability question — can a `tool_call` hook enforce any of these five rules soundly — was tested to exhaustion across three escape classes and then negative, returns rather than assumes."

Specifically:

- **Falsified: "a `tool_call` hook can deny a malformed or actually-blocked call."** `TASK-M5-005`'s three independent hook-enforcement runs (`task-m5-005`, `task-m5-005-guards`, `task-m5-005-sensor`) produced nine rejected assurance attempts and zero accepted ones (§3, terminal). Guard escapes were demonstrated live against the installed harness at every attempt: a hook sees only pre-resolution `input.command`/`input.path` strings, not the tool's own resolved semantics, so a guard re-implementing that resolution independently (command-text matching, path canonicalization, URI-scheme adjudication) diverges from the real tool every time the real tool's resolution logic changes shape. Compare `TASK-M5-005`'s closure (`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md:4`): "Capability finding — can an OMP `tool_call` hook enforce a seat rule (record-before-yield, no-self-merge, verify push/commit/comment denial, ship worktree fence)? Tested to exhaustion across hook attempt cycles, negative result, 2026-09-07 (operator ruling) — negative."
- **Falsified: role identity as a trustworthy enforcement input.** The capability report's own correction (point 6, `docs/reports/2026-09-07-omp-capability-test.md:294-303`) established `getBranch()/getEntries()` as readable, but `TASK-M5-005`'s guard attempts against real fixtures showed that readability alone does not make a *hook-enforced* rule sound: the guard still has to independently re-derive "is this candidates set inside the ship's own worktree" from a raw string, and every one of the three escape classes in §3 is exactly that re-derivation going wrong.

What held, unchanged: points 1–2 (schema rejection, blocked-tool-call denial) and points 3–5 (subagent fencing, recursion depth, after-the-fact audit trail) were never contradicted by later probes — they became the three rungs that actually carry seat discipline today (§5), replacing the fourth rung (hook enforcement) that the report correctly flagged as unverified and that `TASK-M5-005` went on to falsify.

## 2. Did seat discipline hold under real seat traffic?

**(terminal)** Eleven M5-related runs reached `ACCEPTED` and are terminal at the anchor; re-deriving this list can only add later-terminalizing runs, never remove or change these eleven:

```
orc --limit 0 | grep -E '^(m5-omp-harness-pilot|fix-verify-seat-fallback|adopt-270-attempt-binding|docs-external-candidate-lane|fix-262-docs-polish|task-m5-003|fix-254-active-filter|task-m5-006|fix-266-reobservation|task-m5-001|chore-verify-followups):'
```

Every accepted work here has an `evidence_refs` pair of `gh-pr:<n>` and `head:<sha>` recorded at `FACT-EXEC-SETTLED`, and every verify verdict carries a distinct `session_ref` from the ship attempt it reviewed (`executor-identity/v1` extension) — the structural check the seat model rests on: no run in this list shows the same session both shipping and verifying its own candidate.

Two shapes of evidence, both real:

**Discipline working as designed.** `fix-262-docs-polish` attempt 1 (seq 16) was rejected for a factual grounding error — the ship candidate claimed its example JSON matched `.orc/docs-pstack-assurance-depth/journal.jsonl` seq 16 byte-for-byte; it did not, conflating a `PORT-JOURNAL` envelope's `data`-nested fields with the top-level shape. Attempt 2 (seq 26) cured exactly that defect and was accepted, citing the real seq 16 scalars. This is the seat model doing its job: an independent verify seat caught a shipped-but-wrong claim before it reached `master`, at the cost of one extra ship/verify round trip.

**Where it needed operator judgment beyond mechanical retry.** Three real cases surfaced this milestone:

1. **`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md`'s own re-delivery pattern.** `TASK-M5-005`'s underlying hook capability was tested across three separate run identities (`task-m5-005`, `task-m5-005-guards`, `task-m5-005-sensor`), each exhausting its own three-attempt budget without landing (§3). Rather than dispatch a fourth re-delivery run chasing a fourth escape class, the operator closed the capability question with a negative result and retired the mechanism — a judgment call about when continued retrying stops being productive, not something the retry-budget mechanism decides on its own.
2. **`docs-hook-capability-limit` → `docs-hook-limit-r2`.** The first run's own three attempts (seq 16/26/36, `.orc/docs-hook-capability-limit/journal.jsonl`) were all rejected, and `ADR-0007`'s hook-retirement amendment records the correction explicitly: "Operator ruling, 2026-09-07 (amended in-flight after an initial overstatement of what branch protection can do — see rung 2)" (`docs/decisions/ADR-0007-omp-primary-harness.md:255`, § Consequences). The claim was over-broad on first pass and was narrowed before the replacement run (`docs-hook-limit-r2`, `ACCEPTED`, attempts=1) landed it.
3. **Frozen-candidate gap (issue #289, filed 2026-09-07, `OPEN` at anchor).** A ship candidate can freeze at `orc record --outcome` and enter `ASSURING`, and the ledger has no affordance to rebind that candidate if a *sibling* run's settlement invalidates a present-tense claim in it seven minutes later — `record_execution_outcome_entry` (`src/orc_werk/cli/config.py:1259-1264`) rejects a second recorded outcome unconditionally, by design (`INV-021`). The only two options inside the run are to let a now-inaccurate candidate go to verify, or force a reject and burn the attempt budget on a candidate that was correct when frozen. The sanctioned recovery — operator `--abandon-work`, re-ship under a new run on the same branch/PR — works, but it is not something the seat model resolves without an operator stepping in. This is a real, still-open product gap, not a one-off; issue #289 proposes a first-class "superseded-by-external-change" affordance as the fix.

No case above required relaxing tool restriction, branch protection, or the after-the-fact audit trail themselves — all three held everywhere they were exercised in this wave. What needed intervention was retry-budget policy and candidate-freeze mechanics around those three rungs, not the rungs.

## 3. What did the seat-hook capability cycle cost, and what did it teach?

**(terminal)** `TASK-M5-005`'s hook-enforcement capability was probed across three run identities, nine total ship attempts, nine rejected `FACT-ASSURE-SETTLED` verdicts, zero accepted:

```
python3 - <<'PY'
import json, glob
n_rej = n_acc = 0
for j in ("task-m5-005", "task-m5-005-guards", "task-m5-005-sensor"):
    for line in open(f".orc/{j}/journal.jsonl"):
        d = json.loads(line)
        if d.get("kind") == "fact" and d.get("id") == "FACT-ASSURE-SETTLED":
            v = d["data"]["verdict"]
            n_rej += v == "rejected"
            n_acc += v == "accepted"
print("rejected:", n_rej, "accepted:", n_acc)
PY
```

Wall time, ship + verify attempts across the same three journals (`observed_at` deltas between successive `FACT-*-SETTLED` seq pairs in each `times.jsonl`): **~526 minutes total** (≈326.7 min across 9 ship attempts, ≈199.4 min across 9 verify attempts) — reproducible via `.orc/task-m5-005/times.jsonl`, `.orc/task-m5-005-guards/times.jsonl`, `.orc/task-m5-005-sensor/times.jsonl` joined on `seq` against each journal's ship/verify attempt boundaries.

Three escape classes, each independently demonstrated live against the installed harness, the third **introduced by the fix for the second**:

1. **Command-text bound (issue #290).** `task-m5-005` seq 26: a guard requiring an `orc record` invocation accepted command text that merely *mentions* `orc record`. A fresh live OMP session with the hook active ran `echo fake-orc-record --command "orc record run-x --work w --verdict accepted"` and successfully yielded `{result:"bypass-yield-succeeded", recorded:true}` — the hook never distinguished "text containing the words `orc record`" from "a bash call that actually invokes it." `task-m5-005-guards` seq 16 reproduced the same class against a rewritten guard set: a backslash-escaped `g\h pr merge 999 --squash` and `g\it push origin master:verify-escape` both passed the hook (`.omp/extensions/orc-seat.ts:437-449` and `:633-636` only match the literal tokens `gh`/`git`, and the shell strips the backslash before exec). Root cause per issue #290: "a `tool_call` hook receives unresolved arguments (`event.input.command` is a raw string, `event.input.path` a raw target) and requires its own resolution semantics, and every divergence between the hook's guess and the harness's real resolution is an escape (issue #290) — the shell is not Turing-complete: no text predicate establishes program, argv, or effect."
2. **Path canonicalization (issues #296/#297).** `task-m5-005-guards` seq 26: the retained worktree fence compared unresolved `path.resolve` strings, so a real ship subagent escaped it three ways at the same head — a symlink write/edit (`.omp/extensions/orc-seat.ts:153-177`), a colon-split path that drops everything after the first `:` (`write ./safe:/../../outside-probe/colon-split-escape.txt`, `orc-seat.ts:123-129`), and a `://`-containing path skipped entirely (`write ./colon://../../outside-probe/scheme-skip-escape.txt`) — while the same fence also *denied* a legitimate own-worktree path on a case-insensitive filesystem (`case-inside.txt`, `LiveHookProbe.jsonl:28-30`).

`ADR-0007`'s hook-retirement amendment (`docs/decisions/ADR-0007-omp-primary-harness.md:255-274`, ratified 2026-09-07) draws the conclusion directly:

> "Four full prior invariants rest on tool `write`/`edit`. All four guards that inspect **structure** hold [...] Three escape classes, each found a different target class, at a different depth [...] The pattern is not seat quality — it is the enforcement mechanism: a `tool_call` hook receives unresolved arguments [...] and requires its own resolution semantics [...] the shell is not Turing-complete."

The mechanism was retired, not merely descoped: PR #300 (`hook-retire-decision`, merge state landed at head, `docs/decisions/ADR-0007-omp-primary-harness.md`) and PR #299 (`docs/delivery/M5-omp-first-delivery.md`, `README.md`, `docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md`, `docs/delivery/task-cards/TASK-M5-008-seat-reliability-and-pilot-writeup.md`) removed the `.omp/extensions/orc-seat.ts` hook and the seat-hook rung from every card and delivery doc that referenced it, replacing it with the three rungs in §5. What the cycle taught, in one sentence: **a guard that has to independently re-implement a tool's own argument resolution will always be at most one guard-tightening cycle behind that tool**, and issue #298 is the concrete proof — it exists only because the fix for #296/#297 introduced a new resolution path the real tool didn't share.

## 4. The counting lesson

Issue #285 (`OPEN`, filed 2026-09-07) is the milestone's most transferable finding, independent of the seat-hook result above:

> "No whole-ledger aggregate query; hand-rolled FACT-ASSURE-SETTLED count on a live population is a **missing CLI affordance**, not a seat defect. Three separate verify seats each spent independent effort hand-joining `journal.jsonl` × `times.jsonl`, and each produced a different wrong answer."

The mechanism: a retrospective describing a *live, still-growing* ledger population, written from *inside* that population (a run that is itself one more row in the same ledger), fixes a number in prose at write time. The next settlement — anywhere in the ledger, not necessarily in the retrospective's own run — invalidates that number before anyone reads the document. This is not hypothetical for this milestone: two predecessor runs of this exact write-up (`task-m5-008`, `task-m5-008-writeup-r2`) were rejected six times combined, and at least two of those rejections were the retrospective's own count falsified by a settlement that landed after the number was written but before the verify seat read it.

Concretely, at this document's anchor (`2026-09-07T12:11:25Z`, `692c543`), a whole-ledger join of every settled verify verdict looks like this:

```
python3 - <<'PY'
import json, glob
n = {"accepted": 0, "rejected": 0}
for j in glob.glob(".orc/*/journal.jsonl"):
    for line in open(j):
        d = json.loads(line)
        if d.get("kind") == "fact" and d.get("id") == "FACT-ASSURE-SETTLED":
            n[d["data"]["verdict"]] += 1
print(n)
PY
```

**As-of `2026-09-07T12:11:25Z`, this returns `{'accepted': 123, 'rejected': 50}` (173 total).** Running the identical command five minutes later, or five minutes earlier, returns a different total — several runs visible in `orc --limit 0` at the same anchor are non-terminal (`EXECUTING`/`ASSURING`). That is not a defect in the command; it is the correct behavior of a query over a live population, and it is exactly why this number is presented here with its own command and its own instant rather than folded into prose as a fact about "the M5 milestone." A milestone-scoped count (§5) is safe to state plainly only because the milestone's own runs are individually terminal (§2, §3) — the *whole-ledger* count above is not, and never will be while the ledger is in use.

The proposed fix (issue #285's own recommendation) is mechanical, not procedural: a first-class `orc` census/aggregate verb that computes exactly this kind of whole-ledger join server-side, tags its output with the observation instant it ran at, and refuses to be quoted without that tag — so a future retrospective's author re-runs a command instead of re-deriving one from three `jq` invocations by hand under time pressure.

## 5. What M5 delivered

`docs/delivery/M5-omp-first-delivery.md:198-214` (§ "The eight cards") names the eight TASK-M5 cards and their delivery vehicles. Six carry a terminal `ACCEPTED` ledger settlement as of the anchor **(terminal)**, each with a `gh-pr:<n>` + `head:<sha>` evidence pair recorded at settlement (reproduce with `orc verdict <run>` for each name below): `TASK-M5-001`↔run `task-m5-001`; `TASK-M5-002`↔run `task-m5-002`; `TASK-M5-003`↔run `task-m5-003`; `TASK-M5-004`↔runs `m5-omp-harness-pilot` + `fix-verify-seat-fallback` (delivered by the pilot PR itself, per `docs/delivery/M5-omp-first-delivery.md:205-206,309-310`); `TASK-M5-006`↔run `task-m5-006`; `TASK-M5-007`↔run `task-m5-007-r3`. `TASK-M5-005` does not carry an `ACCEPTED` settlement and will not: its terminal disposition is the negative capability finding in §3, which is itself its deliverable per its own closure section (`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md:89-152`, dated 2026-09-07 — "the capability finding above is the deliverable this card closes with"). That is seven of the eight TASK-M5 cards with a terminal, dated disposition; this document is the seventh, delivering `TASK-M5-008`'s write-up half (its seat-reliability half already landed via PR #268, per `docs/delivery/M5-omp-first-delivery.md:308-310`).

Seat discipline today rests on three rungs, per `ADR-0007`'s ratified account (`docs/decisions/ADR-0007-omp-primary-harness.md`, § Consequences, `docs/decisions/ADR-0007-omp-primary-harness.md:255-274`) rather than the four originally proposed:

1. **Tool restriction.** Each seat's OMP agent definition grants only the tools its role needs — `.omp/agents/verify.md:8` lists `tools:` as `read, bash, grep, glob, hub` and explicitly omits `write`/`edit`, so a verify seat structurally cannot mutate the tree it is reviewing. This is enforced by the harness's own tool-availability mechanism (capability report point 2, §1), not by a hook watching for misuse.
2. **GitHub branch protection.** Re-confirmed live at `2026-09-07T12:15:25Z` via `gh api repos/odjhey/orc-werk/branches/master/protection`: `required_status_checks.contexts = ["ci-required"]` (`strict: true`), `enforce_admins.enabled = true`, `allow_force_pushes.enabled = false`, `allow_deletions.enabled = false`. `master` is not writable by a bypassing seat regardless of what a hook would or wouldn't have caught.
3. **After-the-fact ledger audit.** The orc journal (`.orc/<run>/journal.jsonl`) records every attempt's evidence refs and every verdict's findings durably; capability report points 3–5 (§1) confirmed a killed subagent's transcript remains readable post-abort, so a reviewer can always reconstruct what a seat actually did, even from a forcibly-aborted session, without relying on a live guard having caught it in the moment.

The fourth originally-proposed rung — a `tool_call` hook enforcing seat rules in real time — was tested to exhaustion (§3) and retired by operator ruling, landed as PR #300 (`hook-retire-decision`) and PR #299 (`docs/delivery/M5-omp-first-delivery.md` etc.). `docs/delivery/M5-omp-first-delivery.md`'s own acceptance criteria (`docs/delivery/M5-omp-first-delivery.md:242-246,299-303`) name the report basis for this: "`ADR-0007` is accepted and cites the capability-test results, the mechanism (after-the-fact ledger audit, the orc journal), and issues #290/#293/#296/#297/#298 and the three run journals named above."

For a reader deciding whether to adopt this model: the three rungs above held under everything this milestone threw at real seat traffic (§2) without needing a hook at all; the one place a hook was tried, it cost nine rejected attempts and ~526 minutes of combined seat wall time to establish, conclusively, that it could not converge (§3); and the model's biggest operational risk is not seat misbehavior but retrospective-writing discipline over its own ledger (§4) — which is why this document is careful to anchor every count in it.

## Ambiguities encountered

None. The task card and `ADR-0007` gave a consistent account; no contract-level judgment call was required beyond the counting-anchor discipline this document already follows throughout.

## Not covered

- `TASK-M5-004`'s own acceptance details (agent definitions, worktree convention) — out of scope for this write-up; see `docs/delivery/task-cards/TASK-M5-004-omp-agents-and-config.md` directly.
- Issue #293 (per-process rate-limit / usage-limit scoping, deferred, tracked separately from the hook-retirement decision) and issue #288 (operator-abandon vs. retry-exhaustion indistinguishable in the projection) — both open product findings adjacent to this milestone's seat mechanics, neither blocking `TASK-M5-005`'s own closure.
- Bun-test coverage for `.omp/extensions/*` — `TASK-M5-005`'s own closure already discloses this gap; it does not apply post-retirement since the hook file itself is removed.
