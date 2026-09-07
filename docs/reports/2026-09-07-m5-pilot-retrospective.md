---
id: REPORT-2026-09-07-M5-PILOT-RETROSPECTIVE
type: report
status: current
authority: informative
description: Pilot write-up for the M5 OMP-first delivery migration — whether TASK-M5-001's capability predictions held, whether seat discipline held under real traffic, what the seat-hook capability cycle cost, and the counting lesson (issue #285) the milestone produced. Every figure is anchored to a stated commit and instant, and every anchored figure is re-derivable by a published, output-invariant command.
---

# M5 OMP-first delivery — pilot write-up

This is the second half of `TASK-M5-008`. It answers, for a reader with no
prior context, whether the M5 migration to Oh My Pi (OMP) as the primary
delivery harness (`ADR-0007`) is worth adopting further.

## Cutoff anchor

**Every count in this document is as-of `master` commit `692c543a85f8137d305920245e963baed692ae07`, observed at `2026-09-07T12:11:25Z`**, unless a narrower instant or a different commit is stated inline next to that individual figure. The `.orc` ledger is a live, append-only log that several other runs write to concurrently; a count taken from it is only meaningful with the anchor it was taken against.

Two classes of number appear here:

- **Terminal facts** — a run/attempt that has reached a terminal ledger state (`ACCEPTED`, or `BLOCKED` with `retry-budget-exhausted`) cannot be further mutated by that run. Counts built only from terminal rows are durable and will not change on re-derivation, regardless of when you run the command, because the source rows themselves are frozen. These are marked **(terminal)**.
- **As-of, anchor-filtered joins** — a whole-ledger join across every run directory, filtered to facts whose own `observed_at` (from that run's `times.jsonl`) is at or before the anchor instant. A command of this shape is **output-invariant**: re-running it next week reproduces exactly the anchor's figure, because a settlement that lands after the anchor gets a later `observed_at` and is excluded, never included, by the filter. These are marked **(as-of anchor, invariant)** and given with the exact command that reproduces them.

This document does not narrate its own delivery run's attempt count, verdict, or state; that would be exactly the self-referential defect described in §4.

## 1. Did `TASK-M5-001`'s capability predictions hold?

`TASK-M5-001` (`docs/reports/2026-09-07-omp-capability-test.md`, report `REPORT-2026-09-07-OMP-CAPABILITY-TEST`) asks two genuinely different questions, and this section keeps them apart: (a) did the report's own five numbered *capability points* hold, and (b) separately, does a `tool_call` hook soundly enforce any of the five *rules* `TASK-M5-005` set out to encode. Conflating the two — assigning capability points to hook rules, or treating one list's verdict as the other's — was itself a defect in an earlier draft of this document; this section does not repeat it.

### 1a. The five capability points (`docs/reports/2026-09-07-omp-capability-test.md`)

| # | Point (heading line) | Result |
|---|---|---|
| 1 | git-push denial via a blocking hook (`:63`) | **Narrow PASS, later corrected.** The exact, unescaped probe command was denied on 2026-09-06 (`:82-85,116-124`). The 2026-09-07 Correction (`:126-154`) withdraws the generalization: no shell-escaped variant was ever tried, and `task-m5-005-guards` seq 16 supplies the counterexample — `g\it push origin +master` bypassed the identically-shaped guard because the shell strips the backslash the guard's text match relies on. The actual enforcement surface for "no direct write to `master`" is server-side branch protection, not this hook. |
| 2 | write-outside-fence hook / worktree fencing (`:156`) | **PASS for the mechanism tested 2026-09-06, superseded 2026-09-07.** The card's premise (OMP auto-creates a ship worktree) was empirically false and corrected (`:158-183`); the fence itself proved red-then-green for the shape tested (`:190-220`). §9 of the same report (`:601-625`) shows this same guard, once actually shipped in `TASK-M5-005`, was defeated twice more by path-canonicalization and scheme-adjudication escapes — no hook rung survives past this point either. |
| 3 | `outputSchema` + `schemaMode: strict` rejects a missing field (`:222`) | **PASS, unaffected** (`:261-265`). A kernel-level rejection independent of model cooperation — the mechanism `ship.md`/`verify.md`'s own `output:` schemas already rely on. |
| 4 | `task.maxRuntimeMs` kills a stuck process; `history://` survives the abort (`:267`) | **PASS, unaffected** (`:305-309`). Supports the after-the-fact audit rung (§5 below). |
| 5 | transcript durability across a process restart (`:311`) | **PASS, unaffected** (`:343-347`). Also supports the audit rung. |

Points 3–5 held exactly as predicted and were never contradicted by any later probe. Points 1–2 each began as a real, narrow PASS and were each subsequently corrected or superseded once tested adversarially — neither survives as a hook-enforcement mechanism, though point 2's fencing *behavior* (red-then-green, absent adversarial escaping) was genuinely observed on 2026-09-06.

### 1b. The five hook rules (`TASK-M5-005`)

A separate question: can a `tool_call` hook soundly enforce the rule set `TASK-M5-005` was scoped to encode — record-before-yield, no subagent runs `gh pr merge`, verify-role push/commit/comment/review denial, and the ship worktree fence (`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md:31-52`; the capability report's own final answer refers to these collectively as "the five rules" once split by escape class, `docs/reports/2026-09-07-omp-capability-test.md:645`). The capability report's own conclusion (`:644-654`), reached after three independent verify seats, three escape classes, and nine rejected attempts (§3 below):

> "Final answer: no. A `tool_call` hook does not soundly enforce any of the five rules `TASK-M5-005` set out to encode, including the one (structural, cwd-derived fencing) that looked most tractable after this report's original §2."

This is the answer `ADR-0007`'s own hook-retirement amendment (`docs/decisions/ADR-0007-omp-primary-harness.md:570-577`) and `TASK-M5-005`'s own closure (`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md:89-100`) both restate. It is not a re-litigation of §1a's five points — points 3–5 are unaffected by it, and it is orthogonal to whether role identity is readable (`:349-433`, corrected 2026-09-07: readable via `ctx.sessionManager.getEntries()`, but readability of role does not make command *semantics* enforceable, `:435-515`).

## 2. Did seat discipline hold under real seat traffic?

**(terminal)** Eleven M5-related runs reached `ACCEPTED` and are terminal at the anchor; re-deriving this list can only add later-terminalizing runs, never remove or change these eleven:

```
orc --limit 0 | grep -E '^(m5-omp-harness-pilot|fix-verify-seat-fallback|adopt-270-attempt-binding|docs-external-candidate-lane|fix-262-docs-polish|task-m5-003|fix-254-active-filter|task-m5-006|fix-266-reobservation|task-m5-001|chore-verify-followups):'
```

Every accepted work here has an `evidence_refs` pair of `gh-pr:<n>` and `head:<sha>` recorded at `FACT-EXEC-SETTLED`, and every verify verdict carries a distinct `session_ref` from the ship attempt it reviewed (`executor-identity/v1` extension) — the structural check the seat model rests on: no run in this list shows the same session both shipping and verifying its own candidate.

Two shapes of evidence, both real:

**Discipline working as designed.** `fix-262-docs-polish` attempt 1 (seq 16) was rejected for a factual grounding error — the ship candidate claimed its example JSON matched `.orc/docs-pstack-assurance-depth/journal.jsonl` seq 16 byte-for-byte; it did not, conflating a `PORT-JOURNAL` envelope's `data`-nested fields with the top-level shape. Attempt 2 (seq 26) cured exactly that defect and was accepted, citing the real seq 16 scalars. This is the seat model doing its job: an independent verify seat caught a shipped-but-wrong claim before it reached `master`, at the cost of one extra ship/verify round trip.

**Where it needed operator judgment beyond mechanical retry, or surfaced friction.** Four real cases this milestone:

1. **`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md`'s own re-delivery pattern.** `TASK-M5-005`'s underlying hook capability was tested across three separate run identities (`task-m5-005`, `task-m5-005-guards`, `task-m5-005-sensor`), each exhausting its own three-attempt budget without landing (§3). Rather than dispatch a fourth re-delivery run chasing a fourth escape class, the operator closed the capability question with a negative result and retired the mechanism — a judgment call about when continued retrying stops being productive, not something the retry-budget mechanism decides on its own.
2. **`docs-hook-capability-limit` → `docs-hook-limit-r2`.** The first run's own three attempts (seq 16/26/36, `.orc/docs-hook-capability-limit/journal.jsonl`) were all rejected, and `ADR-0007`'s **first** 2026-09-07 amendment (`docs-hook-capability-limit`, not the later retirement amendment — see §3) records the correction explicitly: "Operator ruling, 2026-09-07 (amended in-flight after an initial overstatement of what branch protection can do — see rung 2)" (`docs/decisions/ADR-0007-omp-primary-harness.md:436-437`). The claim was over-broad on first pass and was narrowed before the replacement run (`docs-hook-limit-r2`, `ACCEPTED`, attempts=1) landed it.
3. **Frozen-candidate gap (issue #289, filed 2026-09-07, `OPEN` at anchor).** A ship candidate can freeze at `orc record --outcome` and enter `ASSURING`, and the ledger has no affordance to rebind that candidate if a *sibling* run's settlement invalidates a present-tense claim in it seven minutes later — `record_execution_outcome_entry` (`src/orc_werk/cli/config.py:1259-1264`) rejects a second recorded outcome unconditionally, by design (`INV-021`). The only two options inside the run are to let a now-inaccurate candidate go to verify, or force a reject and burn the attempt budget on a candidate that was correct when frozen. The sanctioned recovery — operator `--abandon-work`, re-ship under a new run on the same branch/PR — works, but it is not something the seat model resolves without an operator stepping in. This is a real, still-open product gap, not a one-off; issue #289 proposes a first-class "superseded-by-external-change" affordance as the fix.
4. **`V7` model-family pairing did surface friction.** Two `openai-codex/gpt-5.6-sol` verify spawns against `m5-omp-harness-pilot`'s `docs` work died within seconds of `usage_limit_reached` on 2026-09-06 and recorded nothing to the ledger (`docs/delivery/seat-reliability.md:21-50`); frontmatter model-list order is resolution preference only, and OMP did not fall through to the list's second entry at spawn time on a usage-limit error, so both dead spawns had to be hand-substituted to `google-antigravity/gemini-3.8-flash`, which then completed and was accepted. `ADR-0007`'s own `V7` amendment (`docs/decisions/ADR-0007-omp-primary-harness.md:322-401`) responds directly to this: it drops the specific `openai-codex`-vs-`anthropic` family assignment as a contract-layer requirement, keeping only the underlying invariant — verify runs on a family different from whichever family ship actually used — and reorders `.omp/agents/verify.md`'s own model list (`google-antigravity` first) so a usage-limit death is less likely to strand a spawn in practice. The invariant itself was never violated (every observed verify spawn ran non-Anthropic against an Anthropic ship), but the specific deployment preference did not survive contact with quota reality.

No case above required relaxing tool restriction, branch protection, or the after-the-fact audit trail themselves — all three held everywhere they were exercised in this wave. What needed intervention was retry-budget policy, candidate-freeze mechanics, and model-list ordering around those three rungs, not the rungs.

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

**Wall time — published method, run against the same three journals:**

```
python3 - <<'PY'
import json
from datetime import datetime

def times_map(run):
    m = {}
    with open(f".orc/{run}/times.jsonl") as f:
        for line in f:
            d = json.loads(line)
            m[d["seq"]] = d["observed_at"]
    return m

def parse(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))

total_ship = total_verify = 0.0
for run in ("task-m5-005", "task-m5-005-guards", "task-m5-005-sensor"):
    tm = times_map(run)
    started = started2 = None
    with open(f".orc/{run}/journal.jsonl") as f:
        for line in f:
            d = json.loads(line)
            if d["id"] == "FACT-EXEC-STARTED":
                started = d["seq"]
            elif d["id"] == "FACT-EXEC-SETTLED" and started is not None:
                total_ship += (parse(tm[d["seq"]]) - parse(tm[started])).total_seconds() / 60
                started = None
            elif d["id"] == "FACT-ASSURE-STARTED":
                started2 = d["seq"]
            elif d["id"] == "FACT-ASSURE-SETTLED":
                total_verify += (parse(tm[d["seq"]]) - parse(tm[started2])).total_seconds() / 60
print("ship_minutes=%.1f verify_minutes=%.1f total_minutes=%.1f" % (total_ship, total_verify, total_ship + total_verify))
PY
```

This joins each journal's `FACT-EXEC-STARTED`→`FACT-EXEC-SETTLED` pairs (ship attempts) and `FACT-ASSURE-STARTED`→`FACT-ASSURE-SETTLED` pairs (verify attempts) against `times.jsonl`'s `seq`→`observed_at` map and sums the deltas. Run against `.orc/task-m5-005`, `.orc/task-m5-005-guards`, `.orc/task-m5-005-sensor` (all terminal, so this figure needs no anchor filter): **`ship_minutes=326.7 verify_minutes=199.4 total_minutes=526.1`** — ~526 minutes total, ≈326.7 across the 9 ship attempts, ≈199.4 across the 9 verify attempts.

Three escape classes, each independently demonstrated live against the installed harness, the third **introduced by the fix for the second**:

1. **Command-text bound (issue #290).** `task-m5-005` seq 26: a guard requiring an `orc record` invocation accepted command text that merely *mentions* `orc record`. A fresh live OMP session with the hook active ran `echo fake-orc-record --command "orc record run-x --work w --verdict accepted"` and successfully yielded `{result:"bypass-yield-succeeded", recorded:true}` — the hook never distinguished "text containing the words `orc record`" from "a bash call that actually invokes it." `task-m5-005-guards` seq 16 reproduced the same class against a rewritten guard set: a backslash-escaped `g\h pr merge 999 --squash` and `g\it push origin master:verify-escape` both passed the hook (`.omp/extensions/orc-seat.ts:437-449` and `:633-636` only match the literal tokens `gh`/`git`, and the shell strips the backslash before exec).
2. **Path canonicalization (issues #296/#297).** `task-m5-005-guards` seq 26: the retained worktree fence compared unresolved `path.resolve` strings, so a real ship subagent escaped it three ways at the same head — a symlink write/edit (`.omp/extensions/orc-seat.ts:153-177`), a colon-split path that drops everything after the first `:` (`write ./safe:/../../outside-probe/colon-split-escape.txt`, `orc-seat.ts:123-129`), and a `://`-containing path skipped entirely (`write ./colon://../../outside-probe/scheme-skip-escape.txt`) — while the same fence also *denied* a legitimate own-worktree path on a case-insensitive filesystem (`case-inside.txt`, `LiveHookProbe.jsonl:28-30`).
3. **Scheme adjudication (issue #298), introduced by the fix for class 2.** `task-m5-005-sensor` seq 37: the fix for class 2's `://`-path-dropping bug added a scheme classifier that itself shipped two new escapes against a real `WriteTool.execute` — a case-insensitive `local://` match (`LOCAL_SCHEME_RE = /^local:\/\//i`) against a harness that treats the `local:` prefix case-sensitively, and an unscoped `conflict://<id>` allowed without inspecting the registered marker's `absolutePath` — both landed writes outside the seat worktree.

`ADR-0007` was amended twice on 2026-09-07, in order, and the write-up mislabeling which is which is a defect this document corrects:

1. **First — the `docs-hook-capability-limit` amendment (run `docs-hook-capability-limit`, PR #292, `eea2319`)**, `docs/decisions/ADR-0007-omp-primary-harness.md:407-568`. This is the amendment that split the original four-rule design into four enforcement rungs after `task-m5-005-guards`' first attempt found guards 1/2/3/5 all defeated by command-text escaping, leaving only guard 4 (the cwd-derived worktree fence) as hook-enforceable.
2. **Second — the hook-retirement amendment (operator ruling, PR #300, `b787bd5`)**, `docs/decisions/ADR-0007-omp-primary-harness.md:570-802`. This is the amendment that retires guard 4 too, once `task-m5-005-guards` attempts 2–3 and `task-m5-005-sensor` attempts 1–3 defeated it via path canonicalization and scheme adjudication. Its "canonical reason" states the mechanism precisely (`docs/decisions/ADR-0007-omp-primary-harness.md:598-609`):

> "A `tool_call` hook receives **unresolved arguments**: `event.input.command` is a raw string, never shell argv, the resolved executable, or process identity [...] Soundness for either guard shape requires the harness's **post-resolution** path or command — the actual argv the shell will run, the actual file the write tool will touch after its own scheme/symlink/case handling — and the hook is never handed that. Every attempt to close the gap made the hook re-implement the harness's own resolution semantics from outside the harness, and every divergence between the hook's reimplementation and the harness's real behavior became a fresh escape."

The mechanism was retired, not merely descoped: PR #300 (`hook-retire-decision`, `b787bd5`) landed the ADR-layer retirement, and PR #299 (`docs/delivery/M5-omp-first-delivery.md`, `README.md`, `docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md`, `docs/delivery/task-cards/TASK-M5-008-seat-reliability-and-pilot-writeup.md`, landed at `692c543`) removed the `.omp/extensions/orc-seat.ts` hook and the seat-hook rung from every card and delivery doc that referenced it, replacing it with the three rungs in §5. What the cycle taught, in one sentence: **a guard that has to independently re-implement a tool's own argument resolution will always be at most one guard-tightening cycle behind that tool**, and issue #298 is the concrete proof — it exists only because the fix for #296/#297 introduced a new resolution path the real tool didn't share.

## 4. The counting lesson

Issue #285 (`OPEN`, filed 2026-09-07) is the milestone's most transferable finding, independent of the seat-hook result above:

> "No whole-ledger aggregate query; hand-rolled FACT-ASSURE-SETTLED count on a live population is a **missing CLI affordance**, not a seat defect. Three separate verify seats each spent independent effort hand-joining `journal.jsonl` × `times.jsonl`, and each produced a different wrong answer."

The mechanism: a retrospective describing a *live, still-growing* ledger population, written from *inside* that population (a run that is itself one more row in the same ledger), fixes a number in prose at write time. The next settlement — anywhere in the ledger, not necessarily in the retrospective's own run — invalidates that number before anyone reads the document, unless the number is derived as-of a stated anchor by a command that filters on it.

**(terminal)** This milestone produced its own live example. Two predecessor runs of this exact write-up (`task-m5-008`, `task-m5-008-writeup-r2`) are both terminal (`BLOCKED`, `retry-budget-exhausted`), so this count needs no anchor filter and will not change on re-derivation:

```
jq -rc 'select(.id=="FACT-ASSURE-SETTLED") | .data.verdict' \
  .orc/task-m5-008/journal.jsonl .orc/task-m5-008-writeup-r2/journal.jsonl | sort | uniq -c
```

**Returns `5 rejected`** — 2 in `task-m5-008`, 3 in `task-m5-008-writeup-r2` (confirmed by running the same filter against each journal individually); issue #285 states the same split. **This document's own prior draft, and the operator brief that seeded it, both said six.** That is not a rounding difference — it is the exact defect class this section describes: a hand-carried integer, propagated from a brief into a document rather than re-derived from the ledger, silently drifted from the true count. It is corrected here, 2026-09-07, anchored to the `jq` command above, precisely because re-deriving instead of re-trusting is what this section asks of every other count in this milestone.

Concretely, at this document's anchor (`2026-09-07T12:11:25Z`, `692c543`), a whole-ledger join of every settled verify verdict, filtered to `observed_at` at or before the anchor, looks like this **(as-of anchor, invariant)**:

```
python3 - <<'PY'
import json, glob
from datetime import datetime

ANCHOR = datetime.fromisoformat("2026-09-07T12:11:25+00:00")
n = {"accepted": 0, "rejected": 0, "inconclusive": 0}
for jpath in glob.glob(".orc/*/journal.jsonl"):
    run_dir = jpath.rsplit("/", 1)[0]
    times = {}
    with open(f"{run_dir}/times.jsonl") as tf:
        for line in tf:
            d = json.loads(line)
            times[d["seq"]] = d["observed_at"]
    with open(jpath) as jf:
        for line in jf:
            d = json.loads(line)
            if d.get("kind") == "fact" and d.get("id") == "FACT-ASSURE-SETTLED":
                ts = times.get(d["seq"])
                if ts and datetime.fromisoformat(ts.replace("Z", "+00:00")) <= ANCHOR:
                    n[d["data"]["verdict"]] += 1
print(n)
PY
```

**As-of `2026-09-07T12:11:25Z`, this returns `{'accepted': 123, 'rejected': 50, 'inconclusive': 0}` (173 total).** Unlike an unfiltered scan of `.orc/*/journal.jsonl`, this command's output does not depend on when it is run: every `FACT-ASSURE-SETTLED` record it counts carries its own `observed_at` (joined from that run's `times.jsonl` on `seq`), and the filter excludes anything settled after the anchor. Re-running this exact command next week, next month, or after any number of further settlements reproduces `{'accepted': 123, 'rejected': 50, 'inconclusive': 0}` unchanged, because no fact that already existed at the anchor can un-settle, and nothing that settles later can have an `observed_at` at or before it. A milestone-scoped count (§5 below) is safe to state plainly without this filter only because the milestone's own runs are individually terminal (§2, §3) — the *whole-ledger* count above is not terminal, which is exactly why it needs the anchor filter rather than a bare scan.

The proposed fix (issue #285's own recommendation) is mechanical, not procedural: a first-class `orc` census/aggregate verb that computes exactly this kind of anchor-filtered whole-ledger join server-side and tags its output with the observation instant it ran at, so a future retrospective's author re-runs a command instead of re-deriving one from three `jq` invocations by hand under time pressure — and so a hand-carried integer from an operator brief, like the six-vs-five error corrected above, is never the only source for a milestone count again.

## 5. What M5 delivered

`docs/delivery/M5-omp-first-delivery.md:198-214` (§ "The eight cards") names the eight TASK-M5 cards and their delivery vehicles. Six carry a terminal `ACCEPTED` ledger settlement as of the anchor **(terminal)**, each with a `gh-pr:<n>` + `head:<sha>` evidence pair recorded at settlement (reproduce with `orc verdict <run>` for each name below): `TASK-M5-001`↔run `task-m5-001`; `TASK-M5-002`↔run `task-m5-002`; `TASK-M5-003`↔run `task-m5-003`; `TASK-M5-004`↔runs `m5-omp-harness-pilot` + `fix-verify-seat-fallback` (delivered by the pilot PR itself, per `docs/delivery/M5-omp-first-delivery.md:205-206,309-310`); `TASK-M5-006`↔run `task-m5-006`; `TASK-M5-007`↔run `task-m5-007-r3`. `TASK-M5-005` does not carry an `ACCEPTED` settlement and will not: its terminal disposition is the negative capability finding in §3, which is itself its deliverable per its own closure section (`docs/delivery/task-cards/TASK-M5-005-orc-seat-hook.md:89-152`, dated 2026-09-07 — "the capability finding above is the deliverable this card closes with"). That is seven of the eight TASK-M5 cards with a terminal, dated disposition as of the anchor. `TASK-M5-008` is the eighth; its seat-reliability half already landed via PR #268 (`docs/delivery/M5-omp-first-delivery.md:308-310`), and this document is that card's remaining pilot-write-up deliverable — as stated in the Cutoff-anchor section above, it does not narrate its own run's attempt count, verdict, or state, and reaching a terminal disposition for `TASK-M5-008` itself is not a claim this document makes.

Seat discipline today rests on three rungs, per `ADR-0007`'s hook-retirement amendment (`docs/decisions/ADR-0007-omp-primary-harness.md:570-802`, ratified 2026-09-07) rather than the four originally proposed:

1. **Tool restriction.** Each seat's OMP agent definition grants only the tools its role needs — `.omp/agents/verify.md:8` lists `tools:` as `read, bash, grep, glob, hub`, omitting `write`/`edit` (the agent's own tool list is documented at `docs/reports/2026-09-07-omp-capability-test.md:54-61`, not one of the five numbered capability points in §1a). `ADR-0007:683-709` is explicit about the honest scope of this rung: it forecloses the `write`/`edit` *tools* specifically, and no more. It does **not** mean a verify seat structurally cannot mutate the tree it is reviewing: `bash` stays in verify's tool list (needed for `scripts/check.sh` and throwaway probes) and `bash` is Turing-complete, so `git commit`/`git push`/`gh pr merge` remain reachable through it — live-disproved against a prior draft of this same amendment, where a real verify seat's `bash`-run `touch` succeeded in its own scratch worktree. General mutation by a verify seat remains policy plus the after-the-fact audit (rung 3), with no enforcement rung of its own.
2. **GitHub branch protection.** Re-confirmed live at `2026-09-07T12:15:25Z` via `gh api repos/odjhey/orc-werk/branches/master/protection`: `required_status_checks.contexts = ["ci-required"]` (`strict: true`), `enforce_admins.enabled = true`, `allow_force_pushes.enabled = false`, `allow_deletions.enabled = false`. This blocks every identity, including the repo admin, from writing directly to `master` outside a passing PR — but it exists for `master` only (`ADR-0007:734-746` reconfirms a non-`master` ref, such as a seat's own scratch branch, returns `404 Branch not protected`), and it does not distinguish which seat role pushed, since every seat authenticates as the same GitHub identity.
3. **After-the-fact ledger audit.** The orc journal (`.orc/<run>/journal.jsonl`) records every attempt's evidence refs and every verdict's findings durably; capability report points 4–5 (`docs/reports/2026-09-07-omp-capability-test.md:267-309,311-347`) confirmed a killed subagent's transcript remains readable post-abort, so a reviewer can always reconstruct what a seat actually did, even from a forcibly-aborted session, without relying on a live guard having caught it in the moment. `ADR-0007:747-762` states this plainly: for "the verify seat specifically may not push/commit/comment/review/merge," this audit trail plus convention is the entire guarantee, not a euphemism for one.

The fourth originally-proposed rung — a `tool_call` hook enforcing seat rules in real time — was tested to exhaustion (§3) and retired by operator ruling, landed as PR #300 (`hook-retire-decision`) and PR #299 (`docs/delivery/M5-omp-first-delivery.md` etc.). `docs/delivery/M5-omp-first-delivery.md`'s own acceptance criteria (`docs/delivery/M5-omp-first-delivery.md:296-302`) name the evidence basis for this: `ADR-0007`, the capability-test report, and issues #290/#293/#296/#297/#298 alongside the three run journals named in §3.

For a reader deciding whether to adopt this model: the three rungs above held under everything this milestone threw at real seat traffic (§2) without needing a hook at all; the one place a hook was tried, it cost nine rejected attempts and ~526 minutes of combined seat wall time to establish, conclusively, that it could not converge (§3); and the model's biggest operational risk is not seat misbehavior but retrospective-writing discipline over its own ledger (§4) — which is why this document anchors every count in it, either to a terminal fact or to an as-of instant with a published, invariant re-derivation command.

## Ambiguities encountered

None. The task card and `ADR-0007` gave a consistent account; no contract-level judgment call was required beyond the counting-anchor discipline this document already follows throughout.

## Not covered

- `TASK-M5-004`'s own acceptance details (agent definitions, worktree convention) — out of scope for this write-up; see `docs/delivery/task-cards/TASK-M5-004-omp-agents-and-config.md` directly.
- Issue #293 (per-process rate-limit / usage-limit scoping, deferred, tracked separately from the hook-retirement decision) and issue #288 (operator-abandon vs. retry-exhaustion indistinguishable in the projection) — both open product findings adjacent to this milestone's seat mechanics, neither blocking `TASK-M5-005`'s own closure.
- Bun-test coverage for `.omp/extensions/*` — `TASK-M5-005`'s own closure already discloses this gap; it does not apply post-retirement since the hook file itself is removed.
