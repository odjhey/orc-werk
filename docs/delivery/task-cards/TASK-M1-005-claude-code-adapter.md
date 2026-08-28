---
id: TASK-M1-005
type: task-card
status: current
authority: normative
description: Implement the Claude Code headless ExecutionPort and a real-artifact CandidatePort, conformance-tested.
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

# TASK-M1-005 — Claude Code headless adapter

## Outcome

Implement a `PORT-EXECUTION` adapter over `claude -p` headless runs (provider vocabulary — CLI flags, session file shapes, model names — stays in the adapter and its mapping doc per `docs/adapters/README.md`, never in core contracts, per `INV-014`), and a `PORT-CANDIDATE` adapter that fingerprints real artifacts (e.g. `git diff`) instead of scripted subjects. Assurance remains operator-recorded in M1b; a real assurance adapter is explicitly out of scope here (deferred to a later milestone).

Record the durable ownership of `crew-report/v1` as a design-time open gate in the adapter's mapping doc — this task decides how the adapter journals execution reports for now (per the durability contract's disposition for that row) but does not resolve the standing `crew-report/v1` ownership question; that stays a deferred-decision ledger entry.

## Depends on

`TASK-M1-004`, `TASK-M1-002`.

## Must not change

Capability honesty: the adapter MUST NOT claim `CAP-EXEC-RESUME-EXACT` without durable `execution-session/v1` session provenance, per `TASK-M1-004`'s `CONTRACT-CAPABILITIES` amendment.

## Acceptance

- the adapter passes `CONF-EXEC-001` through `CONF-EXEC-004` and applicable `CONF-CAND-*` for every capability it advertises;
- `orc dispatch "<real task>"` produces a real candidate authored by a Claude Code headless run, journaled with `execution-session/v1` provenance;
- the run is resumable (pending/incremental mode, `TASK-M1-002`) after an orchestrator restart.
