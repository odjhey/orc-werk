---
id: DFS-009
type: scenario
status: current
authority: informative
description: Journal recovery at the CLI boundary — torn tail heals, corrupt middle and missing path-like targets fail closed; garbage files and bare unknown run ids still silently succeed (issue #18).
---

# DFS-009: journal recovery — torn tail, corrupt middle, missing/garbage paths

## Concern tags

`journal-recovery`, `cli-errors`

## Intent

`PORT-JOURNAL`'s durable-journal recovery rule
(`docs/contracts/ports/journal-port.md`) requires: tolerate a single
unparseable FINAL record as a torn write (heal-while-use); reject any
earlier malformed record with `ERR-VALIDATION` (fail closed). This
scenario checks that rule from the CLI's `status`/`history` surface, plus
two related but distinct "the target itself is wrong" cases that the
contract does not directly speak to: a target path that does not exist at
all, and a target file that exists but was never a journal in the first
place. Round 1 found the second of those (issue #18) exploits the
torn-tail tolerance itself: a one-line garbage file is *entirely* a final
line, so it is indistinguishable from a legitimately torn write.

## Setup

Four fixtures, copied into a fresh scratch directory before running
commands (never read/written in place inside the repo):

- `torn-tail.jsonl` — DFS-001's happy-path journal (19 good records) plus
  one extra unparseable, no-trailing-newline final line
  (`{"seq":20,"kind":"fact","id":"FACT-BOGUS","data":{"trunca`) —
  simulates a crash mid-append.
- `corrupt-middle.jsonl` — the same happy-path content, but the record at
  seq 6 (`FACT-WORK-READY`) is truncated mid-line while *more valid JSON
  records follow it* — this is not a torn tail (the corruption is not the
  last thing in the file), it is real corruption.
- `garbage.jsonl` — a single line of plain English, not JSON at all:
  `hello this is not json at all, just plain text`.
- (no file) a nonexistent `.jsonl` path, and separately a bare run id
  that does not correspond to any journal in the target directory at all.

## Commands

```sh
SCRATCH="$DOGFOOD_SCRATCH/DFS-009"
mkdir -p "$SCRATCH/torn" "$SCRATCH/mid" "$SCRATCH/empty"
cp dogfood/scenarios/DFS-009-journal-recovery/torn-tail.jsonl "$SCRATCH/torn/s1-happy.jsonl"
cp dogfood/scenarios/DFS-009-journal-recovery/corrupt-middle.jsonl "$SCRATCH/mid/s1-happy.jsonl"
cp dogfood/scenarios/DFS-009-journal-recovery/garbage.jsonl "$SCRATCH/ghost.jsonl"

# 1: torn tail — expect heal, ACCEPTED, exit 0
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/torn/s1-happy.jsonl"

# 2: corrupt middle — expect ERR-VALIDATION, exit 2
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/mid/s1-happy.jsonl"

# 3: garbage single-line file, addressed by its actual path — issue #18
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/ghost.jsonl"

# 4a: missing path that looks like a path (ends in .jsonl) — expect
# ERR-NOT-FOUND naming the path
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/does-not-exist.jsonl"

# 4b: bare nonexistent run id (no separator, no .jsonl), run from an
# empty scratch cwd so any side effect (e.g. a stray .orc dir) is visible
(cd "$SCRATCH/empty" && PYTHONPATH="$PWD/../../../../src" python3 -m orc_werk.cli status totally-nonexistent-run-id; ls -la)

# 5: baseline contrast — a directory that legitimately has no journals
mkdir -p "$SCRATCH/emptydir"
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/emptydir"
```

(Adjust the `PYTHONPATH` relative path in case 4b to wherever `src`
actually resolves from the scratch cwd, or just export an absolute
`PYTHONPATH` before `cd`ing.)

## Expected observable outcomes

**1 (torn tail) — correct, confirmed:** exit `0`. `status` prints `run:
s1-happy`, `intent: s1-happy`, `work work-1: state=ACCEPTED attempts=1
candidate_fingerprint=fp-32f9dbceb02fbe89eb72171f` — identical to DFS-001.
The torn 20th line is silently ignored per the recovery rule; it is *not*
truncated off disk by a read-only `status`/`history` call (only the next
*write*/`dispatch` to that journal heals the file on disk — `_heal_tail`
runs from `_append`, not from `history()`/`load_projection()`).

**2 (corrupt middle) — correct, confirmed:** exit `2`, stderr:
`{"details": {"byte_offset": 1171, "delivery_run_id": "s1-happy"},
"error": "ERR-VALIDATION", "message": "malformed non-final JSONL journal
line (corrupt journal file)"}`. Fails closed, per contract, because the
malformed record is not the last one in the file.

**3 (garbage single-line file) — known bug, issue #18:** exit `0`,
`status` prints `run: ghost` then `(no work recorded yet)` — silent
"success" on a file that was never a journal, because the file's one line
*is* its final line, so it is indistinguishable from a torn write with
zero preceding good records. Report as BUG each time this reproduces;
issue #18 proposes only tolerating a torn tail when at least one valid
record precedes it (a docs amendment to `PORT-JOURNAL` is required before
implementing that, since current behavior is normatively correct per the
letter of the existing rule — this is a contract-refinement request, not
a plain code bug).

**4a (missing path-looking target) — correct, confirmed:** exit `2`,
stderr `{"error": "ERR-NOT-FOUND", "message": "journal path does not
exist: <path>", "details": {"path": "<path>"}}` — the missing path is
named. A target that *looks* like a path (contains a path separator or
ends in `.jsonl`) but does not exist no longer falls through to the
bare-run-id branch. This case was fixed by the round-1 fix PR
(`_looks_like_journal_path` in `src/orc_werk/cli/main.py`; it previously
leaked a confusing "not a safe JSONL journal filename component"
`ERR-VALIDATION` or silently succeeded); guarded by
`tests/scenarios/test_cli_dogfood_fixes.py`.

**4b (bare nonexistent run id) — still fail-open (same family as issue
#18's silent-success framing):** `status` prints `run:
totally-nonexistent-run-id` then `(no work recorded yet)`, exit `0` — a
bare token with no separator and no `.jsonl` suffix is by design resolved
as a run id against the CLI-relative default journal directory `./.orc`,
and an unknown run id there projects to an empty run rather than an
error. `JSONLJournal.__init__` also unconditionally `mkdir`s that
directory even for a read-only `status` call — confirmed, a fresh `.orc/`
directory is created in the invocation cwd as a side effect. Report
FRICTION with both symptoms (silent success *and* the stray directory)
each time this reproduces; like case 3, tightening this is a
contract/behavior refinement to route via the watchtower, not a plain
code bug.

**5 (empty dir baseline) — correct, confirmed:** exit `2`, stderr:
`{"details": {"path": "<dir>"}, "error": "ERR-NOT-FOUND", "message": "no
*.jsonl journal files found under directory: <dir>"}`. Included as a
positive contrast: a directory target that legitimately has zero journals
already fails closed correctly — it is specifically the *bare run id*
and *garbage-file* paths that still leak.

## Judgment notes

Cases 3 and 4b are exactly the kind of finding this corpus exists for:
both pass their "did it crash" bar trivially (no traceback, valid JSON
error shape when there is an error at all) while silently doing the wrong
thing on a completely wrong target. A checker agent should specifically
read the `status` output text, not just the exit code, to catch these — a
mechanical "exit code == expected" assertion would have missed both in
round 1. Case 4a is the fixed sibling: if it ever regresses to silent
success or the old "unsafe filename" leak, escalate as BUG (the guard is
in `tests/scenarios/test_cli_dogfood_fixes.py`).

## Verification

All cases re-run against post-round-1-fix `master` (merged into this
branch) on 2026-08-28; outputs above (including the exact `byte_offset:
1171`, case 4a's `ERR-NOT-FOUND` naming the path, and case 4b's stray
`.orc/` directory) are transcribed verbatim from that run. Cases 1/2/5
are unchanged from round 1; case 4a's fix was confirmed live; cases 3 and
4b still reproduce round 1's fail-open behavior (issue #18 and its
bare-run-id sibling remain open).
