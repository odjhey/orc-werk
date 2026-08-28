---
id: DFS-011
type: scenario
status: current
authority: informative
description: Adversarial payloads — NaN candidate leaks a raw Python traceback (confirmed, no issue number yet), unicode/emoji + 100k-char intent and deep nesting both run cleanly.
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
`NaN` is accepted by Python's non-standard `json.loads` extension, so this
loads fine and only fails later), `emoji.json` (plain candidate, used here
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

**1 (NaN candidate) — expected (post-fix): canonical `ERR-VALIDATION`,
exit `2`, no traceback.** **Actual on current `master` (confirmed BUG, not
yet filed with a tracking number): a raw, uncaught Python `TypeError`
traceback is printed to stderr, exit `1`.** The chain: `cmd_dispatch` →
`build_scripted_adapters` → `fingerprint_of` →
`orc_werk.core.portable.to_portable` raises plain `TypeError("non-finite
float is not portable/JSON-compatible: nan")` — `to_portable` never wraps
this in `orc_werk.core.errors.validation_error`, so it is not a
`CoreError`, and `main()`'s `except CoreError`/`except FileNotFoundError`
clauses do not catch it. This is a direct violation of
`DELIVERY-STANCE`'s hard bar "canonical errors at user-facing
boundaries... never implementation tracebacks" — report as BUG, not
FRICTION, and flag for a tracking issue if the checker run confirms it
again (it is not yet one of #16-18).

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

Case 1 is the headline finding here: it is a genuine, currently
reproducible hard-bar violation, worth escalating with higher urgency than
a typical FRICTION item even though it is "only" an adversarial-input
case — a traceback is exactly the failure mode `DELIVERY-STANCE` singles
out as never acceptable, pre- or post-golden. Cases 2-4 are useful mainly
as negative controls: they confirm the adversarial *shape* of an input
(unicode, size, nesting) is not itself the problem — the NaN case fails
because of the value's non-portability, not its unusualness in general.

## Verification

All four cases executed against `master` (worktree `feat/dogfood-corpus`)
on 2026-08-28. Case 1's traceback and exit code `1` are transcribed
verbatim from that run. Cases 2-4's exit codes and `status` lines are
likewise transcribed verbatim (case 3 additionally confirmed the generated
intent was exactly 100,000 characters via shell length check before
dispatch).
