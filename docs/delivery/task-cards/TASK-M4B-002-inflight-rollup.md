---
id: TASK-M4B-002
type: task-card
status: superseded
authority: normative
description: FOLDED into TASK-M4B-001 — the single-dir in-flight roll-up is delivered by M4B-001's --state active filter + shared _index_state_rollup helper.
implements: []
verifies: []
---

> **Note (issue #254, 2026-09-07):** this folded card's worked description
> of `orc --state active` below is superseded. `--state active` had only
> ever excluded terminal `ACCEPTED`, so a retry-budget-exhausted `BLOCKED`
> run sat in the active view forever; the fix makes `--state active`
> exclude every terminal state (`ACCEPTED`, `CANCELLED`, `BLOCKED`),
> matching `STATE-DELIVERY`'s full terminal set. See
> `docs/delivery/M4-cockpit-and-clarity.md` ruling 6's amendment for the
> current semantic and PR #274 for the change. Retained below as
> historical record of the original FOLD decision only.

# TASK-M4B-002 — FOLDED into TASK-M4B-001

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4B.

## Decision (watchtower, 2026-08-30): FOLD — delivered by subsumption

This card's only firm deliverable was to *decide* standalone-vs-fold once
`TASK-M4B-001` shipped. It shipped (PR #138), and it already delivers the
in-flight roll-up this card scoped:

- `orc --state active` lists exactly the non-terminal / blocked runs over
  one journal dir, with each run's `states=<counts>`, `flags=blocked,pending`,
  and `blocked_reason`.
- The `_summarize_states` logic that was per-run-only graduated into the
  shared `_index_state_rollup` helper (`report.py`), consumed by both the
  bare-`orc` index and the HTML `--index` — which was the mechanics gap this
  card named.

A separate standalone surface would duplicate that helper with no added
information, so none is built. See `M4-COCKPIT-AND-CLARITY` ruling 6.

**Deferred nicety (not pulled):** a dir-level aggregate header (e.g.
"4 runs — 2 blocked, 2 ready") over the default unfiltered list. Marginal;
a follow-up only if friction calls for it.
