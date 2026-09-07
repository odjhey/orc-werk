---
id: PLAYBOOK-WATCHTOWER
type: playbook
status: current
authority: informative
description: Multi-agent delivery operating model (watchtower/scout/ship/verify) used to build and evolve this repository — harness-independent seat policy; harness-specific mechanics live in docs/adapters/<harness>/.
---

# Watchtower operations playbook

This playbook records the delivery operating model used to ship M0 and expected for subsequent milestones. It is informative process documentation: it constrains how work is delivered, never what the product means (contracts own that — see `DOCS-ROOT` authority precedence).

The cross-cutting *method* the roles below rely on — how to write agent-facing instructions, diagnose a bug, verify work on separated axes, generate a design before pricing it, and keep records — lives in `PLAYBOOK-ENGINEERING-METHOD`. That doc is deliberately orc-agnostic (it applies to any agent in this workflow); this one is the orc-specific pipeline that references it.

## Seats

This table states each seat's harness-independent boundary — what it may touch, never what tool runs it. Model/effort configuration, tool restrictions, structured-output enforcement, and worktree fencing are *mechanics*; today's mechanics live in `.omp/agents/*.md` and `.omp/config.yml`, documented for this harness in `docs/adapters/omp/` (`ADAPTER-OMP`, `ADR-0007`). A future harness swap changes the mechanics column, never the boundary.

| Seat | Effects boundary | Model family (current harness) | Effort | Result schema | Observed failures |
|---|---|---|---|---|---|
| **Watchtower** | Coordinating session: decomposes milestones into PR-sized tasks, sequences delivery, rules on ambiguity when audits surface it, reviews and merges every PR, maintains the audit trail and deferred-decision ledger. Authors only small process/docs changes directly, never product code. | strongest available (Fable-class for proposal/architecture assessments) | escalate for subtle contract-interaction audits (state-machine totality, idempotency/replay); cheap for docs-shipping and mechanical fix rounds | none — a coordinating session, not a candidate-producing seat | `docs/delivery/seat-reliability.md` |
| **Scout** (reconnaissance) | Read-only: contract map, decomposition proposal, ambiguity list before implementation; also proposal/issue assessment (compatibility, feasibility, alignment). Never edits, writes, commits, or records to the ledger. | `.omp/agents/scout.md` — anthropic (Opus-class) | high | `{report, unverified[], ambiguities[], stale_after}` | `docs/delivery/seat-reliability.md` |
| **Ship agent** | One task card, one worktree under `.worktrees/<branch>`, one branch, one PR; receives governing contract IDs and a checkable definition of done. Never invents semantics — genuine ambiguity routes back in the PR body ("Ambiguities encountered"), never silently resolved. A refusal (guard/allowlist/permission) is likewise reported, never engineered past. Never merges. | `.omp/agents/ship.md` — anthropic (Sonnet-class, mid-tier) | medium | `{run_id, work_id, branch, pr, head_sha, gate, not_covered[], ambiguities[], recorded}` | `docs/delivery/seat-reliability.md` |
| **Verification scout** | Adversarial, read-only audit of every implementation PR before merge, on both directions: does the diff respect governing contracts (checked against doc text, not plausibility), and did implementation expose a doc gap. A contradiction with an existing contract is a first-class callout citing the contract's stable ID, never silently routed around. Never pushes, commits, comments, or merges. | `.omp/agents/verify.md` — a different provider family from ship (`V7`; non-Anthropic, currently `openai-codex`-first) | high | `{run_id, work_id, verdict, derived_head_sha, evidence_grade, findings[], ambiguities[], recorded}` | `docs/delivery/seat-reliability.md` |
| **Dogfood checker** | Read-only, user-perspective agent run against the real CLI, not the test suite; selects and runs the `dogfood/` (`DOGFOOD-CORPUS`) slice tagged to a shipped change. Never fixes anything itself — no code, no docs, no issues filed directly; routing the healing is the watchtower's job, per `DELIVERY-STANCE`'s "dogfood feedback is the backlog." | anthropic (no dedicated `.omp/agents/*` definition yet) | high | PASS / BUG / FRICTION per scenario, with evidence (commands, exit codes, `status`/`history` excerpts) | `docs/delivery/seat-reliability.md` |

The **quality bar** every seat ships against is `docs/delivery/delivery-stance.md` (`DELIVERY-STANCE`). Verification-scout verdicts: MERGE / MERGE-WITH-FOLLOW-UPS / FIX-BEFORE-MERGE, with findings, doc-amendment deadlines, and explicit confirmations of what was positively verified.

Starting at M1a+ (`M-001`), ship agents and verification scouts also record their own observations directly into the delivery ledger through the `orc` CLI rather than the watchtower transcribing outcomes on their behalf — see `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) for the ship/verify recording protocol, role separation (no self-assurance), and the independent-derivation rule for verdicts. This is additive to the seats above, not a replacement: ship agents still ship, verification scouts still audit adversarially; the CLI is now how each records its own outcome, in addition to the PR-thread audit trail below.

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

## External-candidate lane

A pipeline note for the case the roles above don't cover: a candidate that arrives already-formed, with no ledger run behind it.

- **Not a delivery until the ledger says so.** A PR opened by an external contributor, or produced by an adopter/contributor session outside this project's own dispatch loop, is not a delivery yet no matter how complete it looks on GitHub — the ledger, not GitHub, decides what exists.
- **Adoption precedes judgment.** Such a candidate is adopted by a ship seat onto a current base, in that seat's own worktree, before anything about it can be judged. The adopting sha is the run's candidate; the proposed sha is recorded verbatim in the run's intent text so the provenance of what actually arrived stays legible.
- **Auditing spends the seat.** A seat that already audited the proposed sha cannot turn around and sign the adopted one — auditing is itself a use of that seat against that candidate, the same role-separation rule that forbids self-assurance elsewhere in this playbook.
- **Name the tradeoff, don't mandate a path.** Adopting in place — rebase and force-push onto the contributor's own branch — preserves the PR thread, its issue link, and the contributor's authorship. A fresh PR is the alternative when the branch cannot be written. Pick per case; state which in the run record.

**Specimen.** PR #270 (issue #269) arrived 2026-09-06 with no run behind it; its merge base (`3151a35`, v0.9.0) predates master's `4638f14`, so `gh` reports `CONFLICTING DIRTY` rather than a clean fast-forward. Per the operator decision of 2026-09-07, it was adopted in place onto current master. Compare the ordinary shape of the same class of issue when both ends are ours: issue #244 -> PR #247 was scouted, shipped, and verified entirely by our own seats within one run — no adoption step existed because no external candidate ever did.

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

## Conventions

- Local gate `bash scripts/check.sh` mirrors CI exactly; green locally means green remotely.
- Commits carry attribution trailers; PR bodies end with generation attribution.
- Run `python3 scripts/docs_check.py` before committing any documentation change.
- **Authoring the packaged `orc-ledger` skill's frontmatter `description`** (it is loaded by adopters' agents, including strict-YAML providers): (a) no colon-space (`: `) in an unquoted value — strict parsers (e.g. Pi's) read it as a nested mapping and the skill silently fails to load; single-quote the value and double inner apostrophes if a mid-sentence colon is unavoidable; (b) state **what + when** (the trigger phrases that should route to it) and never a how-summary of the workflow — a description that lists the steps makes the agent follow the summary and skip loading the body. The same colon-space caution applies to any doc frontmatter that a non-`docs_check` tool might strict-parse.
