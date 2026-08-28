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
- `history` shows 27 records. Attempt 1's `FX-IDENTIFY-CANDIDATE` (seq 11)
  carries the full structured candidate (`files`, `summary`, `diff_stat`)
  in `dispatch_result.candidate.subject_identity`. Attempt 1's
  `FACT-ASSURE-SETTLED` (seq 16) has `verdict: rejected`; the raw journal
  record at that seq carries `extensions: {"findings": ["missing
  frontmatter..."]}` alongside `data`. Attempt 2's `FACT-ASSURE-SETTLED`
  (seq 26) has `verdict: accepted`, `extensions: {}`.

## Judgment notes

**This is the scenario's real point, not a mechanical assertion.**
Confirmed by direct inspection: `cmd_history` (`src/orc_werk/cli/main.py`)
prints `record['data']` only — it never reads `record['extensions']`. So
seq 16's own printed `history` line shows `verdict":"rejected"` with
**no** findings anywhere on that line; a human scanning line-by-line sees
only that the candidate was rejected, not why. The findings *are*
recoverable from `history` output, but only indirectly: `DEC-RETRY` at seq
17 embeds a full copy of the cited `FACT-ASSURE-SETTLED` record (including
its `extensions`) inside its `basis` array, so `findings` does appear
buried inside that decision's JSON blob one line later — not on the
originating fact's own line where a human would first look.

Judge this as: **FRICTION, not BUG** — the information is not lost (it
would survive a full-history audit), but it is not legible at the natural
reading location. This is exactly the "history-extensions visibility"
gap; round 1's proposed fix is for `cmd_history` to print each record's
own `extensions` field alongside `data` directly, which would put the
findings on seq 16's line where they belong instead of requiring a reader
to notice they are re-embedded one line later. If a checker run finds
`extensions` printed directly on the record's own line, treat the
friction as resolved and update this note.

## Verification

Executed against `master` (worktree `feat/dogfood-corpus`) on 2026-08-28:
exit `0`, `work write-docs-page: state=ACCEPTED attempts=2
candidate_fingerprint=fp-b0f8822ad13abb3671ddfa0a`. The
`extensions`-visibility gap described above was confirmed directly: seq
16's `history` line omits `findings`; seq 17's embedded basis carries it.
