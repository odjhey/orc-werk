---
id: PLAYBOOK-ERGO-COEXISTENCE
type: playbook
status: current
authority: informative
description: Running ergo (backlog planning) and orc (delivery ledger) side by side in one repository — division of authority, observer wiring, and conventions for an adopting project.
---

# ergo + orc coexistence

Guidance for a repository that wants [ergo](https://github.com/sandover/ergo)
(a fast, dependency-aware agent backlog) and orc (this delivery ledger)
together. Written 2026-09-03 for handover to an adopting project; informative
only — canonical semantics live in the contracts this document cites.

New to this? `docs/playbooks/agent-onboarding.md` (`PLAYBOOK-AGENT-ONBOARDING`)
is the executable path — a single top-to-bottom checklist an onboarding agent
follows, including this coexistence wiring verified end-to-end in a sandbox.
This document stays the rationale/conventions home it cites from there.

## Why they coexist cleanly

The tools overlap in plumbing (repo-local JSONL journals, work units with
dependencies, claims for parallel agents, agent-recorded results) but not in
purpose:

- **ergo owns "what should be done."** Backlog decomposition, draft → open
  staging, cross-task dependency ordering, the human-readable board, and an
  interview-driven planning skill. Its `done` is an *agent's own assertion*.
- **orc owns "what was actually done, and who vouched for it."** Dispatch,
  attempt budgets, candidate identity, and — the part ergo deliberately lacks
  — independent verification: execution settlement is not acceptance
  (`INV-003`), the verify seat is never the ship seat, and verdicts bind only
  against corroborated candidate identity.

Mechanically there is no collision: `.ergo/` and `.orc/` are separate
directories, separate CLIs, each independently git-tracked or ignored.

## The lifecycle seam

```
ergo (planning)                          orc (delivery accountability)
draft → open → ready ──── claim ──────▶ orc dispatch (run per task)
                                          EXECUTING → record --outcome
                                          ASSURING  → independent verdict
        ◀── done / fail + result ─────── ACCEPTED / BLOCKED / CANCELLED
            (evidence: run id, PR, head sha)
```

An ergo task is the *ticket*; the orc run is the *record*. A ready ergo task
is claimed by whoever spawns the delivery lane, an orc run is opened for it,
and the outcome flows back to ergo automatically (below).

## The one load-bearing rule

**ergo's terminal task states are a projection of orc outcomes, never an
authority.** No human or agent marks an ergo task `done` by hand; `done` and
`fail` are written only by the observer wiring below, carrying the orc run id
and candidate identity as evidence. This is the same write-only posture orc's
Beads mirror holds (`INV-014`): the board reads well precisely because it
cannot disagree with the ledger.

The caveat to state plainly: ergo itself lets a claiming agent self-declare
`done`. Coexistence preserves orc's verification guarantees only by
convention — the observer as sole writer of terminal ergo states — not by
enforcement on ergo's side. Write the convention into the adopting repo's
agent instructions.

## Wiring (no code on either side)

Observer hooks (`SCN-018`) are the integration mechanism — push-model egress,
fire-and-forget, at-most-once, exactly the posture `ADR-0005` prescribes.

1. **Run naming**: `run_id` = the ergo task id (orc's run-id namespace
   convention absorbs this; see the CLI reference's run-id section). Intent
   text = the ergo task title plus body, written for a reader with no context.
2. **Observers in the run config** (or the repo's `.orc/profile.json` so every
   run inherits them):

```json
{
  "observers": {
    "on_verdict": {"command": ["./scripts/ergo-on-verdict.sh"], "timeout_seconds": 15},
    "on_blocked": {"command": ["./scripts/ergo-on-blocked.sh"], "timeout_seconds": 15}
  }
}
```

3. **The scripts** (in-repo, per `SCN-018`'s containment rule; the triggering
   fact arrives as JSON on stdin — inspect `orc history <run>` output for the
   exact envelope your version emits, and note the observer-cwd caution in
   the CLI reference's observer section):

```bash
#!/usr/bin/env bash
# scripts/ergo-on-verdict.sh — sole writer of terminal ergo states.
set -euo pipefail
fact=$(cat)
run=$(jq -r '.delivery_run_id // .run_id' <<<"$fact")
verdict=$(jq -r '.verdict // .data.verdict' <<<"$fact")
task="$run"   # run_id == ergo task id by convention 1
if [ "$verdict" = "accepted" ]; then
  ergo result "$task" "accepted via orc run $run" || true
  ergo done "$task" || true
else
  ergo result "$task" "verdict=$verdict via orc run $run — see orc report $run" || true
fi
```

   `on_blocked` maps to `ergo fail` (budget exhausted / inconclusive) with the
   `blocked_reason` in the result text. Operator cancellation flows forward
   the same way: `orc cancel` → the adopting repo's cancel note → `ergo
   cancel`, so the board never shows phantom in-flight work.

## Conventions (write these into the adopting repo)

1. **Dependencies live in ergo only.** An orc run is one task (single work)
   unless a task genuinely is a mini-DAG. Never encode the same edges twice —
   a split-brain DAG is worse than either tool alone.
2. **Phase the skills.** Planning agents use ergo's backlog-planning skill
   (its interview/frontier-rounds method is good); seat agents use the
   orc-ledger skill (`orc record --outcome` / `--verdict`, seat discipline
   per `PLAYBOOK-AGENT-CLI`). An agent holding an ergo claim is not thereby a
   verify seat — the seats are orc's.
3. **Terminal ergo states come only from the observer.** Hand-marking `done`
   is the one way to break the whole arrangement.
4. **Wake stays orc-side.** Blocking callers use `orc dispatch --wait`
   (`SCN-017`); ergo's `list --ready` is for planning views, not delivery
   polling.

## Relationship to the Beads board

ergo enters the same slot Beads occupies for orc-werk itself: a write-only
projection surface (`PLAYBOOK-PORTFOLIO-COCKPIT`). A repo can run either
board, or both. Any promotion of board state to *authority* over the ledger
is a separate operator ruling — the dormant issue #47 question — and nothing
in this playbook grants it.

## Trial shape for an adopting repo

Start with one epic: plan it in ergo, drive each task through an orc run with
the observer wiring above, and judge two things after a week: (a) did the
board ever disagree with `orc` (bare) — if yes, a hand-write leaked; (b) did
the observer evidence (run id + PR + head sha on every `done`) make the
board's history auditable without opening orc at all. If both hold, the
coexistence is paying rent.
