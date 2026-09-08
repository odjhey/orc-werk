---
id: TASK-OMP-282-287
type: task-card
status: current
authority: normative
description: Reconcile issue #282 (two harness-specific prose residues left in PLAYBOOK-WATCHTOWER after TASK-M5-002's shrink, and watch_pr.py's merge-frontier discovery missing from docs/adapters/omp/) and issue #287 (docs/adapters/omp/capabilities.md staleness and two unrepresented capability-report findings). Docs-only; no hook reintroduction.
implements:
  - ADR-0007
  - PLAYBOOK-WATCHTOWER
verifies: []
---

# TASK-OMP-282-287 — reconcile `PLAYBOOK-WATCHTOWER` residue and `capabilities.md` staleness

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY`; issue #282; issue
#287; `docs/reports/2026-09-07-omp-capability-test.md`.

## The gap

Two verify-seat-disclosed residues from the M5 playbook shrink
(`TASK-M5-002`, PR #279) and the adapter-docs authoring (`TASK-M5-003`,
PR #273) remained open, each already disclosed honestly rather than
discovered late:

- **#282** — `PLAYBOOK-WATCHTOWER`'s `Seats` intro still names
  `.omp/agents/*.md` and `.omp/config.yml` directly, and the last
  `Conventions` bullet names the Pi (OMP) strict-YAML parser — both
  harness-specific mechanics that belong in `docs/adapters/omp/` per the
  same rule that already moved everything else out of the playbook.
  Separately, `scripts/watch_pr.py`'s Conventions line was *deleted, not
  moved* (correct per `M5-OMP-FIRST-DELIVERY` Phase 3's "Deleted" list for
  the *convention prose*), but that left the merge-frontier tool's
  blocker order and `--verified-sha` staleness check unnamed in every doc
  a fresh session reads.
- **#287** — `docs/adapters/omp/capabilities.md` rows 1–5 were filled in
  since this issue was filed (`TASK-M5-005`'s hook-abandonment amendments,
  PRs #292/#294/#300 landed after PR #286 explicitly declined this as
  out of scope); `conformance.md` still described that table as
  "pending"; and two report findings the card that authored
  `capabilities.md` never asked for (§7a silent `omp -p` concurrency
  death, §7b silent model-family substitution) had no row.

## Outcome

- `PLAYBOOK-WATCHTOWER`'s `Seats` intro references `docs/adapters/omp/`
  (`ADAPTER-OMP`) instead of naming `.omp/agents/*.md`/`.omp/config.yml`
  directly; the Model-family seat-table cells naming those paths are
  unchanged (per #282's own note: seat-table rows are the permitted
  exception). The Conventions section keeps only the harness-independent
  "what + when, never a how-summary" skill-authoring rule; the OMP
  strict-YAML colon-space mechanism moves to
  `docs/adapters/omp/README.md`.
- `docs/adapters/omp/mapping.md` gains a `watch_pr.py` discovery
  paragraph: the blocker order (`CONFLICTS` > `UNRESOLVED-THREADS` >
  `CI-FAILING` > `MERGE-GATE` > `CI-PENDING`/`NEEDS-UPDATE-BRANCH` >
  `READY`, per `classify()`) and `--verified-sha`'s patch-id staleness
  check (`STALE-VERDICT`/`REBASED`/`INDETERMINATE`), grounded in the
  installed script's own `--help` and source — restoring discoverability
  without reopening `ADR-0007`'s "kept, unchanged" ruling on the script
  itself.
- `docs/adapters/omp/capabilities.md` gains two rows (7a, 7b) for the
  report's unplanned findings, cross-referencing issue #302 (concurrency,
  filed separately as harness-runtime remediation, not reopened here)
  and issue #281 (model-family substitution). `conformance.md`'s stale
  "pending" reference to that table is corrected to reflect its landed,
  amended state.
- No code change; no hook reintroduced; `ADR-0007`'s 2026-09-07
  hook-retirement amendment and the "no `.omp/extensions/*` hook writes
  `.orc`" ruling are unaffected.

## In scope

- `docs/delivery/watchtower-operations.md` — the `Seats` intro paragraph
  and the last `Conventions` bullet only.
- `docs/adapters/omp/README.md` — the moved strict-YAML frontmatter
  mechanic.
- `docs/adapters/omp/mapping.md` — the restored `watch_pr.py` discovery
  paragraph.
- `docs/adapters/omp/capabilities.md` — the two new findings rows.
- `docs/adapters/omp/conformance.md` — the stale "pending" fix.
- This card and its index registration.

## Out of scope

- `scripts/watch_pr.py` itself (kept unchanged per `ADR-0007`; this card
  documents it, never modifies it).
- Reopening any `tool_call` hook rung (`TASK-M5-005`, closed unmerged;
  `ADR-0007`'s 2026-09-07 amendment stands).
- Issue #302 (OMP concurrent print-mode exit-zero) and issue #281
  (`executor-identity/v1.model` self-reporting) themselves — referenced,
  not resolved, here.
- `docs/delivery/M5-omp-first-delivery.md` — a historical milestone
  record, left as the belief it stated at the time.

## Acceptance

- `docs_check.py` passes.
- `PLAYBOOK-WATCHTOWER` contains no direct reference to
  `.omp/agents/*.md`/`.omp/config.yml` outside the seat table's
  Model-family column, and no reference to the Pi/OMP YAML parser
  outside `docs/adapters/omp/`.
- `docs/adapters/omp/mapping.md` states `watch_pr.py`'s blocker order and
  `--verified-sha`'s staleness check, both verified against the
  installed script's `--help` output and `classify()`/`classify_verdict()`
  source, not recalled from memory.
- `docs/adapters/omp/capabilities.md` contains rows for report §7a and
  §7b, each citing a tracking issue (#302, #281 respectively).
- `docs/adapters/omp/conformance.md` no longer describes `capabilities.md`
  as pending.
- `bash scripts/check.sh` is green.

## Ambiguities encountered

- The former Conventions bullet mixed one harness-independent rule
  ("what + when, never a how-summary") with one OMP-specific mechanism
  (the strict-YAML colon-space gotcha). Issue #282 names the whole bullet
  as residue; this card splits rather than wholesale-relocates it,
  because the "what + when" rule is genuinely harness-independent policy
  (it holds regardless of which harness loads the skill) while only the
  colon-space parsing detail is OMP-specific mechanics. Recorded here as
  a local, mechanical decision, not a contract-level ambiguity requiring
  an operator ruling.
