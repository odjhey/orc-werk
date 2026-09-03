---
id: PLAYBOOK-WATCHTOWER
type: playbook
status: current
authority: informative
description: Multi-agent delivery operating model (watchtower/scout/ship/verify) used to build and evolve this repository.
---

# Watchtower operations playbook

This playbook records the delivery operating model used to ship M0 and expected for subsequent milestones. It is informative process documentation: it constrains how work is delivered, never what the product means (contracts own that — see `DOCS-ROOT` authority precedence).

The cross-cutting *method* the roles below rely on — how to write agent-facing instructions, diagnose a bug, verify work on separated axes, generate a design before pricing it, and keep records — lives in `PLAYBOOK-ENGINEERING-METHOD`. That doc is deliberately orc-agnostic (it applies to any agent in this workflow); this one is the orc-specific pipeline that references it.

## Roles

- **Watchtower** — the coordinating session. Decomposes milestones into PR-sized tasks, sequences delivery, makes contract rulings when audits surface ambiguity, reviews and merges every PR, and maintains the audit trail and deferred-decision ledger. The watchtower does not implement product code directly; it authors only small process/docs changes like this one.
- **Scouts** (reconnaissance) — read-only agents that map contracts before implementation: produce the contract map, decomposition proposal, and — critically — the list of ambiguities that must be resolved in docs before code. Also used for proposal/issue assessments (compatibility, feasibility, alignment).
- **Ship agents** — implementation agents. One task card, one worktree under `.worktrees/<branch>`, one branch, one PR. They receive governing contract IDs and a checkable definition of done; they must not invent semantics — genuine ambiguity is reported back in the PR body ("Ambiguities encountered"), not silently resolved. A guard, allowlist, or permission that refuses an action is likewise **reported, never worked around** — a refusal is a signal to route back, not an obstacle to engineer past. They never merge.
- **Verification scouts** — adversarial read-only auditors that run on every implementation PR before merge. They audit both directions: does the diff respect the governing contracts (checked against actual doc text, not plausibility), and did implementation expose gaps in the docs that need amendment. When a diff — or recon — contradicts an existing contract, the conflict is surfaced as a **first-class callout** that cites the contract by its stable ID and states why it should be reopened ("contradicts &lt;contract-id&gt;, worth reopening because …"), never silently routed around: the bidirectional check is only real if a contradiction is licensed to challenge the contract *out loud* rather than quietly conform to or ignore it. Verdicts: MERGE / MERGE-WITH-FOLLOW-UPS / FIX-BEFORE-MERGE, with findings, doc-amendment deadlines, and explicit confirmations of what was positively verified.
- **Dogfood checker** — a read-only, user-perspective agent run against the real CLI, not the test suite. It selects and executes the slice of `dogfood/` (`DOGFOOD-CORPUS`) whose concern tags intersect a shipped change, then reports PASS / BUG / FRICTION per scenario with evidence (commands, exit codes, `status`/`history` excerpts). It never fixes anything itself — no code, no docs, no issues filed directly; routing the healing (a fix PR, an issue, a docs amendment) is the watchtower's job, per `DELIVERY-STANCE`'s "dogfood feedback is the backlog."

Starting at M1a+ (`M-001`), ship agents and verification scouts also record their own observations directly into the delivery ledger through the `orc` CLI rather than the watchtower transcribing outcomes on their behalf — see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for the ship/verify recording protocol, role separation (no self-assurance), and the independent-derivation rule for verdicts. This is additive to the roles above, not a replacement: ship agents still ship, verification scouts still audit adversarially; the CLI is now how each records its own outcome, in addition to the PR-thread audit trail below.

## Pipeline

1. **Scout** the milestone: contract map, port signatures, serialization requirements, proposed decomposition, ambiguity list.
2. **Resolve blockers in docs first** (contract-first): every ambiguity that an implementer would otherwise guess at becomes a docs PR before dependent code is dispatched.
3. **Ship** tasks in dependency order; independent tasks fan out in parallel worktrees. Shared files (package `__init__`s) get append-only edits; test files are distinctly named.
4. **Verify** each PR adversarially; required fixes are applied by the same ship agent on the same PR (fix-on-PR, not merge-then-patch) when they sit on advertised contracts; smaller items are tracked.
   - **Corrective-intent rounds are the norm for contract rejections** (operator ruling, 2026-08-29, issue #75): when a verdict rejects a candidate on findings, the fix round is a NEW dispatch whose intent text carries the verifier's findings verbatim — never a blind re-dispatch of the original intent, which re-briefs the executor with no knowledge of what failed. The kernel's bounded blind retry remains for transient execution failures only. Findings-in-retry-prompt automation stays dormant behind the full-autonomy trigger recorded on issue #75.
5. **Merge** — watchtower only, squash merges, branch refreshed against master first (the single required `ci-required` status check is strict). Doc amendments merge before the code they govern whenever possible.
   - **A verdict is stale the moment the head moves.** An assurance verdict binds to the head sha it judged; any new head — including a routine branch refresh — silently voids it with no CI signal. Before merging, compare the verified sha against the merge candidate: `git patch-id` distinguishes content drift (re-verify) from a mere rebase of identical content (the verdict carries). Record which case it was. After merging, the merged sha itself is discoverable via the ledger's own `landing` affordance (`orc refs <run>`'s derived `landing` row, resolve `gh pr view <N> --json state,mergedAt,mergeCommit` — issue #65) rather than a separate manual lookup, closing this staleness check's own verified-sha-vs-merged-sha loop with a runnable command.
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
- **Wide mechanical refactors use expand → migrate → contract** — the sanctioned exception to "one PR = one green claim." A change with cross-codebase blast radius (rename a shared field, retype a shared symbol) cannot be a single green standalone PR. Sequence it: **expand** (add the new form beside the old; nothing breaks) → **migrate** call sites in blast-radius-sized batches (each its own PR, gate green batch-to-batch) → **contract** (delete the old form; blocked by all migrates). Every step keeps the gate green; there is no single giant red PR, and the "one reviewable claim" rule holds per batch.
- **Pilot one unit to falsify the brief before fanning out.** Before dispatching a multi-unit batch from one brief template, push exactly one unit through the entire pipeline — brief, ship, verify, merge — with the stated purpose of *breaking* the template, the verify recipe, and the unit sizing while that costs one agent instead of many. Fix the template from pilot evidence, then scale. A batch dispatched on an unpiloted template bets the whole fan-out on an untested contract.

## Autonomy and operator interaction

How the watchtower proceeds while the operator is away — previously informal,
now canonical:

- **The reversible/irreversible boundary.** Proceed on anything reversible and
  present the result; pause only for irreversible or outward-facing acts (force
  pushes to shared branches, deletions, deploys, external messages) unless a
  standing authorization covers them. Direction comes from the operator;
  execution never blocks on them. "Should I keep going?" is never a question to
  ask.
- **An empirical fork is settled by a probe, not a question.** Before asking
  "which approach?", classify the fork: if the answer is observable by running
  something, build the throwaway probe and hand the operator a *result to react
  to* instead of a decision to make. Questions are reserved for genuine
  preference calls no experiment settles.
- **A parked question carries a default.** Every question queued for the
  operator states the options *and the default that applies if no answer
  arrives*, so the program routes around the gate instead of truly blocking.
  The default fires as an ordinary recorded ruling.
- **A duration is not a finish condition.** Unattended runs get a checkable
  predicate, never an hour count — and a pre-authorized escape hatch: if
  genuinely stuck, stop and write up why. A written stop beats hours of creative
  goal reinterpretation.

Source for this section's mechanics: `cursor/plugins` pstack (poteto-mode,
orchestrate, overnight), reconciled with our existing proceed-while-AFK
practice and the reward-hacking clause above.

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

### Classifying deferred work, and what earns a record

Not every "later" is the same, and not every decision earns a durable entry:

- **Fog vs dormant vs out-of-scope** — the test is *can you state the question
  precisely now*, not whether you can answer it. A **dormant item** is a
  question sharp enough to phrase (recorded, with a named trigger). **Fog**
  ("not yet specified") is work you cannot yet frame precisely — leave it as
  fog; do not force it into a ticket to feel productive. **Out of scope** is
  past the destination: it never graduates in place and returns only as a fresh
  effort if the destination is redrawn. Conflating "we can't frame the question
  yet" with "we've framed it and are waiting for the trigger" is the drift this
  split prevents.
- **What earns a durable decision record** — record a ruling when it is (1) hard
  to reverse, (2) surprising without its context, or (3) the outcome of a real
  trade-off. Absent all three it is probably a no-op the next reader would have
  chosen anyway; recording it is ledger noise. The highest-value records are the
  explicit **no**s and the deliberate deviations from the obvious path — a ruling
  whose whole purpose is "do not re-litigate this / do not 'fix' this intentional
  choice" is an anti-regression guard for a future agent, not noise.

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
- `scripts/watch_pr.py` is the read-only merge-frontier watcher; it classifies blockers in conflicts > unresolved threads > CI > merge-gate order, and `--verified-sha` checks the verdict-staleness rule before merge.
- **Authoring the packaged `orc-ledger` skill's frontmatter `description`** (it is loaded by adopters' agents, including strict-YAML providers): (a) no colon-space (`: `) in an unquoted value — strict parsers (e.g. Pi's) read it as a nested mapping and the skill silently fails to load; single-quote the value and double inner apostrophes if a mid-sentence colon is unavoidable; (b) state **what + when** (the trigger phrases that should route to it) and never a how-summary of the workflow — a description that lists the steps makes the agent follow the summary and skip loading the body. The same colon-space caution applies to any doc frontmatter that a non-`docs_check` tool might strict-parse.
