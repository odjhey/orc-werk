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
