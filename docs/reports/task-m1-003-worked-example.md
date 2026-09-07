---
id: REPORT-TASK-M1-003-WORKED-EXAMPLE
type: report
status: current
authority: informative
description: Worked example - the real ship/verify recording loop from TASK-M1-003's own CLI-UX PR, walked fact-by-fact through the ledger. Moved from PLAYBOOK-AGENT-CLI's former §7 (TASK-M5-002); nothing about the loop it describes has changed.
---

# Worked example — task-m1-003

This section moved here verbatim from `docs/playbooks/agent-cli-usage.md`
(`PLAYBOOK-AGENT-CLI`)'s former §7, as part of `TASK-M5-002`'s playbook
shrink (`T6`: appended, not deleted). It is historical reference, not
canonical protocol — the protocol itself lives in `PLAYBOOK-AGENT-CLI`
§§3-4.

This is the real record sequence from a completed run in this
repository's own delivery history (`.orc/task-m1-003.jsonl`), tracking
`TASK-M1-003`'s own CLI-UX PR through the ledger. It predates
`PLAYBOOK-AGENT-CLI` and was recorded through the same config/backing-store
observation path an agent uses under that playbook (§5) — it is the exact
loop a ship agent and a verification agent perform under push mode,
summarized here rather than dumped record-for-record:

1. **Intent submitted, Work created and claimed, dispatched.** `FACT-INTENT-SUBMITTED` → `FX-CREATE-WORK`/`FACT-WORK-CREATED` → `FX-CLAIM-WORK`/`FACT-WORK-CLAIMED` → `FACT-WORK-READY` → `DEC-DISPATCH` (kernel decision, not agent-recorded) → `FX-START-EXECUTION`/`FACT-EXEC-STARTED` for attempt 1.
2. **Ship agent does the work and records settlement + candidate.** The next `orc dispatch` invocation, before the outcome was recorded, would have stopped at exit `3` (pending, awaiting `execution-outcome`) per `SCN-007` — the same wait an agent sees today. Once the PR existed, the ship agent recorded the execution settlement (`outcome: completed`) and a candidate whose content is externally resolvable identity, not prose: `{"pr": 32, "head_sha": "c9b1390d..."}`. Re-dispatching journaled `FACT-EXEC-SETTLED(completed)` and `FACT-CANDIDATE-OBSERVED` (fingerprint `fp-204c92f5...`), then `DEC-REQUEST-ASSURANCE` (kernel decision) moved the Work to `ASSURING`.
3. **Pending again, this time for assurance.** With no verdict recorded yet, dispatch would stop at exit `3` (pending, awaiting `assurance-verdict`) — `FX-START-ASSURANCE`/`FACT-ASSURE-STARTED` journaled, nothing fabricated for the missing verdict.
4. **Verification agent independently derives the candidate and records its verdict.** The verification agent — a *different* agent from the one that recorded step 2's settlement, per Role separation — did not copy `fp-204c92f5...`/`pr 32`/the head sha from the ship agent's record. It independently fetched PR #32 and computed the head sha itself, then recorded its verdict against that self-derived identity. Because the independently derived fingerprint matched, assurance settled `accepted`: `FACT-ASSURE-SETTLED(accepted)`. (Had it mismatched, the correct move per `PLAYBOOK-AGENT-CLI` §4 is to report `ERR-CONFLICT`, not reconcile it away.)
5. **Acceptance and completion — kernel decisions, not agent-recorded.** `DEC-ACCEPT` → `FX-COMPLETE-WORK`/`FACT-WORK-COMPLETED`. Final re-dispatch would exit `0`.

Notice what the two agent seats did and did not do: the ship agent
recorded a settlement and a resolvable candidate, never a verdict on its
own work; the verification agent recorded a verdict derived from its own
independent fetch, never copied from the settlement record; neither
agent recorded any `DEC-*`. That is the whole loop.

## Related

- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) — the canonical ship/verify recording protocol this example illustrates
