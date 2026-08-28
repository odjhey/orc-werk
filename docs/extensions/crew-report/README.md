---
id: EXT-CREW-REPORT-V1
type: extension
status: current
authority: normative
version: 1
description: Append-only, claim-only handoff report extension for execution turns, with an adapter-owned durable log.
---

# `crew-report/v1`

`crew-report/v1` is an optional extension carrying a structured, per-turn handoff report from an execution's producer — a crew member, subagent, or any `PORT-EXECUTION` participant that narrates its own progress mid-attempt. It is registered per `TASK-M1-007`, closing the `crew-report/v1` open gate recorded in `CONTRACT-DURABILITY`'s ownership matrix and Rozoro retirement ledger, per the watchtower dispositions on issue #12: adapter-owned append-only log, and the report's verdict field renamed to `claimed_verdict`.

It is intentionally not part of generic `Execution` semantics. `PORT-EXEC-002`'s canonical `state`/`outcome` fields are unchanged by this extension; a crew report only gives a provider's own narration of what it did, what it thinks is pending, and what it believes the outcome to be, a durable and portable place to live — never a substitute for canonical settlement or assurance.

## Purpose

Preserve the useful semantic portion of a provider's append-only handoff history — the turn-by-turn story a crew member tells about its own work — without ever letting that story be mistaken for, or silently promoted into, canonical orchestration truth. A `crew-report/v1` report answers: **what does this execution's producer currently believe about its own progress?** It never answers, and MUST NOT be used to answer, whether Work is accepted (`INV-003`) or what an execution's canonical outcome was (`PORT-EXEC-002`).

## Scope rules

A `crew-report/v1` report MUST remain an in-flight progress claim made by the seat performing the work: its turn, its `claimed_verdict`, and the seat's self-identification follow `PLAYBOOK-AGENT-CLI`. It MUST NOT be used as a general annotation channel. Review findings belong in `FACT-ASSURE-SETTLED` extensions under `EXT-REVIEW-FINDINGS-V1`; assurance evidence belongs in the settled fact's `evidence_refs`; briefs and status narrative belong in the Beads mirror when configured (`ADAPTER-BEADS-MAPPING`). Landing or merge linkage MUST NOT be ledger-recorded until the open shape question on issue #65 is resolved.

- **`claimed_verdict`, not `verdict`.** The field is named `claimed_verdict` precisely so no consumer confuses a crew's self-report with a canonical assurance verdict. This is a deliberate `EXT-003`/`INV-003` immunization: `EXT-003` forbids an extension from redefining or overriding canonical fields such as assurance verdict, and `INV-003` requires that "done" remain a claim until independently accepted. Naming the field `verdict` would invite exactly the confusion both rules exist to prevent; `claimed_verdict` cannot be mistaken for `PORT-ASSURANCE`'s canonical verdict vocabulary even by a careless reader. See [Schema](schema.md).
- **A claim, never canonical state.** A `claimed_verdict` of any value — including `"done"` — is a claim only. It MUST NOT affect canonical state, decisions, or transitions (`CONF-EXT-006` core-ignorance). See [Semantics](semantics.md).
- **Ref-only artifacts and inputs.** `artifact_refs` and `inputs_needed` are opaque reference strings only; no inlined content. This mirrors `execution-session/v1`'s `transcript_ref` rule and `PORT-JOURNAL`'s "not an artifact store" boundary.
- **Portable JSON.** The payload MUST satisfy `EXT-006` and use only portable JSON-compatible values.
- **Unknown-key tolerance, producer-side strictness.** Per `EXT-005`, a consumer that does not understand this extension (or a future field within it) still processes the enclosing observation unchanged. Producer-side strictness applies only to the fields this schema reserves (`turn`, `claimed_verdict`, `reason`, `did`, `pending`, `inputs_needed`, `artifact_refs`): a producer MUST NOT repurpose a reserved key for a different meaning, but MAY include additional, non-reserved keys that a lossless-round-trip consumer preserves per `EXT-005`/`CONF-EXT-003`.

## Durable ownership (the gate closure)

The durable owner of the append-only crew-report history is an **adapter-owned append-only log, beside — not inside — the journal**: a plain NDJSON file per `DeliveryRun`, distinct from (and never merged into) the `JournalPort`'s own journal file. This is the watchtower-recorded disposition from issue #12 and `CONTRACT-DURABILITY`'s ownership matrix, now closed.

Exact filename layout (amended by issue #55 H1, per-run directory layout): the reference implementation writes every run created under this code to `<delivery_run_id>/reports.jsonl`, inside that run's own per-run directory, beside that same directory's `<delivery_run_id>/journal.jsonl`. A run that already had a legacy `<delivery_run_id>+reports.jsonl` flat sidecar before issue #55 keeps using it for its whole lifetime instead (read/write-fallback, never a mid-run switch); `orc_werk.adapters.jsonl.layout` resolves which layout applies, independently per artifact (a run's crew-report log and its journal may legitimately sit on different layouts, since `orc crew-report append` never requires a journal to exist at all). The legacy `+` sidecar separator remains on the books for that flat layout — `+` is outside the safe run-id charset (`[A-Za-z0-9_.-]`, `orc_werk.adapters.jsonl.tailsafe.SAFE_DELIVERY_RUN_ID`), so no legal run id can ever produce a filename that classifies as a sidecar; a dot-separated suffix (an earlier example used `<run_id>.reports.jsonl`) was rejected by the attempt-2 watchtower ruling on PR #46 because a legal dot-namespaced run id such as `m1.reports` yields exactly that shape and collides. Inside a new-layout run directory this separator rule is moot: every artifact is disambiguated by directory scope plus a fixed filename, not a run-id-derived suffix.

- **One file per `DeliveryRun`, `execution_id` per record.** The log is scoped per-run (mirroring the jsonl `JournalPort` adapter's own per-run file layout, `PORT-JOURNAL`), with each record carrying its own `execution_id`. Per-run scoping is chosen over per-execution files for the same reasons the journal adapter scopes per-run rather than globally: reading the full report history for one run never has to merge many small files, and a crash mid-write to one run's log cannot corrupt an unrelated run's log. `execution_id` per record — rather than one log per execution — keeps a Work lineage's reports (which may span several attempts/executions per `INV-018`) in one append-ordered stream per run, so "the crew's story for this run" is one file to read, filterable by `execution_id` when a caller wants one attempt's turns only.
- **Append-only, torn-tail tolerant.** The log is append-only for the life of the run. On reopen, a durable adapter for this log MUST apply the same torn-tail tolerance `PORT-JOURNAL`'s durable-journal recovery clause defines for the journal itself (tolerate a single unparseable FINAL record as a torn write, reject any earlier malformed record with `ERR-VALIDATION`) — see that clause by reference rather than restating it here; the crew-report log adopts it wholesale.
- **Journal `extensions` carries snapshots only, never ownership.** An individual report MAY additionally ride an execution observation's or journal record's `extensions` slot as a point-in-time snapshot (per `CONTRACT-EXTENSIONS`), but the adapter-owned log remains the durable owner of the full history. This is because reports are produced *between* canonical transitions — a crew narrates progress mid-attempt, before the next `FACT-EXEC-*` fact is journaled — so there is frequently no canonical journal write for an individual report to ride at the moment it is produced; the log is the only place with a fact to append to at that moment.

## Ack / open-item state (explicitly out of scope)

Report acknowledgement and open-item/attention handling are explicitly **out of** `crew-report/v1`. Acknowledging a report remains distinct from accepting the Work it describes, and both remain distinct from attention handling (`INV-017`, reserved and conditional on attention being enabled). This extension only gives the append-only report content a durable home; it does not define an ack cursor, an open-item lifecycle, or any attention machinery. A future companion contract owns ack/open-item state, per `CONTRACT-DURABILITY`'s ownership matrix. Building that machinery now would be scope creep beyond what issue #12's `crew-report/v1` shape requires and beyond `INV-017`'s M1 conditionality.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `CONTRACT-DURABILITY`
- `PORT-EXECUTION`
- `PORT-JOURNAL`
- `INV-003`
- `INV-014`
- `INV-017`
- `TASK-M1-007`
