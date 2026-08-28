---
id: PLAYBOOK-WATCHTOWER
type: playbook
status: current
authority: informative
description: Multi-agent delivery operating model (watchtower/scout/ship/verify) used to build and evolve this repository.
---

# Watchtower operations playbook

This playbook records the delivery operating model used to ship M0 and expected for subsequent milestones. It is informative process documentation: it constrains how work is delivered, never what the product means (contracts own that — see `DOCS-ROOT` authority precedence).

## Roles

- **Watchtower** — the coordinating session. Decomposes milestones into PR-sized tasks, sequences delivery, makes contract rulings when audits surface ambiguity, reviews and merges every PR, and maintains the audit trail and deferred-decision ledger. The watchtower does not implement product code directly; it authors only small process/docs changes like this one.
- **Scouts** (reconnaissance) — read-only agents that map contracts before implementation: produce the contract map, decomposition proposal, and — critically — the list of ambiguities that must be resolved in docs before code. Also used for proposal/issue assessments (compatibility, feasibility, alignment).
- **Ship agents** — implementation agents. One task card, one worktree under `.worktrees/<branch>`, one branch, one PR. They receive governing contract IDs and a checkable definition of done; they must not invent semantics — genuine ambiguity is reported back in the PR body ("Ambiguities encountered"), not silently resolved. They never merge.
- **Verification scouts** — adversarial read-only auditors that run on every implementation PR before merge. They audit both directions: does the diff respect the governing contracts (checked against actual doc text, not plausibility), and did implementation expose gaps in the docs that need amendment. Verdicts: MERGE / MERGE-WITH-FOLLOW-UPS / FIX-BEFORE-MERGE, with findings, doc-amendment deadlines, and explicit confirmations of what was positively verified.

## Pipeline

1. **Scout** the milestone: contract map, port signatures, serialization requirements, proposed decomposition, ambiguity list.
2. **Resolve blockers in docs first** (contract-first): every ambiguity that an implementer would otherwise guess at becomes a docs PR before dependent code is dispatched.
3. **Ship** tasks in dependency order; independent tasks fan out in parallel worktrees. Shared files (package `__init__`s) get append-only edits; test files are distinctly named.
4. **Verify** each PR adversarially; required fixes are applied by the same ship agent on the same PR (fix-on-PR, not merge-then-patch) when they sit on advertised contracts; smaller items are tracked.
5. **Merge** — watchtower only, squash merges, branch refreshed against master first (the single required `ci-required` status check is strict). Doc amendments merge before the code they govern whenever possible.
6. **Consolidate** doc amendments produced by a round of audits into one docs PR rather than many.
7. At integration gates, run a **falsifiability pass**: hand-picked contract-violating mutants applied to a scratch copy; every mutant must turn the suite red, and any survivor becomes a mandatory test addition.

## Task sizing

Tasks are sized by reviewability and decision count, not implementation effort:

- **One PR = one reviewable claim**, statable as "implements these stable contract IDs". If the ID list spans layers, split.
- **Zero unresolved ambiguities at dispatch** — shippers get mechanical-once-specified work; judgment stays with the watchtower and its scouts, or routes back as a stop-and-report.
- **Checkable definition of done** — enumerable conformance requirements and scenarios, never "make it work".
- **Disjoint file territory** for anything dispatched in parallel.

## Audit trail

Every decision must be reconstructable after the fact:

- PR bodies carry scope, governing contract IDs, design decisions, verification output, and ambiguities encountered.
- Audit verdicts, watchtower rulings, and fix rounds are recorded on the PR threads.
- Consciously deferred decisions (with the trigger that will force each) are tracked as a deferred-decision ledger; deferrals are recorded, never implicit.
- Operator (human) review is asynchronous and non-blocking: contract rulings are reviewable as small isolated diffs in `docs/` history, and overriding any ruling is itself one docs PR.

## Conventions

- Worktrees: `.worktrees/<branch-name>` (gitignored), removed after merge.
- Local gate `bash scripts/check.sh` mirrors CI exactly; green locally means green remotely.
- Commits carry attribution trailers; PR bodies end with generation attribution.
- Run `python3 scripts/docs_check.py` before committing any documentation change.
