---
id: DFS-009
type: scenario
status: current
authority: informative
description: Journal recovery at the CLI boundary — torn tail heals, corrupt middle fails closed, missing/garbage targets should fail closed too (one confirmed bug, issue #18).
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
- (no file) a bare run id that does not correspond to any journal in the
  target directory at all.

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

# 4: missing path — a bare run id with nothing behind it, run from an
# empty scratch cwd so any side effect (e.g. a stray .orc dir) is visible
(cd "$SCRATCH/empty" && PYTHONPATH="$PWD/../../../../src" python3 -m orc_werk.cli status totally-nonexistent-run-id; ls -la)

# 5: baseline contrast — a directory that legitimately has no journals
mkdir -p "$SCRATCH/emptydir"
PYTHONPATH=src python3 -m orc_werk.cli status "$SCRATCH/emptydir"
```

(Adjust the `PYTHONPATH` relative path in case 4 to wherever `src` actually
resolves from the scratch cwd, or just export an absolute `PYTHONPATH`
before `cd`ing.)

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

**4 (missing path) — known bug (untracked by number, same family as
issue #18 / #17's fail-open framing) — expected (post-fix): canonical
`ERR-NOT-FOUND`, exit `2`, no directory created.** Actual on current
`master`: `status` prints `run: totally-nonexistent-run-id` then `(no
work recorded yet)`, exit `0` — because `_resolve_journal` (`src/orc_werk/cli/main.py`)
falls through to treating any non-existent path as a bare run id resolved
against the CLI-relative default journal directory `./.orc`, and
`JSONLJournal.__init__` unconditionally `mkdir(parents=True,
exist_ok=True)`s that directory even for a read-only `status` call — so
this bug has a **side effect** too: confirmed, a fresh `.orc/` directory
is created in the invocation cwd. Report BUG with both symptoms (wrong
exit code *and* the stray directory) each time this reproduces.

**5 (empty dir baseline) — correct, confirmed:** exit `2`, stderr:
`{"details": {"path": "<dir>"}, "error": "ERR-NOT-FOUND", "message": "no
*.jsonl journal files found under directory: <dir>"}`. Included as a
positive contrast: a directory target that legitimately has zero journals
already fails closed correctly today — it is specifically the *bare run
id* and *garbage-file* paths that leak.

## Judgment notes

Cases 3 and 4 are exactly the kind of finding this corpus exists for: both
pass their "did it crash" bar trivially (no traceback, valid JSON error
shape when there is an error at all) while silently doing the wrong thing
on a completely wrong target. A checker agent should specifically read the
`status` output text, not just the exit code, to catch these — a
mechanical "exit code == expected" assertion would have missed both in
round 1.

## Verification

Read-only spot-check run against `master` (worktree `feat/dogfood-corpus`)
on 2026-08-28 for all five cases; outputs above (including the exact
`byte_offset: 1171` and the stray `.orc/` directory) are transcribed
verbatim from that run, not merely carried over from round 1. Case 1/2/5
match round-1 findings exactly; cases 3/4 reproduce the round-1 findings
(issue #18, and the related missing-path side effect) unchanged.
