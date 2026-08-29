---
id: M3-HARDEN-THE-LOOP
type: milestone
status: draft
authority: normative
description: M3 — close the wedge class the adoption testing exposed; small by design, most of the originally-proposed scope shipped ahead of the milestone.
---

# M3 — Harden the loop

## Context, and why this milestone is small

M2 closed on wild-adoption evidence (`M2-close-the-loop.md`, M2c status
note). The adoption harvest (2026-08-29) drove a delivery burst that
shipped most of what issue #101 originally proposed for M3 *before this
document existed*: the reference-first surfaces (`orc refs`, PR #104; the
crew-report removal, PR #107; the reference-first disposition in
`CONTRACT-DURABILITY`) and the agent-native error surface (error
affordances, PR #108) are already on master. This milestone deliberately
does not re-claim delivered work; it scopes exactly what remains.

**Theme:** make the xatu-class wedge — a run stuck or corrupted by a
rejected/foreign settlement path — structurally impossible, then stop.

## Phase M3b — Wedge-class closure

Two cards, sequential (both touch assurance/verdict semantics; the first
amends the state machine the second relies on).

- `TASK-M3B-001` — verdict inheritance + operator abandon record
  (approved ruling, issue #76; also resolves issue #95). Docs first:
  `STATE-DELIVERY` transition + scenario before kernel code.
- `TASK-M3B-002` — no-mistakes inspect-side identity guard (issue #92
  scope extension). An already-bound divergent provider run must never
  settle this candidate's verdict.

## Tail (explicitly unglamorous)

- Trivia sweep (in flight at draft time: DFS-013 enumeration, stale CLI
  doc snapshots, issue #45 payload hygiene).
- Test-hardening (`mutmut`/`hypothesis`) — LOW priority per operator
  ruling (2026-08-29); dev-only, one card when pulled, zero core impact
  (`CLAUDE.md` rule 8 unaffected). Not scheduled to a phase; pulled when
  someone wants it.

## Explicitly NOT in M3 (dormant registry, triggers unchanged)

Rozoro (deferred stands); `acpx claude` provider swap; policy
parameterization; Beads authority graduation (issue #47); multi-repo
registry/profiles (the shared-portfolio *convention* — one `bd`
workspace + `ORC_JOURNAL_DIR` — is in live trial and may generate this
trigger); `--json` (issue #53, trigger: a structured consumer exists);
attention model.

## Acceptance

- `TASK-M3B-001` and `TASK-M3B-002` accepted through the ledger with the
  standard adversarial-verification pipeline.
- A regression scenario exists for each wedge shape (same-candidate
  retry; foreign-run settlement) proving the closed behavior.
- The dormant registry above is untouched.
