---
id: ADR-0006
type: decision
status: current
authority: informative
description: An inconclusive assurance verdict re-requests assurance of the same candidate under a bounded assurance budget instead of blocking the Work outright.
---

# ADR-0006 — Bounded assurance re-request on `inconclusive`

## Status

Accepted (operator ruling, 2026-09-05, option B of `docs/reports/2026-09-05-pstack-graded-verdicts.md` §4 Q1).

## Context

Since M0, `STATE-DELIVERY` resolved an `inconclusive` assurance settlement in one row: `ASSURING` → `DEC-BLOCK` → terminal `BLOCKED`, reason `assurance-inconclusive`. The rest of the contract simultaneously steers verifiers *toward* that verdict: `ADR-0002` requires a provider that cannot prove subject identity to answer `inconclusive`; `CONF-ASSURE-006` requires a command-backed verifier to map every crash, signal, and timeout to `inconclusive`. The honest verdict for "I could not evaluate this" was therefore also the one that ended the Work.

Two distinct situations were forced through one word:

- the verifier evaluated the candidate and genuinely cannot decide (identity diverged, output ambiguous);
- the verifier could not evaluate at all (sandbox down, tooling missing, timeout).

For the second, the only contract-legal answers were silence (rest at `ASSURING`, record nothing — safe but illegible: the ledger cannot distinguish "a verifier tried and was blocked" from "no verifier showed up") or an outright `rejected`, which spends the *ship* seat's retry budget (`INV-018`) and triggers a corrective-intent round for a defect that was never in the candidate. The verify seat's record verb offered only `accepted|rejected`, reinforcing the second answer. A command-backed verifier cannot even choose silence: one flaky timeout permanently blocked the Work.

The abandon path (`DEC-ABANDON-ATTEMPT`, `STATE-DELIVERY` item 9) does not rescue this. It spends an execution attempt, and a re-produced unchanged candidate with no *settled* prior assurance is a conflict resting point, not an inheritance, so the operator abandons again until the budget is gone. There was no path that re-verified an unchanged candidate.

The assessment of pstack's graded verification ledger (`RESEARCH-LINEAGE`, pstack entry) surfaced the missing rule crisply: "`verifier-blocked` is not a pass; respawn when the environment heals. `verifier-failed` gets a fix unit, not a re-verify."

## Options

1. **Keep `inconclusive` terminal; fix legibility.** Playbook rule: a blocked verifier records nothing and leaves the reason where the ledger can see it. Cheapest. Leaves the command adapter's timeout problem unsolved and the ledger blind to blocked verifiers.
2. **Re-request assurance of the same candidate on `inconclusive`, bounded by a separate assurance budget.** New transition row; exhaustion still resolves to `DEC-BLOCK`. Touches `INV-020`'s key form and adds an `INV-019` sibling.
3. **Split "could not evaluate" from "evaluated, undecidable" at the port.** Blocked becomes a non-settlement (like the command adapter's spawn-failure `ERR-PROVIDER-UNAVAILABLE`), `inconclusive` keeps its terminal meaning. Changes `PORT-ASSURANCE` and every adapter mapping table; a timeout is genuinely ambiguous between a hung verifier and a hung candidate.

## Decision

Option 2.

- `STATE-DELIVERY` gains two rows in place of one: `inconclusive` with assurance budget available → `DEC-REQUEST-ASSURANCE` → `ASSURING` (same exact candidate, new assurance identity, `FX-START-ASSURANCE`); `inconclusive` with budget exhausted → `DEC-BLOCK` → `BLOCKED`, reason `assurance-inconclusive` unchanged.
- `INV-021` defines the assurance budget (`max_assurance_attempts`, default `2`) and the per-execution-attempt `assurance_number`. Assurance re-requests never consume the execution retry budget (`INV-018`) because they journal no execution-start record.
- `INV-020`'s `FX-START-ASSURANCE` key gains an `assurance_number` component for the second and later assurances of a candidate. The first keeps the pre-existing key form so every journal written before this decision replays under identical keys.
- The budget is journaled at run creation in `FX-CREATE-WORK.data.max_assurance_attempts`, under the same single-authority and match-or-refuse rules `SCN-008` establishes for `max_attempts`. A legacy journal that lacks the field folds under budget `1`, which is exactly pre-decision behavior — so no existing journal changes meaning on replay.
- An `inconclusive` settlement is never *inherited* (`STATE-DELIVERY` item 8). A candidate whose only settled assurances are `inconclusive`, re-observed on a later attempt, enters `ASSURING` afresh: it is neither an inheritance nor an item 9 conflict.
- The verify seat's record verb accepts `--verdict inconclusive`. `PLAYBOOK-AGENT-CLI` tells a verifier when to record it and when to simply wait.

## Consequences

Positive:

- Honesty stops being fatal. A verifier that cannot evaluate records exactly that, and the run pays with assurance budget, never with the ship seat's retry budget.
- Command-backed assurance survives one transient failure by contract, not by luck.
- Blocked verifiers become legible in the journal: the `inconclusive` settlement, its evidence, and the re-request Decision citing it are all durable.
- `inconclusive` keeps one meaning at the port ("this settlement decided nothing"); the *budget*, not the word, decides whether the Work continues.

Costs:

- One more budget to configure, journal, and reason about; a second key form for one effect.
- Scripted/pending-mode configs need a way to carry more than one assurance settlement per execution attempt (a CLI-owned config shape, decided at implementation).
- The dogfood corpus scenario that encoded "inconclusive blocks immediately" (`DFS-005`) must be re-stated in terms of the budget.

Not decided here: an exit from `BLOCKED` (issue #254); distinguishing "could not evaluate" from "undecidable" as separate port values (option 3 stays available as a future refinement — the two would then feed the same budget); the `assurance-depth/v1` draft (`EXT-ASSURANCE-DEPTH-V1`), which is orthogonal.

## Related contract IDs

- `STATE-DELIVERY`, `INV-018`, `INV-019`, `INV-020`, `INV-021`
- `PORT-ASSURANCE`, `INV-009`, `ADR-0002`
- `DEC-REQUEST-ASSURANCE`, `DEC-BLOCK`, `FX-START-ASSURANCE`
- `SCN-021`, `SCN-007`, `SCN-008`, `SCN-009`
- `CONF-ASSURE-004`, `CONF-ASSURE-006`, `CONF-ASSURE-008`, `CONF-JOURNAL-003`
- `PLAYBOOK-AGENT-CLI`, `RESEARCH-LINEAGE`
