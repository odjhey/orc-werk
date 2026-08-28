---
id: M-001
type: milestone
status: current
authority: normative
description: Second milestone — orc-werk becomes its own first user via a CLI-usable durable delivery ledger (M1a), agent-recorded push mode (M1a+), and a first real execution adapter (M1b).
---

# M1 — Delivery ledger

## Goal

M1 makes orc-werk its own first user. M0 proved the pure orchestration kernel could drive a scripted delivery loop to a verified terminal state entirely with in-memory/scripted providers; M1 puts real, valuable work through that same kernel, unamended in its core semantics.

M1 is delivered in two phases, with an explicit intermediate stage between them:

- **Phase M1a — CLI-usable ledger (no integrations).** The human/watchtower operator is the execution provider. The CLI becomes durable and usable enough to run a real multi-work delivery by hand, with outcomes recorded by the operator as they become known rather than supplied up front by a script.
- **Stage M1a+ — agents record via CLI (push mode).** Subagents (ship/verify agents) call the orc CLI themselves to record observations, instead of the operator transcribing on their behalf. Push mode delivers real multi-agent orchestration with zero adapters and de-risks M1b's ExecutionPort design.
- **Phase M1b — first real adapter.** The execution seat is automated with the first genuine `PORT-EXECUTION` provider: Claude Code headless (`claude -p`).

Both phases exercise value claims that only matter once real, non-scripted work is on the line:

- **"Done is a claim, not a fact."** `INV-003`/`P-003` stop being a paper guarantee and start gating real candidate-bound assurance (`INV-005` through `INV-010`) on work whose outcome the operator does not yet know at dispatch time.
- **Durable, auditable orchestration truth.** `PORT-JOURNAL` becomes the record of a delivery that actually happened, not a scripted rehearsal — `P-008`'s append-preserving history is read live while dogfooding, not just asserted in tests.
- **Crash-boring resume.** Self-healing stays journal-replay/idempotent-effect/bounded-policy driven (`INV-020`, `DELIVERY-STANCE`'s heal-while-using bar), now proven against a process that can be killed mid-flight for real, not just between scripted steps.
- **Providers as policy.** M1b swaps the execution provider from scripted to real without touching kernel semantics (`P-001`) — the same `PORT-EXECUTION` contract, honestly capability-gated (`INV-013`).

## Phase M1a — CLI-usable ledger

No new integrations; the operator is the execution and assurance provider.

### Pending/incremental mode is the M1a default

Incremental/pending mode is the **default** dispatch mode in M1a, not an opt-in variant. A config with no recorded outcome for the next attempt means **pending**: `orc dispatch` stops cleanly with the Work at `EXECUTING` and exits with a distinct exit code (an addition to the CLI's existing `0`/`1`/`2` exit-code contract in `docs/playbooks/cli-usage.md`, not a replacement of it). The operator resumes the run by recording the real outcome (candidate content, assurance verdict) and re-running the same `orc dispatch` command, which advances the run via ordinary idempotent replay (`INV-020`) — no separate "resume" command.

A work attempt whose outcome is not yet known is **PENDING, not failed**. Fully scripted attempts (every outcome supplied up front, as M0's config shape already allows) remain supported as the opt-in simulation/testing mode — what the automated test suite and the dogfood corpus use. The default reflects who M1a is actually for: the incremental operator recording reality attempt-by-attempt is the first real user of the ledger; a fully-scripted run is the special case that exists for repeatable, deterministic testing.

This is contract-first work:

- a new golden scenario, SCN-007 (pending execution / operator-recorded settlement), authored before implementation. SCN-007 must specify the default-mode semantics explicitly: no recorded outcome for the next attempt is pending by default, the distinct in-progress exit code, and that recording an outcome plus re-dispatching advances the run;
- a short normative clause added to `STATE-DELIVERY`'s "Mechanical fact sequencing" section stating that the absence of a settlement observation is not a settlement — no fact is fabricated for waiting.

This must not disturb `STATE-DELIVERY`'s existing dispatch-gate-failure normalization rule (mechanical fact sequencing item 6): capability failures remain failed attempts (`FACT-EXEC-STARTED` + synthetic-ref `FACT-EXEC-SETTLED(failed)`), routed through the ordinary retry/`DEC-BLOCK` machinery. Only a started-but-unobserved outcome is pending; an unsupported capability is never pending.

### CLI UX batch (#16, #17, #18, #23)

- **#16** — root-cause surfacing via CLI presentation: read journaled effect records' `dispatch_result` and surface it in `status`/`dispatch` output, e.g. `blocked_reason=retry-budget-exhausted (root_cause=ERR-UNSUPPORTED-CAPABILITY)`. Presentation-only; no contract change.
- **#17** — strict config validation at load time: reject unknown top-level keys and require `attempts` coverage for every planned Work, as canonical `ERR-VALIDATION` before any dispatch. The config schema is CLI-owned/non-normative; no contract change.
- **#18** — torn-tail content-blindness refinement. This requires a docs amendment to `PORT-JOURNAL`'s durable-journal recovery clause: only tolerate a torn tail when at least one valid record precedes it, and/or the line looks like truncated JSON (starts with `{`). Fail closed otherwise. The current behavior is normatively correct as written today, so the contract must change before the code does.
- **#23** — `status` shows the submitted intent text (`FACT-INTENT-SUBMITTED.data.text`) instead of the run id under the `intent:` label.

### M1a acceptance

An operator can run a real multi-work delivery (e.g. this repo's own PRs modeled as Works) purely through `orc dispatch`/`status`/`history`, in the default pending/incremental mode, with hand-recorded outcomes appended between dispatches, surviving process exits between every step.

## Stage M1a+ — agents record via CLI (push mode)

Between M1a and M1b sits an explicit intermediate stage: the recording seat moves from the human operator to the subagents themselves, while the execution seat stays unautomated (no adapters). Ship/verify agents call the orc CLI to record their own observations:

- a **ship agent** claims its Work, does the work, and records the execution settlement and candidate;
- a **separate verification agent** records the assurance verdict with `evidence_refs`;
- **no agent ever records a decision** — decisions remain kernel policy per `INV-011`.

Recorded outcomes are observations/claims only: an agent recording `completed` or `accepted` is submitting a claim into the ledger, never committing acceptance itself. The kernel enforces claim ≠ acceptance structurally (`INV-003`, `INV-011`); role separation — the settlement recorder and the verdict recorder MUST be different agents — is process discipline, documented rather than kernel-enforced at this stage.

Rationale: push mode delivers real multi-agent orchestration with zero adapters and de-risks M1b's ExecutionPort design.

### M1a+ deliverable — agent CLI guidance playbook

A written guidance playbook for agents using the CLI, under `docs/playbooks/` (e.g. an agent-cli-usage playbook, or a clearly-scoped section of `PLAYBOOK-CLI-USAGE`), covering:

- role separation — never self-assurance: the settlement recorder and the verdict recorder MUST be different agents;
- claim-before-work;
- one writer per run journal;
- what belongs in candidate content;
- exit-code handling (including the M1a in-progress exit code);
- that recorded outcomes are observations/claims only, with the structural-vs-discipline note above.

Sequencing: this playbook is authored **after** SCN-007 fixes the command surface — guidance must not precede the commands it documents. It depends on `TASK-M1-001` and `TASK-M1-002`.

## Phase M1b — first real adapter (Claude Code headless ExecutionPort)

### Prerequisite docs

Per the issue #12 watchtower assessment, these land before the adapter ships:

- `docs/contracts/durability-responsibilities.md` — the durability-obligations contract plus the Rozoro retirement ledger (source-object → semantic guarantee → Orc disposition → durable owner → contract/schema → verification). Planned-rows (contracts not yet built) are allowed; every row must reach one of canonicalized/delegated/implementation-local/intentionally-dropped, even if the disposition is "planned."
- `execution-session/v1` — registered under `docs/extensions/`, satisfying `CONTRACT-EXTENSIONS` (`EXT-001` through `EXT-007`). Session id, resume strength + ref, `transcript_ref` as a reference only (never inlined content, per `PORT-JOURNAL`'s "not an artifact store" boundary), provider/model carried as opaque strings (`INV-014`). Dispatcher/watchtower/preset/policy provenance is a separate extension, not a field inside `execution-session/v1`.
- A `CONTRACT-CAPABILITIES` amendment: a capability MUST NOT be claimed when its durability obligations are unmet — concretely, `CAP-EXEC-RESUME-EXACT` requires durable session provenance (`execution-session/v1`) before an adapter may advertise it.

### Adapter

`PORT-EXECUTION` over `claude -p` headless runs; provider vocabulary (CLI flags, session file shapes, model names) stays in the adapter and its mapping doc, never in core contracts (`INV-014`, `docs/adapters/README.md`). `PORT-CANDIDATE` fingerprints real artifacts (e.g. `git diff`) instead of scripted subjects. Assurance may remain operator-recorded in M1b — a real assurance adapter is explicitly deferred to a later milestone (M2), not implied by this one. The adapter must pass the existing `CONF-EXEC-001` through `CONF-EXEC-004` suite (and applicable `CONF-CAND-*`) for every capability it advertises, and capability advertisement must be honest under the new durability rule above.

### Open gate

Durable ownership of `crew-report/v1` (the adapter's append-only execution report log) is a decision due at M1b design time, recorded here as an open gate — not resolved by this milestone doc. The issue #12 watchtower recommendation is an adapter-owned append-only log; the ack/open-item state question and the multi-work `work-spec/v1` owner question are recorded alongside it as the same class of deferred decision.

### M1b acceptance

`orc dispatch "<real task>"` produces a real candidate authored by a Claude Code headless run, journaled with `execution-session/v1` provenance, and is resumable after an orchestrator restart.

## Required contracts

- `STATE-DELIVERY` (amended: pending-mode clause; mechanical fact sequencing item 6 unchanged)
- `PORT-JOURNAL` (amended: durable-journal recovery clause refinement for #18)
- `CONTRACT-CAPABILITIES` (amended: durability-honesty rule)
- `CONTRACT-EXTENSIONS` (governs `execution-session/v1` registration)
- `docs/contracts/durability-responsibilities.md` (new, with Rozoro retirement ledger)
- `PORT-EXECUTION`, `PORT-CANDIDATE` (adapter conformance)
- `CONTRACT-ERRORS` (`ERR-VALIDATION` reused for #17; no new error values)

## Required scenarios

- SCN-007 (pending execution / operator-recorded settlement) — new, authored before implementation
- `SCN-001` through `SCN-006` continue to pass unmodified (regression bar)
- Existing `CONF-EXEC-*`/`CONF-CAND-*` conformance suite, re-run against the Claude Code headless adapter

## Required implementation

- pending/incremental dispatch semantics in the application layer and CLI;
- CLI UX batch: root-cause presentation, strict config validation, refined torn-tail recovery, intent-text display;
- agent CLI guidance playbook under `docs/playbooks/` (M1a+, authored after SCN-007 fixes the command surface);
- `docs/contracts/durability-responsibilities.md` and the `execution-session/v1` extension schema;
- `CONTRACT-CAPABILITIES` durability-honesty amendment;
- Claude Code headless `PORT-EXECUTION` adapter under `src/orc_werk/` (adapters layer only — `src/orc_werk/core` remains integration-free per `CLAUDE.md`);
- real-artifact `PORT-CANDIDATE` adapter (git diff fingerprinting).

## Acceptance

- **M1a:** an operator can run a real multi-work delivery (e.g. this repo's own PRs as works) purely through `orc dispatch`/`status`/`history` with hand-recorded outcomes, surviving process exits between every step.
- **M1a+:** ship/verify agents record their own observations (settlement + candidate by the ship agent; assurance verdict with `evidence_refs` by a separate verification agent) through the orc CLI per the agent guidance playbook, with no agent recording decisions and no self-assurance.
- **M1b:** `orc dispatch "<real task>"` produces a real candidate authored by a Claude Code headless run, journaled with `execution-session/v1` provenance, resumable after orchestrator restart.

## Out of scope

- attention/AttentionPort machinery;
- `DEC-ESCALATE`/`DEC-CANCEL` activation;
- Beads/zxro adapters;
- real assurance automation (assurance stays operator-recorded through M1b; a real assurance adapter is a later milestone);
- `crew-report/v1` implementation (design decision only — see the M1b open gate);
- mutation/property tooling (per `DELIVERY-STANCE`);
- Go rewrite.
