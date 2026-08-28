---
id: TASK-M1-008
type: task-card
status: current
authority: normative
description: Add `orc report` — a read-only, stdlib-only renderer producing one self-contained HTML file per DeliveryRun for human review, plus a local run index.
implements:
  - PORT-JOURNAL
verifies: []
---

# TASK-M1-008 — Human run report (`orc report`)

## Outcome

Add a read-only presentation surface: `orc report <run>` renders one DeliveryRun's
journal (and its `crew-report/v1` log when present) into a **single self-contained
HTML file** a human can open, share, and archive — the async-review surface for
runs the operator did not watch. An `orc report --index` variant renders a small
local index page over the journal directory's runs.

This is CLI-owned composition, not product semantics: the renderer consumes the
portable journal envelope (`PORT-JOURNAL-ENVELOPE`) and the crew-report log as
plain data. It defines no new canonical shapes and MUST NOT alter any existing
command's behavior.

## Content requirements

Per run: header (verbatim intent text, run id, per-work state/attempts, exit
disposition); a per-work timeline of facts, decisions, and effects in `seq`
order, with each decision's `basis` visibly linked to the cited fact(s); candidate
fingerprints with their portable `subject_identity`; assurance verdicts with
`evidence_refs`; blocked works with `blocked_reason` and root cause (from effect
records' `dispatch_result.error`, mirroring `orc status`); pending works with an
explicit "awaiting …" callout; and, when a `<run_id>.reports.jsonl` exists, crew
reports interleaved by `execution_id`.

## Presentation rules (normative for this surface)

- **Claims are visually quarantined from canonical state.** A crew report's
  `claimed_verdict` MUST render in a categorically different style (muted/
  outlined, labeled "claim") from canonical facts and verdicts — the
  `EXT-CREW-REPORT-V1` claim-vs-fact distinction applied visually. Status colors
  are reserved for canonical delivery state and always paired with a text label.
- **No invented semantics.** The renderer displays what the journal records; it
  MUST NOT compute derived judgments (scores, health, ratings) the kernel did
  not make.
- **Self-contained output**: inline CSS only, no external requests, light and
  dark mode both deliberately styled, wide content scrolling in its own
  container. The HTML file is as portable as the journal it renders.
- **Static record, not a feed.** No server, no watching, no auto-refresh — the
  live-cockpit surface remains out of scope (`PRODUCT-ADOPTION` §4 misfits).

## Hard constraints

- Stdlib-only (string templating; no template engine, no third-party deps).
- Strictly read-only: no directory or file creation other than the output HTML
  at the caller-specified (or clearly announced default) path; missing run →
  canonical `ERR-NOT-FOUND`; corrupt journal handling inherited from the
  reading adapters (never weakened in presentation).
- Canonical errors at the CLI boundary; established exit codes.
- All content HTML-escaped (intent text and report fields are untrusted
  free text).

## Acceptance

- Rendering `.orc/task-m1-007.jsonl` (the reject→retry→accept run) produces an
  HTML file from which a reader with no prior context can follow the full story:
  two attempts, two distinct candidate fingerprints, the rejected verdict and
  the retry decision citing it, the accepted verdict on the second candidate.
- A pending run renders with its awaiting-state callout; a blocked run renders
  its root cause; the index page lists local runs with state at a glance.
- Regression tests: report on missing run → `ERR-NOT-FOUND`, no side effects;
  output contains expected fingerprints/decisions/escaped content; claims
  styled distinctly from canonical verdicts (assert on distinguishing markup);
  `--index` read-only.
- `bash scripts/check.sh` green.

## Must not change

`src/orc_werk/core`, `src/orc_werk/ports`, `src/orc_werk/app`, existing adapter
behavior, existing CLI commands' semantics, and all normative contracts.
