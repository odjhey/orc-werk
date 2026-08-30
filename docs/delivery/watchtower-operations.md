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
- **Ship agents** — implementation agents. One task card, one worktree under `.worktrees/<branch>`, one branch, one PR. They receive governing contract IDs and a checkable definition of done; they must not invent semantics — genuine ambiguity is reported back in the PR body ("Ambiguities encountered"), not silently resolved. A guard, allowlist, or permission that refuses an action is likewise **reported, never worked around** — a refusal is a signal to route back, not an obstacle to engineer past. They never merge.
- **Verification scouts** — adversarial read-only auditors that run on every implementation PR before merge. They audit both directions: does the diff respect the governing contracts (checked against actual doc text, not plausibility), and did implementation expose gaps in the docs that need amendment. Verdicts: MERGE / MERGE-WITH-FOLLOW-UPS / FIX-BEFORE-MERGE, with findings, doc-amendment deadlines, and explicit confirmations of what was positively verified.
- **Dogfood checker** — a read-only, user-perspective agent run against the real CLI, not the test suite. It selects and executes the slice of `dogfood/` (`DOGFOOD-CORPUS`) whose concern tags intersect a shipped change, then reports PASS / BUG / FRICTION per scenario with evidence (commands, exit codes, `status`/`history` excerpts). It never fixes anything itself — no code, no docs, no issues filed directly; routing the healing (a fix PR, an issue, a docs amendment) is the watchtower's job, per `DELIVERY-STANCE`'s "dogfood feedback is the backlog."

Starting at M1a+ (`M-001`), ship agents and verification scouts also record their own observations directly into the delivery ledger through the `orc` CLI rather than the watchtower transcribing outcomes on their behalf — see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for the ship/verify recording protocol, role separation (no self-assurance), and the independent-derivation rule for verdicts. This is additive to the roles above, not a replacement: ship agents still ship, verification scouts still audit adversarially; the CLI is now how each records its own outcome, in addition to the PR-thread audit trail below.

## Pipeline

1. **Scout** the milestone: contract map, port signatures, serialization requirements, proposed decomposition, ambiguity list.
2. **Resolve blockers in docs first** (contract-first): every ambiguity that an implementer would otherwise guess at becomes a docs PR before dependent code is dispatched.
3. **Ship** tasks in dependency order; independent tasks fan out in parallel worktrees. Shared files (package `__init__`s) get append-only edits; test files are distinctly named.
4. **Verify** each PR adversarially; required fixes are applied by the same ship agent on the same PR (fix-on-PR, not merge-then-patch) when they sit on advertised contracts; smaller items are tracked.
   - **Corrective-intent rounds are the norm for contract rejections** (operator ruling, 2026-08-29, issue #75): when a verdict rejects a candidate on findings, the fix round is a NEW dispatch whose intent text carries the verifier's findings verbatim — never a blind re-dispatch of the original intent, which re-briefs the executor with no knowledge of what failed. The kernel's bounded blind retry remains for transient execution failures only. Findings-in-retry-prompt automation stays dormant behind the full-autonomy trigger recorded on issue #75.
5. **Merge** — watchtower only, squash merges, branch refreshed against master first (the single required `ci-required` status check is strict). Doc amendments merge before the code they govern whenever possible.
6. **Consolidate** doc amendments produced by a round of audits into one docs PR rather than many.
7. At integration gates, run a **falsifiability pass**: hand-picked contract-violating mutants applied to a scratch copy; every mutant must turn the suite red, and any survivor becomes a mandatory test addition.
8. After a major merge, run the concerned slice of `dogfood/` (`DOGFOOD-CORPUS`) via the dogfood checker. Findings route per `DELIVERY-STANCE`: a deterministic, contract-relevant finding becomes an issue and/or a fix PR; a legibility/output-quality finding (FRICTION) becomes an issue or a docs amendment; either way the finding is recorded, never left as an unfiled observation.

## Task sizing

Tasks are sized by reviewability and decision count, not implementation effort:

- **One PR = one reviewable claim**, statable as "implements these stable contract IDs". If the ID list spans layers, split.
- **Zero unresolved ambiguities at dispatch** — shippers get mechanical-once-specified work; judgment stays with the watchtower and its scouts, or routes back as a stop-and-report.
- **Checkable definition of done** — enumerable conformance requirements and scenarios, never "make it work".
- **No reward-hacking in the definition of done** — the brief states explicitly that tests, gates, and checks must not be deleted, skipped, weakened, or narrowed to make them pass. A green gate reached by weakening the check is a rejected candidate, not a delivery. This is the shipper-side complement to the verifier's tautological-test hunt: the shipper is told not to game the gate; the verifier confirms the gate was not gamed (it hunts tests that cannot fail and re-derives any identity a verdict rests on).
- **Disjoint file territory** for anything dispatched in parallel.

## Dormant-feature lifecycle

Every "if ever" feature follows the same lifecycle: **recon → rulings → recorded
shape → dormant until pulled.**

1. **Recon** — a scout produces the evidence-grounded picture (what exists, what
   maps, what conflicts) before anyone commits to anything.
2. **Rulings** — the judgment-heavy questions the recon surfaces are decided by
   the operator/watchtower while context is freshest, including consequence
   analysis for the contested ones.
3. **Recorded shape** — the implementation design (invocation model, op mapping,
   testing pattern, slice boundaries) is written down where the eventual
   implementer will find it (issue thread, task card, or adapter doc stub),
   fully pre-decided minus any explicitly-named open questions.
4. **Dormant until pulled** — nothing is built until real usage demands it, and
   every dormant item MUST name its pull trigger. When the trigger fires, the
   executing agent inherits a complete design instead of an open debate.

The point: the decision cost is paid exactly once, at the moment of maximum
context — nothing is built speculatively, and nothing is re-litigated. This
extends the deferred-decision ledger (Audit trail, below) from deferred
*decisions* to pre-decided *features*. A dormant item without a named trigger
is a defect in this lifecycle, the same way an unrecorded rough edge is a
defect under `DELIVERY-STANCE`.

## Audit trail

Every decision must be reconstructable after the fact:

- PR bodies carry scope, governing contract IDs, design decisions, verification output, and ambiguities encountered.
- Audit verdicts, watchtower rulings, and fix rounds are recorded on the PR threads.
- Consciously deferred decisions (with the trigger that will force each) are tracked as a deferred-decision ledger; deferrals are recorded, never implicit.
- Operator (human) review is asynchronous and non-blocking: contract rulings are reviewable as small isolated diffs in `docs/` history, and overriding any ruling is itself one docs PR.

## Model and effort selection

Capability is spent where decisions are made; mechanical work runs on economical models.

- **Ship agents** run on a mid-tier implementation model (Sonnet-class). Tasks reach them with zero unresolved ambiguity and a checkable definition of done, so authorship is mechanical-once-specified; capability budget goes to review instead.
- **Reconnaissance and verification scouts** run on a high-capability reasoning model (Opus-class). Decomposition and adversarial audit are the judgment-dense stages — a missed contract interaction there costs more than any implementation bug.
- **Assessment scouts** for proposals and architecture rulings that shape milestones run on the strongest model available (Fable-class): these produce dispositions the watchtower adopts largely as-is.
- **Reasoning effort** defaults to inherited session settings; escalate for audits of subtle contract interactions (state-machine totality, idempotency/replay), and keep docs-shipping and mechanical fix rounds cheap.
- The **quality bar these agents ship against** is defined in `docs/delivery/delivery-stance.md` (`DELIVERY-STANCE`).

## Conventions

- Worktrees: `.worktrees/<branch-name>` (gitignored), removed after merge.
- Local gate `bash scripts/check.sh` mirrors CI exactly; green locally means green remotely.
- Commits carry attribution trailers; PR bodies end with generation attribution.
- Run `python3 scripts/docs_check.py` before committing any documentation change.
- **Authoring the packaged `orc-ledger` skill's frontmatter `description`** (it is loaded by adopters' agents, including strict-YAML providers): (a) no colon-space (`: `) in an unquoted value — strict parsers (e.g. Pi's) read it as a nested mapping and the skill silently fails to load; single-quote the value and double inner apostrophes if a mid-sentence colon is unavoidable; (b) state **what + when** (the trigger phrases that should route to it) and never a how-summary of the workflow — a description that lists the steps makes the agent follow the summary and skip loading the body. The same colon-space caution applies to any doc frontmatter that a non-`docs_check` tool might strict-parse.
