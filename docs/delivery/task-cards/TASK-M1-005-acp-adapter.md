---
id: TASK-M1-005
type: task-card
status: current
authority: normative
description: Implement the acpx (ACP) ExecutionPort adapter driving Pi as the first agent, and a real-artifact CandidatePort, conformance-tested.
implements:
  - PORT-EXECUTION
  - PORT-CANDIDATE
verifies:
  - CONF-EXEC-001
  - CONF-EXEC-002
  - CONF-EXEC-003
  - CONF-EXEC-004
  - CONF-CAND-001
  - CONF-CAND-002
  - CONF-CAND-003
---

# TASK-M1-005 — ACP (acpx) adapter driving Pi

## Retarget note

This card supersedes the original "Claude Code headless (`claude -p`)" framing of `TASK-M1-005`, per a completed watchtower/scout assessment and a subsequent operator ruling on the first-agent choice. The `TASK-M1-005` id and its dependency edges (`TASK-M1-004`, `TASK-M1-002`) are unchanged; only the adapter's target protocol/runtime changes. `docs/delivery/task-cards/TASK-M1-005-claude-code-adapter.md` is renamed to this file; update any inbound links (`docs/delivery/task-cards/README.md`, `docs/INDEX.md`) to point here under the same `TASK-M1-005` id.

The first agent driven through the adapter is **Pi** (`acpx pi`, using gpt5.6-family models — model ids are opaque strings per `INV-014` and are never enumerated in contracts), not Claude Code. Rationale: the operator's workflow already exercises Claude Code and its subagents heavily (the watchtower process itself); M1b deliberately tests a different agent lineage, making the `P-001` providers-as-policy claim a real cross-provider proof rather than Claude-orchestrating-Claude. Claude Code remains available through the **same** adapter at zero additional cost and is the natural provider-swap demonstration — the second agent, already known-good manually.

## Outcome

Implement a `PORT-EXECUTION` adapter over the `acpx` CLI (an Agent Client Protocol client) driving Pi as its first configured agent (`acpx pi`), and a `PORT-CANDIDATE` adapter that fingerprints real artifacts (e.g. `git diff`) instead of scripted subjects — the `PORT-CANDIDATE` scope is unchanged from the original card. Assurance remains operator-recorded in M1b; a real assurance adapter is explicitly out of scope here (deferred to a later milestone).

All protocol/provider vocabulary — `acpx` CLI flags, session-scope keys, `acpxRecordId`/`acpxSessionId`/`agentSessionId`, process exit codes, ACP method names, agent binary names, and model ids — stays adapter vocabulary and belongs in `docs/adapters/acp/mapping.md`, never in core contracts or core domain logic, per `INV-014` and `docs/adapters/README.md`.

Record the durable ownership of `crew-report/v1` as a design-time open gate in the adapter's mapping doc — this task decides how the adapter journals execution reports for now (per the durability contract's disposition for that row) but does not resolve the standing `crew-report/v1` ownership question; that stays a deferred-decision ledger entry.

## Adapter shape

- Drive `acpx pi` with `--format json --json-strict` for structured NDJSON output — this is the concrete basis for advertising `CAP-EXEC-STRUCTURED-LIFECYCLE`.
- Sessions are always explicit and named (`-s <name>`), never anonymous. The session name is deterministically derived from the `INV-020` idempotency tuple `(delivery_run_id, work_id, attempt_number, effect_id)`.
- Session start MUST use `sessions ensure`, never `sessions new` — `ensure` is idempotent (create-or-attach), matching `FX-START-EXECUTION`'s idempotent-start requirement; `new` is not safe to retry.
- The adapter is agent-agnostic at the protocol layer: swapping the configured agent (e.g. to `acpx claude`) MUST require no adapter code change — this is the `P-001` provider-swap demonstration path.
- Pin the `acpx` version explicitly in `docs/adapters/acp/mapping.md` (0.13.1 at assessment time) and record the Node runtime dependency there as an accepted M1b-only, adapter-local dependency — `src/orc_werk/core` and its tests remain stdlib-only per `CLAUDE.md`.

## Advertised capability set

- `CAP-EXEC-SEND`
- `CAP-EXEC-CANCEL`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `CAP-EXEC-STRUCTURED-LIFECYCLE`

`CAP-EXEC-RESUME-EXACT` is explicitly **withheld**. `acpx`'s documented crash recovery transparently falls back to `session/new` when it cannot honor exact resume, and presenting that fallback as resume would violate `INV-013` (unsupported stronger semantics must fail explicitly, not be silently emulated). Agent-native resume commands (e.g. `claude --resume` when driving the Claude Code agent) are demoted to documented break-glass recovery — an operator/watchtower escape hatch, not part of the adapter's `PORT-EXECUTION` path.

The future proving condition for advertising `CAP-EXEC-RESUME-EXACT` (not required by this task, recorded for the next one that attempts it):

1. an id-comparison guard — a native `agentSessionId` is present in the ACP session `_meta` AND the `acpx` session id is verified unchanged across a resume attempt; **and**
2. durable `execution-session/v1` provenance is recorded per the `CONTRACT-CAPABILITIES` capability-durability rule (`TASK-M1-004`).

## Risk / spike — Pi ACP adapter maturity

The exact-resume proving condition above depends on the Pi ACP adapter's session-id fidelity, which is less established than the version-pinned Claude adapter's. Verifying Pi adapter maturity — session-id behavior (native `agentSessionId` presence and stability), resume behavior, and structured-lifecycle completeness — is part of the M1b spike, alongside the crash-mid-turn observability question in Acceptance below. If Pi adapter fidelity gaps are found, they narrow what the adapter may honestly advertise (per `INV-013` and the capability-durability rule); they do not license silent emulation.

## Depends on

`TASK-M1-004`, `TASK-M1-002`.

## Must not change

Capability honesty: the adapter MUST NOT claim `CAP-EXEC-RESUME-EXACT` without durable `execution-session/v1` session provenance, per `TASK-M1-004`'s `CONTRACT-CAPABILITIES` amendment (in flight as PR #26 at the time of this retarget).

## Mapping-doc requirements (footguns to record in `docs/adapters/acp/mapping.md`, not written by this card)

The following operational hazards MUST be documented in the mapping doc so the adapter implementation and its reviewers do not relearn them the hard way:

- always pass explicit `-s <session-name>` — never rely on an implicit/default session;
- `ensure`, never `new`, for session start, on every attempt including retries;
- a `cancel` call that exits `0` may mean "nothing to cancel" — a clean exit code alone does not prove a cancellation happened;
- permission-denied runs can exit looking successful (process exit 0) while no actual work occurred — these MUST map to canonical failure, not success, at the adapter boundary;
- `--approve-all` (or equivalent headless-permission posture) is a documented security stance, not a default — record its implications explicitly;
- `acpx status` values of `idle`/`dead` describe host/process state, never canonical settlement — settlement MUST be derived only from an observed `result.stopReason` (or, failing that, the adapter's own journal), never inferred from process/session status alone.

## Acceptance

- the adapter passes `CONF-EXEC-001` through `CONF-EXEC-004` and applicable `CONF-CAND-*` for every capability it advertises;
- `orc dispatch "<real task>"` produces a real candidate authored by a Pi run driven over ACP (`acpx pi`), journaled with `execution-session/v1` provenance;
- the run is resumable (pending/incremental mode, `TASK-M1-002`) after an orchestrator restart;
- a stub-`acpx` conformance harness (subprocess stub pattern, no live agent required) proves `CONF-EXEC-001` through `CONF-EXEC-004`;
- the M1b spike questions are answered and recorded: (a) crash-mid-turn observability — can a turn's final `stopReason` be recovered after the process that submitted it dies, or is that turn pending-until-reprompted? (b) Pi ACP adapter maturity per the Risk/spike section above. **Open spike questions — unanswered as of this card's authoring; they block the adapter's crash-boring resume claims, not this docs retarget.**
