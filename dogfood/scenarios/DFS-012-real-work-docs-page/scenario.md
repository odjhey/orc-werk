---
id: DFS-012
type: scenario
status: current
authority: informative
description: A realistic "write a docs page" delivery with a structured candidate and review-style findings carried in an assurance extension — can a human reconstruct the story from status+history alone?
---

# DFS-012: real-work simulation — write docs page

## Concern tags

`real-work`, `cli-output`

## Intent

Every other seeded scenario uses a minimal `{"label": "..."}` candidate.
This one simulates what a real delivery looks like: a candidate shaped
like an actual code-review artifact (`files`, `summary`, `diff_stat`), a
first attempt rejected with structured findings carried in the assurance
extension (`review-findings`-style, though simplified to a plain
`findings` list rather than the full `EXT-REVIEW-FINDINGS-V1` dimension
schema), and a second attempt that addresses the findings and gets
accepted. The judgment question this scenario exists to ask on every
checker run: **reading only `status` and `history` output, with no other
context, could a human reconstruct what happened and why?**

## Setup

None beyond a scratch journal directory. Uses this directory's
`config.json`: one work (`write-docs-page`), two attempts. Attempt 1's
candidate claims to add `docs/scenarios/SCN-007-cli-dogfood.md` but is
rejected with `assurance.extensions.findings: ["missing frontmatter
id/type/status/authority header"]`. Attempt 2's candidate is the corrected
version, accepted.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-012"

PYTHONPATH=src python3 -m orc_werk.cli dispatch "write a docs page for the CLI dogfood scenario" \
  --config dogfood/scenarios/DFS-012-real-work-docs-page/config.json \
  --run-id s10-docs-page \
  --journal "$JOURNAL_DIR"

PYTHONPATH=src python3 -m orc_werk.cli status "$JOURNAL_DIR/s10-docs-page.jsonl"
PYTHONPATH=src python3 -m orc_werk.cli history "$JOURNAL_DIR/s10-docs-page.jsonl"
```

## Expected observable outcomes

- `dispatch` exit `0`. `status`: `work write-docs-page: state=ACCEPTED
  attempts=2 candidate_fingerprint=<fp of attempt 2's candidate>`.
- `history` shows 29 records. Attempt 1's `FX-IDENTIFY-CANDIDATE` (seq 11)
  carries the full structured candidate (`files`, `summary`, `diff_stat`)
  in `dispatch_result.candidate.subject_identity`. Attempt 1's
  `FACT-ASSURE-SETTLED` (seq 16) has `verdict: rejected` **and its own
  printed line ends with the record-level extensions rendered inline**:
  `extensions={"findings":["missing frontmatter id/type/status/authority
  header"]}` — `cmd_history` renders each record's non-empty `extensions`
  field on the record's own line (fixed by the round-1 fix PR; previously
  extensions were journaled but invisible in `history` output, guarded by
  `tests/scenarios/test_cli_dogfood_fixes.py`). Attempt 2's
  `FACT-ASSURE-SETTLED` (seq 26) has `verdict: accepted` and no
  `extensions=` suffix (empty extensions are not rendered).
- Exactly one `extensions=` suffix appears in the whole history output
  for this run (seq 16's rejection findings).

## Judgment notes

**This is the scenario's real point, not a mechanical assertion:** with
the findings now on seq 16's own line, a human reading only
`status` + `history` can reconstruct the full story — candidate 1's
content and diff stat (seq 11), why it was rejected (seq 16's
`extensions=` findings), the retry decision citing that rejection (seq
17), candidate 2's corrected content (seq 21), and its acceptance (seq
26-27). Judge each checker run against that bar: if reconstructing "what
happened and why" ever again requires reading the raw `.jsonl` or fishing
findings out of a decision's embedded `basis` blob instead of the
originating record's line, the extensions-visibility friction has
regressed — escalate as BUG (the deterministic guard is in
`tests/scenarios/test_cli_dogfood_fixes.py`).

## Verification

Executed against post-round-1-fix `master` (merged into this branch) on
2026-08-28: exit `0`, `work write-docs-page: state=ACCEPTED attempts=2
candidate_fingerprint=fp-b0f8822ad13abb3671ddfa0a`; seq 16's `history`
line ends `extensions={"findings":["missing frontmatter id/type/status/
authority header"]}` and it is the only `extensions=` occurrence in the
output — both transcribed verbatim from the live run. (The pre-fix run of
this same scenario is what surfaced the visibility gap as round-1
FRICTION-1.)

Re-executed against `master` for the M1 close-out sweep (2026-08-28,
`m1-closeout` checker run): fingerprint and seq-16 `extensions=` shape
match exactly. Arithmetic correction from that sweep: the actual/correct
record count for this run is **29**, not 27 as previously stated here —
the cited seq numbers throughout this doc (16, 21, 26-27 for acceptance)
were already internally consistent with 29 records; only the stated total
was off.
