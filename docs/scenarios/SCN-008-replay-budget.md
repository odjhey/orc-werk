---
id: SCN-008
type: scenario
status: current
authority: normative
description: Journal replay is self-sufficient under a non-default retry budget, including for a run that reached BLOCKED.
---

# SCN-008 — Replay under the run's own retry budget

## Given
- A run is dispatched with a non-default `max_attempts` (e.g. `2`, not the reducer's schema default of `3`).
- Work A's every attempt fails, exhausting that budget: Work A reaches `BLOCKED` via `DEC-BLOCK` (`SCN-004`'s shape, with a non-default budget).
- The run's `FX-CREATE-WORK` effect record durably carries `data.max_attempts` alongside `data.plan` (`CONTRACT-DURABILITY`'s topology/budget row).

## Then
- `PORT-JOURNAL-005 load_projection`, replayed from a fresh reader with no access to the original dispatch config, folds the run's Facts under the recorded `data.max_attempts` — not the reducer's schema default — and reconstructs the identical projection the original run produced (`CONF-JOURNAL-003`).
- In particular, `FACT-WORK-BLOCKED` replays as a legal transition from `BLOCKED` (not `ERR-CONFLICT` from a wrongly-derived `READY`), because replay used the same budget the run used to reach `BLOCKED` in the first place.
- Every read-side consumer built on `load_projection` (status, history, `report`, `report --index`, `report --all`) renders this run without raising a canonical error.

## Given (legacy fallback)
- A journal record for `FX-CREATE-WORK` predates this durability fix and carries `data.plan` but no `data.max_attempts`.

## Then (legacy fallback)
- `load_projection` falls back to the reducer's schema default (`DEFAULT_MAX_ATTEMPTS`) for that run, exactly as if the run had used that default — a documented read-fallback, not an error (mirrors the issue #55 layout fallback).

Verifies: `PORT-JOURNAL-005`, `CONF-JOURNAL-003`, `INV-018`, `INV-019`, `CONTRACT-DURABILITY`.

## Amendment (issue #240): budget authority, match-or-refuse, and the divergence-is-forbidden statement

Issue #240 found that this scenario's own guarantee ("a fresh reader ... reconstructs the identical projection the original run produced") had a write-side hole: `--max-attempts 1` on first dispatch journaled into `FX-CREATE-WORK` but was not persisted into the run's `config.json`, so a bare `--run-id` resume (a *write*-side replay, inside `Orchestrator`) evaluated retry policy under the config-derived default (`3`) instead of the journaled budget (`1`) and journaled `DEC-RETRY` → `FACT-EXEC-STARTED` for a second attempt — a decision the run's own journal already forbade. From then on, read-side verbs (`status`/`history`/`record`), replaying honestly under the journaled budget, raised `ERR-CONFLICT` on the run's own seq'd fact, while `dispatch` — replaying under its own process's wrong budget — kept advancing: one journal, two reconstructed states, exactly the divergence this scenario's original "Then" clause already forbids for the read side alone.

### Given (budget authority, issue #240 R1)
- A run already has a `FX-CREATE-WORK` effect record durably journaled (i.e. any pass over the run other than the one that creates it).

### Then (budget authority, issue #240 R1)
- The journaled budget (`FX-CREATE-WORK.data.max_attempts`, read back via `journaled_max_attempts`/`effective_max_attempts`) is the single authority for `max_attempts` for EVERY verb's fold of that run — not just `load_projection` (this scenario's original scope) but every write-side decision fold too (`orc_werk.app.orchestrator.Orchestrator._reconcile_ports`, `.projection`, `.cancel_work`, `._apply_decision`/`orc_werk.core.policy.decide`). A caller's own effective config, `RunConfig`, or CLI flag governs `max_attempts` ONLY at the moment of run creation (`Orchestrator.bootstrap`, before any `FX-CREATE-WORK` record exists) — that is the one call where the config value is legitimately the source, precisely because it is about to become the journaled value every later pass must defer to.

### Given (match-or-refuse on resume, issue #240 R2)
- An operator supplies an explicit `--max-attempts` flag, or an explicit `--config` file's `max_attempts` key, when dispatching a run that already has a `FX-CREATE-WORK` record.

### Then (match-or-refuse on resume, issue #240 R2)
- If the supplied value differs from that run's journaled `max_attempts`, the dispatch MUST be refused with a canonical `ERR-VALIDATION` naming both the journaled value and the requested value, with `next` guidance to resume without the flag/overlay ("the run's budget was fixed at creation: N"). If the supplied value equals the journaled value, the dispatch proceeds — a no-op with respect to the budget. An ordinary bare `--run-id` resume that supplies no explicit `max_attempts` opinion is never refused by this clause; it silently resumes under the journaled budget per R1. Changing a live run's budget after creation is explicitly OUT OF SCOPE for this ruling — a possible future operator feature, not provided here.

### Then (divergence is forbidden, issue #240 R4)
- Replaying one journal — by any verb, in any process — MUST reconstruct exactly one projection (this scenario's original guarantee, now stated generally rather than for `load_projection` alone). Consequently, a write path MUST NEVER return having appended a record that its own fresh replay, under R1's same budget-authority rule, would itself reject: appending a record and then being unable to legally fold it back is not a legitimate outcome for any pass to leave behind. A dispatch pass (and any other journal-appending write path — `abandon_attempt`, `cancel_work`) that appended one or more records ends with exactly one additional fresh fold of the run's full history under R1. If that fold raises, the pass fails LOUDLY with a canonical error naming the offending record, instead of returning success and leaving the divergence for a later, different verb to discover as an inexplicable conflict on its own journal.

### Given (legacy wedged journals, issue #240 R5)
- A journal already durably contains a record that is illegal under this budget-authority rule (for example, a `FACT-EXEC-STARTED` for an attempt number the journaled `max_attempts` forbids) — written by a pre-fix process that derived its retry decision from the wrong, config-derived budget instead of R1's journaled one.

### Then (legacy wedged journals, issue #240 R5)
- Such a journal is a documented-unrecoverable specimen, exactly as the issue #52/#77 precedent established for other illegal-history classes on this same run-history surface: replay of that run continues to raise the ordinary canonical `ERR-CONFLICT` it always would under this rule, and the reducer's legality checking is NOT weakened or special-cased to accept it — the append-only journal cannot un-record an illegal Fact (`PROTOCOL-FACTS`). This ruling prevents NEW specimens; it does not repair existing ones. An operator holding an already-wedged run from before this fix should treat it as unrecoverable and start a fresh run — wedged specimens are trivially regenerable from the repro that found them, so there is nothing irreplaceable to salvage. (Whether a future relaxation — folding recorded history without re-legalizing it — is worth pursuing is an open question; see the fixing PR's "Ambiguities encountered", not a code change made here.)

Verifies (amendment): `PORT-JOURNAL`, `PORT-JOURNAL-005`, `CONF-JOURNAL-003`, `INV-018`, `INV-019`, `CONTRACT-DURABILITY`, `ERR-VALIDATION`, `ERR-CONFLICT`. Cites: issue #240.
