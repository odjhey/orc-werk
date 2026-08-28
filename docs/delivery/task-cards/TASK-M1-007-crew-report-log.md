---
id: TASK-M1-007
type: task-card
status: current
authority: normative
description: Implement the small file-based reference crew-report/v1 log — append-only NDJSON per DeliveryRun beside the journal, stdlib-only, reusing the jsonl journal's mechanics.
implements:
  - EXT-CREW-REPORT-V1
verifies:
  - CONF-EXT-001
  - CONF-EXT-003
  - CONF-EXT-006
---

# TASK-M1-007 — Crew-report log (`crew-report/v1` reference implementation)

## Outcome

Implement a small, file-based reference implementation of the `crew-report/v1` durable log (`EXT-CREW-REPORT-V1`'s "Durable ownership" section): an append-only NDJSON file per `DeliveryRun`, distinct from — and never merged into — the `JournalPort`'s own journal file, living under the CLI's journal directory area with a distinct file suffix (for example `<run_id>.reports.jsonl` beside the existing `<run_id>.jsonl`). Stdlib-only (`json`, `pathlib`, `os`), matching `src/orc_werk/core`'s and the existing `orc_werk.adapters.jsonl` package's zero-integration-dependency stance (`CLAUDE.md` rule 8).

Reuse the jsonl `JournalPort` adapter's (`src/orc_werk/adapters/jsonl/journal.py`) mechanics rather than reinventing them:

- the same flush-without-fsync durability stance for the same reasons (single-machine, single-writer-per-run context; a later milestone that needs a stronger guarantee revisits this as an advertised capability, not a silent change);
- the same torn-tail recovery rule from `PORT-JOURNAL`'s durable-journal recovery clause, applied to this log by reference: on reopen, tolerate a single unparseable FINAL record as a torn write and continue from the last good record, while rejecting any earlier malformed record with `ERR-VALIDATION`; a file with no valid records at all is not a log and reading it MUST reject with `ERR-VALIDATION` rather than presenting empty history.

Each appended line carries the `crew-report/v1` payload (`EXT-CREW-REPORT-V1-SCHEMA`) plus at minimum `delivery_run_id` and `execution_id`, per `EXT-CREW-REPORT-V1`'s per-run-file/per-record-`execution_id` disposition. Append order within one run's file is the log's own ordering key — distinct from, and not required to align with, the `JournalPort` envelope's `seq`.

## CLI surface

A minimal way to:

- **append** a report for a run/execution (write one NDJSON line);
- **list** reports for a run (read the log back in append order, applying the torn-tail rule on reopen).

The exact verb/flag naming is left to implementation, following the existing `orc dispatch`/`status`/`history` conventions (`docs/playbooks/cli-usage.md`) rather than inventing a disjoint command family.

## Conformance addition

A slim addition to the extension conformance suite, exercising this reference log:

- **append-only** — no operation the log exposes can mutate or remove an already-appended record;
- **ordered** — reports read back in the same order they were appended;
- **lossless round-trip** — a `crew-report/v1` payload, including unknown/reserved-adjacent keys tolerated per `EXT-005`, survives an append/reopen/read cycle unchanged (`CONF-EXT-001`, `CONF-EXT-003`);
- **`claimed_verdict` never affects projection** — a core reducer test (`CONF-EXT-006`) proving that appending a report with any `claimed_verdict` value, including `"done"`, produces no change in `PORT-JOURNAL-005`'s canonical projection when the underlying canonical facts are held constant. This is the log-level instance of the same core-ignorance guarantee `EXT-CREW-REPORT-V1-SCHEMA` requires of the payload generally.

## Depends on

`TASK-M1-006` context — this log exists to durably record what ship/verify agents narrate about their own progress, so it is most useful once agents are producing reports through the M1a+ push-mode playbook. It is implementable before `TASK-M1-006` lands, since the log's shape depends only on `EXT-CREW-REPORT-V1` (registered by this same docs change), not on the playbook's content.

## Sequencing

Sequenced at the **start of stage M1a+**, before phase M1b: the report log is small, self-contained infrastructure that ship/verify agents can start using as soon as it exists, and `TASK-M1-005` (the M1b ACP adapter) benefits from having a settled report-log shape to journal against rather than inventing one under adapter-specific pressure.

## Must not change

Core/envelope shape: this log is an adapter-owned structure beside the journal, not a journal extension. It MUST NOT change `PORT-JOURNAL-ENVELOPE`, `PORT-EXEC-002`'s execution observation shape, or any core contract. Where a report additionally rides an execution observation's or journal record's `extensions` slot as a snapshot (`EXT-CREW-REPORT-V1`'s "Durable ownership" section), that snapshot uses the existing `extensions` transport unchanged.

## Out of scope

Ack/open-item state (explicitly out of `crew-report/v1`, per `EXT-CREW-REPORT-V1`'s "Ack / open-item state" section); a real `PORT-EXECUTION` adapter producing reports automatically (that is `TASK-M1-005`'s concern, and this log's shape is adapter-agnostic); any attention/notification machinery (`INV-017`, reserved).

## Acceptance

- an append-only NDJSON log exists per `DeliveryRun` under the CLI's journal directory area, at a distinct path/suffix from the `JournalPort`'s own file, implemented stdlib-only;
- the log's torn-tail recovery rule matches `PORT-JOURNAL`'s durable-journal recovery clause by reference (same tolerance, same failure mode for real corruption);
- a minimal CLI surface can append a report and list reports for a run;
- the conformance addition above (append-only, ordered, lossless round-trip, `claimed_verdict`-never-affects-projection) passes;
- `python3 scripts/docs_check.py` and `bash scripts/check.sh` pass.
