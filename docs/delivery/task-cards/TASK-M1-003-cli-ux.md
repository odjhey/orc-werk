---
id: TASK-M1-003
type: task-card
status: current
authority: normative
description: CLI UX batch closing issues #16, #17, #18, #23, including the #18 PORT-JOURNAL docs amendment.
implements:
  - PORT-JOURNAL
verifies: []
---

# TASK-M1-003 — CLI UX batch (#16, #17, #18, #23)

## Outcome

- **#16** — root-cause surfacing via CLI presentation: `status`/`dispatch` output reads journaled effect records' `dispatch_result` and surfaces the root cause alongside the block reason, e.g. `blocked_reason=retry-budget-exhausted (root_cause=ERR-UNSUPPORTED-CAPABILITY)`. Presentation-only; no contract change.
- **#17** — strict config validation at load time: unknown top-level keys and planned Works with no `attempts` coverage are rejected as canonical `ERR-VALIDATION` before any dispatch. The config schema is CLI-owned/non-normative; no contract change.
- **#18** — torn-tail content-blindness refinement: amend `PORT-JOURNAL`'s durable-journal recovery clause so a torn tail is tolerated only when at least one valid record precedes it, and/or the trailing line looks like truncated JSON (starts with `{`); fail closed otherwise (`ERR-VALIDATION`). Docs amendment lands before the code change.
- **#23** — `status` shows the submitted intent text (`FACT-INTENT-SUBMITTED.data.text`) instead of the run id under the `intent:` label.

## Depends on

`TASK-M1-001` (shared M1a docs baseline).

## Must not change

`STATE-DELIVERY`'s dispatch-gate-failure normalization rule; `CONTRACT-ERRORS`' canonical error taxonomy (#17 reuses `ERR-VALIDATION`, no new error values).

## Acceptance

- `docs/playbooks/cli-usage.md`'s known-issues ledger rows for #16/#17/#18/#23 are closed (deleted) by this task's PR;
- the `PORT-JOURNAL` durable-journal recovery amendment merges before or in the same PR as the #18 code change;
- issues #16, #17, #18, #23 are closed by this task's PR.
