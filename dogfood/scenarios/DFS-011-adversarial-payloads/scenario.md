---
id: DFS-011
type: scenario
status: current
authority: informative
description: Adversarial payloads — NaN candidate rejected with canonical ERR-VALIDATION at config load, unicode/emoji + 100k-char intent and deep nesting all run cleanly.
---

# DFS-011: adversarial payloads — NaN, unicode/emoji + 100k intent, deep nesting

## Concern tags

`adversarial`

## Intent

Push degenerate/hostile-but-plausible payloads through the CLI: a
candidate whose subject identity contains a non-finite float, a
huge-and-unicode intent string, and a pathologically deeply nested
candidate structure. `ARCH-REPOSITORY-STRUCTURE`/`core/portable.py`
already forbid non-finite floats in canonical shapes (they have no JSON
literal per RFC 8259); the question this scenario asks is *how* that
prohibition surfaces at the CLI boundary — as a canonical `ERR-VALIDATION`
(the hard bar), or as something worse.

## Setup

None beyond a scratch journal directory. Three configs in this directory:
`nan.json` (single work, one attempt, candidate `{"score": NaN}` —
`NaN` is accepted by Python's non-standard `json.loads` extension, so the
*parse* succeeds and the load-time portability check is what must catch
it), `emoji.json` (plain candidate, used here
paired with a hostile intent string rather than a hostile config),
`nested.json` (a candidate containing ~200 levels of nested objects,
`{"nest": {"nest": {...{"leaf": "bottom"}...}}}`).

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-011"

# 1: NaN candidate
PYTHONPATH=src python3 -m orc_werk.cli dispatch "adversarial: nan candidate" \
  --config dogfood/scenarios/DFS-011-adversarial-payloads/nan.json \
  --journal "$JOURNAL_DIR/nan"

# 2: unicode/emoji intent, generated at run time (not stored as a fixture)
EMOJI_INTENT=$(python3 -c "print('emoji intent 🚀🔥✨ ' * 20)")
PYTHONPATH=src python3 -m orc_werk.cli dispatch "$EMOJI_INTENT" \
  --config dogfood/scenarios/DFS-011-adversarial-payloads/emoji.json \
  --journal "$JOURNAL_DIR/emoji"

# 3: 100,000-character intent, generated at run time
LONG_INTENT=$(python3 -c "print('a' * 100000)")
PYTHONPATH=src python3 -m orc_werk.cli dispatch "$LONG_INTENT" \
  --config dogfood/scenarios/DFS-011-adversarial-payloads/emoji.json \
  --journal "$JOURNAL_DIR/longintent"

# 4: deeply nested candidate
PYTHONPATH=src python3 -m orc_werk.cli dispatch "deep nesting" \
  --config dogfood/scenarios/DFS-011-adversarial-payloads/nested.json \
  --journal "$JOURNAL_DIR/nested"
```

## Expected observable outcomes

**1 (NaN candidate) — correct, confirmed:** exit `2`, stderr
`{"error": "ERR-VALIDATION", "message": "config value at
<config>.attempts.work-1[0].candidate.score is not
portable/JSON-compatible: nan", "details": {"path":
"<config>.attempts.work-1[0].candidate.score"}}` — the exact offending
path is named. No journal directory/file is created (rejected at config
load, before the journal is opened). No traceback. This case regressed in
round 1 (a raw uncaught `TypeError` traceback, round-1 BUG-1) and was
fixed by the round-1 fix PR, which added a recursive load-time
portability check (`_require_portable` in `src/orc_werk/cli/config.py`)
plus a last-resort canonical-error catch-all in `main()`; both are
guarded by `tests/scenarios/test_cli_dogfood_fixes.py`.

**2 (unicode/emoji intent) — correct, confirmed:** exit `0`, `work
work-1: state=ACCEPTED attempts=1 candidate_fingerprint=<fp>`. The intent
text itself (emoji, repeated) is never candidate-identity-bearing (only
`FACT-INTENT-SUBMITTED.data.text` carries it), and multi-byte UTF-8 in an
argv string round-trips fine through `argparse`/journaling.

**3 (100k-character intent) — correct, confirmed:** exit `0`, same
outcome shape as case 2. `_derive_run_id` hashes the intent text
(`sha256(...)[:12]`), so run id length is independent of intent length —
confirms nothing chokes on a large `FACT-INTENT-SUBMITTED.data.text`
value.

**4 (deep nesting) — correct, confirmed:** exit `0`, `work work-1:
state=ACCEPTED attempts=1 candidate_fingerprint=<fp>`. ~200 levels of
nested single-key objects canonicalize and fingerprint without recursion
errors at Python's default recursion limit.

## Judgment notes

Case 1 is a regressed-then-fixed hard-bar case (round-1 BUG-1): a
traceback here is exactly the failure mode `DELIVERY-STANCE` singles out
as never acceptable, pre- or post-golden. If any checker run ever sees a
Python traceback (or exit `1`) from this case again, escalate as BUG
immediately — the deterministic guard lives in
`tests/scenarios/test_cli_dogfood_fixes.py`, so a reappearance here means
that suite has a hole. Cases 2-4 are useful mainly as negative controls:
they confirm the adversarial *shape* of an input (unicode, size, nesting)
is not itself the problem — the NaN case fails because of the value's
non-portability, not its unusualness in general.

## Verification

All four cases executed against `master` (worktree `feat/dogfood-corpus`)
on 2026-08-28. Case 1 was executed twice: once pre-round-1-fix (raw
`TypeError` traceback, exit `1` — the run that surfaced BUG-1) and again
after merging the round-1 fix PR (canonical `ERR-VALIDATION`, exit `2`,
offending path named — transcribed verbatim above). Cases 2-4's exit
codes and `status` lines are transcribed verbatim (case 3 additionally
confirmed the generated intent was exactly 100,000 characters via shell
length check before dispatch); case 4 was re-run post-merge to confirm
the new load-time recursive portability check itself handles ~200 levels
of nesting without recursion errors — it does.
