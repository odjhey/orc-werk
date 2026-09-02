---
id: PLAYBOOK-AGENT-CLI
type: playbook
status: current
authority: informative
description: Guidance for ship/verify subagents recording their own observations through the orc CLI (M1a+ push mode).
---

# Agent CLI usage playbook

This playbook is for **agents** — ship agents and verification agents — recording their own observations into the `orc` CLI during the M1a+ stage (`M-001`, `TASK-M1-006`). It complements, and does not duplicate, `docs/playbooks/cli-usage.md` (`PLAYBOOK-CLI-USAGE`): read that document first for commands, config shape, and the exit-code contract (including exit `3`, pending). This playbook only adds the discipline an agent must follow on top of that surface. Informative only — canonical semantics live in the contracts it cites.

## 1. What you are doing

You are recording **observations** into a durable delivery ledger — nothing more. Every outcome you record (`completed`, `failed`, `accepted`, `rejected`, `inconclusive`, a candidate) is a **claim**, not a fact the kernel takes on faith. Acceptance happens only through the kernel's candidate-bound assurance machinery (`INV-003`, `INV-005` through `INV-010`): recording `accepted` yourself does not accept the Work.

You **never record a decision**. `DEC-*` records (`DEC-DISPATCH`, `DEC-REQUEST-ASSURANCE`, `DEC-ACCEPT`, `DEC-RETRY`, `DEC-BLOCK`, ...) are kernel policy, attributed per `INV-011`. Nothing in your CLI usage should be read as, or attempt to be, a decision. You submit inputs (settlements, candidates, verdicts); the kernel decides.

`DEC-CANCEL`/`FACT-WORK-CANCELLED` (`SCN-011`, `orc cancel`) is an operator-only terminal closure and is never recorded by a ship/verify agent. Agents must not close Work without acceptance or fabricate a verdict to imitate cancellation; hand deliberate closure to the operator.

`DEC-ABANDON-ATTEMPT` (`TASK-M3B-001`, `--abandon-work`/`--abandon-reason`/`--abandon-by` on `orc dispatch`, `PLAYBOOK-CLI-USAGE`) is likewise not something you record as a ship/verify agent: it is an operator power, exercised when a run's own state cannot resolve a stuck attempt on its own (an irrecoverable candidate-observation conflict, or an assurance you have out-of-band reason to believe will never settle). If your run looks stuck for either reason, stop and hand it to the operator rather than working around it — recording your own outcome to force past a conflicted/unsettleable resting point is exactly the fabrication `DEC-ABANDON-ATTEMPT` exists to avoid.

## 2. Role separation (MUST) — no self-assurance, ever

**The agent that records an execution settlement/candidate for a Work MUST NOT also record the assurance verdict for that same candidate.** Ship agents record settlements. A *different* verification agent records verdicts. This is process discipline, not kernel-enforced at this stage (`M-001` M1a+ section): the kernel enforces claim ≠ acceptance structurally (`INV-003`/`INV-011`), but it does not itself know or check which agent identity is typing the command. Self-assurance is a playbook violation even though the CLI will not reject it.

If you are unsure which seat you are in, stop and ask rather than guess — recording a verdict on your own candidate defeats the entire point of candidate-bound assurance.

### Executor identity when no adapter journals the seat

When a seat's execution is not adapter-journaled with `execution-session/v1` provenance — for example, a ship agent working as an external executor that pushes its own observation in (the ordinary case since `ADR-0005`) — put an `executor-identity/v1` payload (model/tool, session reference, per-seat reference, role) under the `extensions` key. A ship seat puts it on that Work's execution attempt entry in the dispatch config (`attempts.<work_id>[n].extensions`; `orc config-schema` prints the full, current attempt-entry key set); a verify seat puts the same extension on its assurance entry as described in §4. Config-entry `extensions` transport losslessly into the corresponding settled Fact per `CONF-EXT-003` (issues #105/#106), so the identity payload becomes part of the durable journal and is visible via `orc history`/`orc refs` — read-only, no new recording mechanism. Agents populate the registered `executor-identity/v1` extension according to `EXT-EXECUTOR-IDENTITY-V1` (for example, `"executor-identity/v1": {"model": "...", "session_ref": "...", "seat_ref": "...", "role": "ship"}`). `seat_ref` is an agent- or thread-level identifier — such as a subagent id, spawn reference, or per-seat nonce — that is stable for that seat and distinct between seats. The ship seat's and verify seat's identity payloads for the same candidate must be distinguishable from the journal alone; `session_ref` by itself is insufficient when both seats run as subagent threads of one orchestrating session, as occurred in issue #182. The registered schema defines the payload shape, which is transported unchanged and cannot override canonical core fields (`EXT-003`, `EXT-007`). This gives blind reconstruction the executor identity that an adapter-managed execution would otherwise have journaled — the `crew-report/v1` sidecar this section used to point at is removed (`EXT-CREW-REPORT-V1`, superseded, issue #100 part 2).

## 3. Ship-agent protocol

1. **Claiming is orchestrator-mechanical, not something you invoke.** There is no `orc claim` command. A claim is once per Work lineage (`PORT-WORK-004`, `INV-020`'s reduced-key form) — it is held by its claimant across all retry attempts and is never re-acquired on retry — but the CLI journals `FACT-WORK-CLAIMED` automatically at dispatch, as part of the ordinary `FX-CLAIM-WORK` effect; you do not, and cannot, issue a separate claim step. Your discipline is instead: **do not dispatch/work a run, or a Work within a shared-config run, that another agent is actively working.** If you are unsure whether a run or Work is already in flight, check `orc history <run>` for a recent `FACT-WORK-CLAIMED`/`FACT-EXEC-STARTED` you did not produce yourself, and hold off rather than racing it.
2. **Do the work.**
3. **Record the outcome and candidate** for the config/backing store the ExecutionPort reads (see Mechanics below) — not prose. Candidate content MUST be **externally resolvable identity**: a PR number, a head sha, a run URL — anything a stranger with no access to your reasoning could independently fetch and check. Never record a description of what you did as the candidate; a sentence is not verifiable, an artifact reference is.
4. **Re-dispatch** (`orc dispatch`, same command, same journal) to advance the run. This is always safe — see Mechanics.
5. **Expect exit `3` (pending)** after you record a settlement but before a verification agent has recorded a verdict. That is the run resting at `ASSURING`, correctly. It is not an error and not something for you to work around by recording your own verdict (see Role separation above).

## 4. Verification-agent protocol

1. **Derive the candidate identity independently from the artifact itself.** Fetch the PR. Compute the head sha yourself (`git rev-parse`, the GitHub API, whatever your tooling is — but *you* run it). Do not read the shipper's recorded fingerprint/sha and copy it into your verdict.
2. **Record your verdict against your own self-derived identity**, never against the shipper's reported value. This is the binding rule from the watchtower's record-correctness ruling (`gh pr view 24`, post-merge comment): the assurance-recording agent derives candidate identity independently from the artifact and records its verdict against that self-derived value. It MUST NOT copy identity from the ship agent's settlement record. In scripted mode, the verifier SHOULD put the independently derived portable JSON identity in the assurance entry's optional `derived_identity` key (`attempts.<work>[n].assurance.derived_identity`). The CLI checks every asserted field for uninterpreted JSON equality with the bound candidate's durable `subject_identity` before any Fact is recorded (`CONF-ASSURE-005`, `SCN-013`, issue #180). Detection is only as strong as the fields asserted, so include every identity field independently established by the audit. With `derived_identity`, the derive-it-yourself rule becomes kernel-checked on the verdict-binding path in scripted mode; without it, the rule remains convention-only and binding behaves exactly as before.
3. **A mismatch is the system working, not a bug to smooth over.** If your independently derived identity disagrees with what was recorded, preserve the `ERR-CONFLICT` — do not reconcile it away by substituting the shipper's value, and do not silently accept anyway. The rejected ingestion exits `2` without journaling a Fact and leaves the run pending at `ASSURING`; correct the entry and re-dispatch, or hand a genuinely stale bound candidate to the operator for `DEC-ABANDON-ATTEMPT`.
4. **Record `evidence_refs`** pointing at your audit output (the command you ran, the diff you fetched, the log you read) — not a narrative summary. Evidence is candidate-bound (`INV-007`) and non-transferable across candidates (`INV-008`): if the candidate changes, your prior evidence no longer applies and you must re-derive.
5. **Record the verify seat's identity when no adapter journals it.** Put the registered `executor-identity/v1` extension described in §2 alongside the verdict in the config assurance entry's `extensions` key, including `model`, `session_ref`, `seat_ref`, and `role` (for example, `"role": "verify"`). Choose a `seat_ref` stable for this verifier seat and distinct from the ship seat's value so the two identity payloads for this candidate are distinguishable from the journal alone; sharing an orchestrating `session_ref` does not establish or disprove seat separation. The payload transports unchanged into `FACT-ASSURE-SETTLED.extensions` per `CONF-EXT-003` and does not alter canonical assurance fields.
6. **Record the audit base when Git-backed.** A Git-backed verify seat SHOULD put an `assurance-context/v1` payload alongside the verdict in the config assurance entry's `extensions` key, with `base.identity` set to the resolved immutable sha the audit compared against (never a bare mutable ref). This is verifier-attested provenance, not a value the kernel re-derives or validates; see `EXT-ASSURANCE-CONTEXT-V1`.
7. **Journal substantive review findings with the verdict.** When your review produces substantive findings, put a `review-findings/v1` payload in the config assurance entry's `extensions` key. That entry accepts extensions and transports them losslessly into `FACT-ASSURE-SETTLED` per `CONF-EXT-003`; `EXT-REVIEW-FINDINGS-V1` is the schema home. A transcript path alone is not a durable record of what the review found.
8. As a standing discipline (SHOULD, not just for this one verdict): periodically reconcile the ledger against GitHub — every `ACCEPTED` Work's PR is actually merged, every recorded sha actually exists. This reconciliation-as-checker-duty is a supporting practice, not a one-time step.

## 5. Mechanics

**Multi-work briefs are not durable.** In a multi-work run, the journal durably records the topology and every settlement/verdict — but NOT what each work meant. Per-work briefs live only in the dispatching party's instructions (`CONTRACT-DURABILITY`, adapter-owned row): put anything a future reader must know into the run-level intent text or the PR/artifact the candidate points at; never assume the journal carries your assignment.


- **One writer per run journal at a time.** Concurrent writers to the same run's journal are not supported; if two agents believe they own the same run, that is a coordination bug upstream of the CLI, not something the CLI arbitrates.
- **Outcomes are recorded into the config/backing store, not the journal directly.** In M1a/M1a+, the ExecutionPort and AssurancePort read their next-attempt outcome from the dispatch config's `attempts` entries (see `PLAYBOOK-CLI-USAGE`'s Config section). For an assurance verdict, prefer `orc record <run-id> --work <work-id> --verdict accepted|rejected ...` (issue #192): it validates the current requested attempt and performs the same merge-only config update atomically, then prints the exact resume command without running it. Recording belongs to the verify seat; dispatch remains a separate party's act under the one-party-dispatch rule. Hand-editing the persisted config remains legal and follows the identical semantics and discipline documented here—the verb is validation sugar, not a new recording or journal contract. In either path, the kernel journals the resulting facts itself via the normal observation path on the next `orc dispatch` (`SCN-007`); you never hand-author journal records.
- **Exit codes and what they obligate you to do next** (full contract: `PLAYBOOK-CLI-USAGE`):
  - **`0`** — all Work `ACCEPTED`. Nothing further to record for this run.
  - **`1`** — some Work `BLOCKED` (or another non-accepted terminal state). Recording more outcomes will not help; escalate per the run's retry/`DEC-BLOCK` policy, you do not override it.
  - **`2`** — usage/config error (canonical error JSON on stderr). Fix your invocation or config entry; nothing was recorded that needs undoing.
  - **`3`** — run non-terminal, pending input. The output names which Work is waiting and for what (`execution-outcome` or `assurance-verdict`). If it's waiting on an execution outcome and you are the ship agent for that Work, record it (protocol §3). If it's waiting on an assurance verdict and you are the verification agent, record it (protocol §4). If it's waiting on the *other* seat's input, you are done for now — do not fill in the other seat's record yourself.
- **Re-running the same dispatch is safe (idempotent) and is the crash-recovery move.** Idempotency keys are derived from durable canonical state (`INV-020`), never randomness or wall-clock time, so replaying `orc dispatch` after a crash — yours or the process's — reproduces identical keys and never duplicates a fact or effect. If you are unsure whether your last recording landed, the answer is always: record it (or re-record it — idempotent) and re-dispatch. Never invent a workaround to "force" a stuck-looking run past exit `3`; pending is correct until the real outcome is known and recorded.

## 6. Multi-work etiquette (shared-config runs)

Watchtower ruling, normative for this playbook. Applies whenever multiple
Works in the **same** run share one config/journal (a multi-work plan, not
several unrelated single-work runs):

- **Merge only your own Work's `attempts` entries.** When you edit the
  config/backing store to record your settlement or verdict (per §5's
  Mechanics), your edit MUST be append/merge-only and scoped to the
  `attempts` entries for the Work you are recording for. Never touch a
  sibling Work's entries, and never touch the `plan` key. A shared-config
  multi-work run has one config file serving every Work in the plan; your
  write discipline must not assume you are its only writer.
- **Concurrent `orc dispatch` of the *same* run is forbidden.** Re-dispatch
  is one-party-at-a-time: the journal is single-writer (§5's "one writer
  per run journal at a time" already says this for the journal itself —
  this ruling makes the same constraint explicit for the *config* side of
  a shared multi-work run, where the temptation to have two agents record
  outcomes and dispatch in parallel is higher). If you are unsure whether
  another agent is mid-dispatch on the same run, do not race it — check
  `orc history <run>` first (see §3 item 1) and wait if a recent record you
  did not produce suggests another party is active.

## 7. Worked example — task-m1-003

This is the real record sequence from a completed run in this repository's own delivery history (`.orc/task-m1-003.jsonl`), tracking `TASK-M1-003`'s own CLI-UX PR through the ledger. It predates this playbook and was recorded through the same config/backing-store observation path an agent uses under this playbook (§5) — it is the exact loop a ship agent and a verification agent perform under push mode, summarized here rather than dumped record-for-record:

1. **Intent submitted, Work created and claimed, dispatched.** `FACT-INTENT-SUBMITTED` → `FX-CREATE-WORK`/`FACT-WORK-CREATED` → `FX-CLAIM-WORK`/`FACT-WORK-CLAIMED` → `FACT-WORK-READY` → `DEC-DISPATCH` (kernel decision, not agent-recorded) → `FX-START-EXECUTION`/`FACT-EXEC-STARTED` for attempt 1.
2. **Ship agent does the work and records settlement + candidate.** The next `orc dispatch` invocation, before the outcome was recorded, would have stopped at exit `3` (pending, awaiting `execution-outcome`) per `SCN-007` — the same wait an agent sees today. Once the PR existed, the ship agent recorded the execution settlement (`outcome: completed`) and a candidate whose content is externally resolvable identity, not prose: `{"pr": 32, "head_sha": "c9b1390d..."}`. Re-dispatching journaled `FACT-EXEC-SETTLED(completed)` and `FACT-CANDIDATE-OBSERVED` (fingerprint `fp-204c92f5...`), then `DEC-REQUEST-ASSURANCE` (kernel decision) moved the Work to `ASSURING`.
3. **Pending again, this time for assurance.** With no verdict recorded yet, dispatch would stop at exit `3` (pending, awaiting `assurance-verdict`) — `FX-START-ASSURANCE`/`FACT-ASSURE-STARTED` journaled, nothing fabricated for the missing verdict.
4. **Verification agent independently derives the candidate and records its verdict.** The verification agent — a *different* agent from the one that recorded step 2's settlement, per Role separation — did not copy `fp-204c92f5...`/`pr 32`/the head sha from the ship agent's record. It independently fetched PR #32 and computed the head sha itself, then recorded its verdict against that self-derived identity. Because the independently derived fingerprint matched, assurance settled `accepted`: `FACT-ASSURE-SETTLED(accepted)`. (Had it mismatched, the correct move per §4 above is to report `ERR-CONFLICT`, not reconcile it away.)
5. **Acceptance and completion — kernel decisions, not agent-recorded.** `DEC-ACCEPT` → `FX-COMPLETE-WORK`/`FACT-WORK-COMPLETED`. Final re-dispatch would exit `0`.

Notice what the two agent seats did and did not do: the ship agent recorded a settlement and a resolvable candidate, never a verdict on its own work; the verification agent recorded a verdict derived from its own independent fetch, never copied from the settlement record; neither agent recorded any `DEC-*`. That is the whole loop.

## 8. Narrative content is reference-first, not a separate recording channel

Everything in this playbook is canonical observation: settlements,
candidates, verdicts. Your own turn-by-turn narration — what you believe
you did, what's still pending, what you think the outcome is — is
deliberately **not** given its own recording channel. The `crew-report/v1`
sidecar log (`orc crew-report append`/`orc crew-report list`) that used to
live here is **removed** (`EXT-CREW-REPORT-V1`, superseded; operator
ruling, issue #100 part 2, "reference-first narrative doctrine," amending
issue #65). The doctrine: narrative/report *content* stays provider-owned
— your own session/transcript, wherever your tooling already keeps it —
and the ledger journals a durable, resolvable *reference* to it instead of
a copy. Use the existing reference-carrying surfaces:

- **`execution-session/v1`** (`EXT-EXECUTION-SESSION-V1`), when your
  provider is adapter-managed — session/resume/transcript references are
  already journaled onto `FACT-EXEC-SETTLED`'s `extensions` automatically.
  As of 0.5.0 no shipped `ExecutionPort` adapter does this for a real
  provider (`ADR-0005` removed the `acp` adapter, the one that did); an
  external executor instead pushes this same extension shape itself via a
  config-entry `extensions` payload (next bullet).
- **`evidence_refs`** on the assurance verdict (`FACT-ASSURE-SETTLED`),
  for a verification agent's audit trail (§4 item 4 above).
- **A config-entry `extensions` payload** on the execution attempt, for
  anything else you need to record about your own turn/identity that has
  no better home — §2's "Executor identity when no adapter journals the
  seat" above shows the mechanics.
- **`orc refs <run>`** surfaces every resolvable reference a run carries,
  across all of the above, each with a runnable resolve command.

There is no longer a place to journal free-form claimed-verdict narration
per turn; a claim about your own progress belongs in your own session/
transcript (referenced, not duplicated) or, if it must be canonical, in
the settlement/candidate/verdict recording this playbook already governs.

## 9. Fresh-session protocol — resuming from the record alone

A fresh session has no memory of any prior session's work. It never resumes from a doc, a chat summary, or another session's context — it resumes entirely from the durable ledger, in this order: bare `orc` (the live portfolio of every run, per-work state, attempts, pending flags) → `orc status <run>` for each non-terminal run, reading its `next:` affordance block → `orc report <run>`/`orc history <run>` for depth when the affordance alone isn't enough → `gh pr list`/`gh issue list` to cross-check the ledger's view against GitHub's own state. If the ledger and any other source (a doc, a memory, an operator's recollection) disagree, the ledger wins.

This loop — plus the seat discipline and recording mechanics this playbook governs above — is packaged as a project skill for onboarding: `.claude/skills/orc-ledger` (source `.agents/skills/orc-ledger/SKILL.md`). A fresh session working this repo's delivery ledger should read that skill first; this section only summarizes what it teaches in full, including the resume-don't-duplicate rule (never start parallel effort for work a run already owns) and the config-persistence-aware mechanics for run-id-only re-dispatch (`PLAYBOOK-CLI-USAGE`'s "Config persistence" bullet, issue #55 H2).

## Related

- `docs/playbooks/cli-usage.md` (`PLAYBOOK-CLI-USAGE`) — command surface, config shape, full exit-code contract
- `docs/delivery/watchtower-operations.md` (`PLAYBOOK-WATCHTOWER`) — ship/verification-scout roles in the surrounding human-driven process
- `docs/scenarios/SCN-007-pending-settlement.md` — the pending/idempotent-resume flow this playbook's exit-`3` handling follows
- `docs/extensions/execution-session/README.md` (`EXT-EXECUTION-SESSION-V1`) — durable provider session/resume/transcript references
- `docs/extensions/crew-report/README.md` (`EXT-CREW-REPORT-V1`, superseded) — the removed narrative-report sidecar; historical reference only
- `.claude/skills/orc-ledger` (source `.agents/skills/orc-ledger/SKILL.md`) — the fresh-session onboarding artifact, section 9 above
- `INV-003`, `INV-006`, `INV-007`, `INV-008`, `INV-011`, `INV-020`
- `PORT-WORK-004`, `ERR-CONFLICT`, `CONF-ASSURE-005`, `SCN-013` (issue #180)
