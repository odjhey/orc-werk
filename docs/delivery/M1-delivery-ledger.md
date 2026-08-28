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
- **Phase M1b — first real adapter.** The execution seat is automated with the first genuine `PORT-EXECUTION` provider: the `acpx` CLI (Agent Client Protocol) driving Pi as the first agent behind it.

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
- **#17** — strict config validation at load time: reject unknown top-level keys and require `attempts` coverage for every planned Work, as canonical `ERR-VALIDATION` before any dispatch. The config schema is CLI-owned/non-normative; no contract change. **Re-scoped per the PR #29 verification ruling:** the "require `attempts` coverage" clause must be reconciled with the SCN-007 pending default — a config with no `attempts` key at all, or a planned Work with no entry, is the valid fully-incremental case and MUST NOT be rejected. Load-time `ERR-VALIDATION` applies only to structurally malformed or partial-and-inconsistent `attempts` entries (wrong types, unknown keys inside an entry); any stricter full-coverage requirement is opt-in (e.g. a `--strict` flag), not the default.
- **#18** — torn-tail content-blindness refinement. This requires a docs amendment to `PORT-JOURNAL`'s durable-journal recovery clause: only tolerate a torn tail when at least one valid record precedes it, and/or the line looks like truncated JSON (starts with `{`). Fail closed otherwise. The current behavior is normatively correct as written today, so the contract must change before the code does.
- **#23** — `status` shows the submitted intent text (`FACT-INTENT-SUBMITTED.data.text`) instead of the run id under the `intent:` label.

### M1a acceptance

An operator can run a real multi-work delivery (e.g. this repo's own PRs modeled as Works) purely through `orc dispatch`/`status`/`history`, in the default pending/incremental mode, with hand-recorded outcomes appended between dispatches, surviving process exits between every step.

## Stage M1a+ — agents record via CLI (push mode)

Between M1a and M1b sits an explicit intermediate stage: the recording seat moves from the human operator to the subagents themselves, while the execution seat stays unautomated (no adapters). Ship/verify agents call the orc CLI to record their own observations:

- a **ship agent** claims its Work, does the work, and records the execution settlement and candidate;
- a **separate verification agent** records the assurance verdict with `evidence_refs`;
- **no agent ever records a decision** — decisions remain kernel policy per `INV-011`;
- an agent's own turn-by-turn narration is durably recorded via the `crew-report/v1` file-based reference report log (`TASK-M1-007`), sequenced at the start of this stage — beside, not inside, the settlement/candidate/verdict observations above.

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

## Phase M1b — first real adapter (acpx ExecutionPort driving Pi)

### Retarget note (supersedes the original Claude Code headless framing)

Per a completed watchtower/scout assessment (issue #12 follow-on) and a subsequent operator ruling on the first-agent choice, M1b's `PORT-EXECUTION` target is retargeted from `claude -p` headless invocation to the `acpx` CLI — an Agent Client Protocol (ACP) client — driving **Pi** as its first agent (`acpx pi`, using gpt5.6-family models; model ids are carried as opaque strings per `INV-014` and are never enumerated in contracts). `docs/adapters/acp/` already carries draft stubs anticipating this shape; this section makes them binding for M1b. M1a and M1a+ are **unaffected** by this retarget — both phases remain operator/agent-CLI-driven with zero execution adapters, exactly as delivered.

Rationale, concisely:

- the port shape maps natively onto ACP: idempotent session `ensure` corresponds to `FX-START-EXECUTION`'s idempotent start; ACP's first-class send/cancel messages map directly onto `CAP-EXEC-SEND`/`CAP-EXEC-CANCEL`; raw ACP NDJSON output is exactly `CAP-EXEC-STRUCTURED-LIFECYCLE`;
- one protocol adapter can serve many agents, making `P-001` (providers as policy) concrete rather than aspirational — the same `acpx`-backed `PORT-EXECUTION` adapter is not agent-specific at the protocol layer, only its first configured agent is;
- **Pi-first is a deliberate cross-provider proof.** The operator's workflow already exercises Claude Code and its subagents heavily — the watchtower process itself runs on them. Driving a different agent lineage through the adapter makes the `P-001` providers-as-policy claim a real cross-provider proof rather than Claude-orchestrating-Claude. Claude Code remains available through the **same** adapter at zero additional cost and becomes the natural provider-swap demonstration: it is the second agent, already known-good manually;
- the operator's surrounding ecosystem (the `zxro` runtime-port contract, `rozoro`, the `no-mistakes` production driver) is converging on ACP as the common runtime/session transport;
- `docs/adapters/acp/` already carries draft capability/mapping/conformance stubs anticipating exactly this adapter.

### Prerequisite docs

Per the issue #12 watchtower assessment, these land before the adapter ships:

- `docs/contracts/durability-responsibilities.md` — the durability-obligations contract plus the Rozoro retirement ledger (source-object → semantic guarantee → Orc disposition → durable owner → contract/schema → verification). Planned-rows (contracts not yet built) are allowed; every row must reach one of canonicalized/delegated/implementation-local/intentionally-dropped, even if the disposition is "planned." **Status: in flight as PR #26 (`TASK-M1-004`), not yet merged to `master` as of this retarget** — the durability-honesty rule below is written as a requirement M1b's adapter must satisfy once that PR lands, not as an already-canonical fact.
- `execution-session/v1` — registered under `docs/extensions/`, satisfying `CONTRACT-EXTENSIONS` (`EXT-001` through `EXT-007`). Session id, resume strength + ref, `transcript_ref` as a reference only (never inlined content, per `PORT-JOURNAL`'s "not an artifact store" boundary), provider/model carried as opaque strings (`INV-014`). Dispatcher/watchtower/preset/policy provenance is a separate extension, not a field inside `execution-session/v1`. Also part of PR #26, in flight.
- A `CONTRACT-CAPABILITIES` amendment (the capability-durability rule): a capability MUST NOT be claimed when its durability obligations are unmet — concretely, `CAP-EXEC-RESUME-EXACT` requires durable session provenance (`execution-session/v1`) before an adapter may advertise it. Also part of PR #26, in flight.

### Adapter

`PORT-EXECUTION` over the `acpx` CLI driving Pi as the first agent: `acpx pi`, `--format json --json-strict` for structured NDJSON output, and explicit named sessions created via `sessions ensure` (never `sessions new`) — the session name is derived deterministically from the `INV-020` idempotency tuple so that `ensure` is itself the idempotent start. Provider/protocol vocabulary (acpx flags, scope keys, ACP method names, session id fields, exit codes, agent binary names, model ids) stays in the adapter and its mapping doc, never in core contracts (`INV-014`, `docs/adapters/README.md`).

**Advertised capability set at M1b:**

- `CAP-EXEC-SEND`
- `CAP-EXEC-CANCEL`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `CAP-EXEC-STRUCTURED-LIFECYCLE`

**`CAP-EXEC-RESUME-EXACT` is explicitly withheld at M1b.** `acpx`'s documented crash-recovery behavior transparently falls back to `session/new` when exact resume cannot be honored, and `INV-013` forbids presenting that silent fallback as resume. The proving condition for advertising exact resume in a future milestone is: (1) a native `agentSessionId` is present in the ACP session (`_meta`) AND the `acpx` session id is verified unchanged across a resume, plus (2) durable `execution-session/v1` provenance per the capability-durability rule above. Note that this proving condition depends on the Pi ACP adapter's session-id fidelity, which is less established than the version-pinned Claude adapter's — verifying Pi adapter maturity is part of the M1b spike (see the task card). Until the condition is proven, agent-native resume commands (e.g. `claude --resume` when driving the Claude Code agent) are demoted to documented break-glass recovery (an operator/watchtower escape hatch) — they are not part of the adapter's `PORT-EXECUTION` path.

`PORT-CANDIDATE` fingerprints real artifacts (e.g. `git diff`) instead of scripted subjects — unchanged from the original M1b scope. Assurance may remain operator-recorded in M1b — a real assurance adapter is explicitly deferred to a later milestone (M2), not implied by this one. The adapter must pass the existing `CONF-EXEC-001` through `CONF-EXEC-004` suite (and applicable `CONF-CAND-*`) for every capability it advertises, and capability advertisement must be honest under the durability rule above.

The `acpx` version is pinned (`0.13.1` at assessment time; the pin is recorded in `docs/adapters/acp/mapping.md`), and the adapter carries a Node runtime dependency as an accepted M1b-only dependency — `src/orc_werk/core` and its tests remain stdlib-only per `CLAUDE.md`; the `acpx`/Node dependency is confined to the adapter layer, exactly the kind of integration the reference architecture quarantines away from core.

### Open gate

Durable ownership of `crew-report/v1` (the adapter's append-only execution report log) was recorded here as an open gate due at M1b design time. **Resolved ahead of M1b**: `crew-report/v1` is registered under `docs/extensions/crew-report/` (`EXT-CREW-REPORT-V1`) with the issue #12 watchtower-recommended disposition — an adapter-owned append-only log, one NDJSON file per `DeliveryRun` — and its file-based reference implementation is carded as `TASK-M1-007`, sequenced at the start of M1a+. `docs/contracts/durability-responsibilities.md`'s ownership matrix and retirement ledger reflect this resolution. The report ack/open-item state question remains **OPEN**, explicitly out of `crew-report/v1`'s scope and reserved for a future companion contract; the multi-work `work-spec/v1` owner question also remains open and is unaffected by this resolution.

### M1b acceptance

`orc dispatch "<real task>"` produces a real candidate authored by a Pi run driven over ACP (`acpx pi`), journaled with `execution-session/v1` provenance (a native `agentSessionId` when present — optional by schema — with the resume ref carrying the `acpx` scope tuple), and is resumable after an orchestrator restart.

Two additional acceptance items beyond the original scope:

1. a stub-`acpx` conformance harness (subprocess stub pattern, matching the existing scripted-adapter test style) that proves `CONF-EXEC-001` through `CONF-EXEC-004` without requiring a live agent;
2. a resolved live-spike answer to a crash-mid-turn observability question — whether a turn's final `stopReason` can be recovered after the process that submitted it dies, or whether that turn is instead pending-until-reprompted. Verifying Pi ACP adapter maturity (session-id fidelity, resume behavior, structured-lifecycle completeness) is part of this same M1b spike. These are recorded as open spike questions on the task card until the operator answers them; they are not blocking for this docs retarget but block the adapter's crash-boring claims.

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
- Existing `CONF-EXEC-*`/`CONF-CAND-*` conformance suite, re-run against the `acpx`-driving-Pi adapter, including a stub-`acpx` subprocess harness proving `CONF-EXEC-001` through `CONF-EXEC-004` without a live agent

## Required implementation

- pending/incremental dispatch semantics in the application layer and CLI;
- CLI UX batch: root-cause presentation, strict config validation, refined torn-tail recovery, intent-text display;
- agent CLI guidance playbook under `docs/playbooks/` (M1a+, authored after SCN-007 fixes the command surface);
- `docs/contracts/durability-responsibilities.md` and the `execution-session/v1` extension schema;
- `CONTRACT-CAPABILITIES` durability-honesty amendment;
- `acpx`-driving-Pi `PORT-EXECUTION` adapter under `src/orc_werk/` (adapters layer only — `src/orc_werk/core` remains integration-free per `CLAUDE.md`; the `acpx`/Node dependency is confined to this adapter layer as an accepted M1b-only dependency);
- real-artifact `PORT-CANDIDATE` adapter (git diff fingerprinting);
- stub-`acpx` conformance harness (subprocess stub pattern) for `CONF-EXEC-001` through `CONF-EXEC-004`.

## Acceptance

- **M1a:** an operator can run a real multi-work delivery (e.g. this repo's own PRs as works) purely through `orc dispatch`/`status`/`history` with hand-recorded outcomes, surviving process exits between every step.
- **M1a+:** ship/verify agents record their own observations (settlement + candidate by the ship agent; assurance verdict with `evidence_refs` by a separate verification agent) through the orc CLI per the agent guidance playbook, with no agent recording decisions and no self-assurance.
- **M1b:** `orc dispatch "<real task>"` produces a real candidate authored by a Pi run driven over ACP (`acpx pi`), journaled with `execution-session/v1` provenance (native `agentSessionId` when present, resume ref = the `acpx` scope tuple), resumable after orchestrator restart. `CAP-EXEC-RESUME-EXACT` is withheld at M1b (see the Phase M1b adapter section); agent-native resume commands are documented break-glass recovery only.

## Out of scope

- attention/AttentionPort machinery;
- `DEC-ESCALATE`/`DEC-CANCEL` activation;
- Beads/zxro adapters;
- real assurance automation (assurance stays operator-recorded through M1b; a real assurance adapter is a later milestone);
- a real `PORT-EXECUTION` adapter producing `crew-report/v1` reports automatically (`TASK-M1-007` carries the file-based reference log; wiring a live adapter to it is `TASK-M1-005`'s and later work's concern) and the `crew-report/v1` ack/open-item companion contract (explicitly out of `crew-report/v1`'s own scope, remains open per `docs/contracts/durability-responsibilities.md`);
- mutation/property tooling (per `DELIVERY-STANCE`);
- Go rewrite.
