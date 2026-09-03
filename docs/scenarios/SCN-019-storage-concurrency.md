---
id: SCN-019
type: scenario
status: current
authority: normative
description: Concurrent-storage safety as executable specification — no lost updates, no corrupted appends, crash-safe recovery, and a canonical busy error instead of an unlocked fallback (`CONTRACT-STORAGE-CONCURRENCY`).
---

# SCN-019 — Storage concurrency

## Purpose

`CONTRACT-STORAGE-CONCURRENCY` rules the locking, atomic-replacement, and
append-safety protocol every Orc Werk CLI storage path must follow once
implemented. This scenario is that contract's §12 required test battery
stated as an executable specification, and is the conformance bar the
implementation PR (PR 2, following this docs-only PR) must satisfy before
any lock-acquiring code lands. It exists because the live gap it closes is
real, not hypothetical: two seats recording into the same multi-work run's
`config.json` concurrently can silently lose one seat's recorded outcome
today (`CONTRACT-STORAGE-CONCURRENCY`'s "Current gaps at adoption" list).

Unlike the other golden scenarios, this one is not a delivery-state-machine
walkthrough — `src/orc_werk/core` has no filesystem concerns at all
(`ARCH-REPOSITORY-STRUCTURE`) and is untouched by anything here. This
scenario exercises the CLI/adapter storage layer directly:
`orc_werk.adapters.jsonl` (the journal) and `orc_werk.cli.config`/
`orc_werk.cli.main` (the config read-modify-write and effective-config
persistence paths).

## Given

- A run directory laid out per `CONTRACT-STORAGE-CONCURRENCY` A1:
  `<journal-dir>/<run_id>/journal.jsonl`, `<journal-dir>/<run_id>/config.json`,
  and `<journal-dir>/<run_id>/.state.lock` covering both as one group.
- Multiple independent OS processes (not threads or async tasks — §12's
  "SHOULD run in separate OS processes" requirement, stated here as a
  conformance bar, not merely a recommendation) capable of invoking the
  same read-modify-write, append, or replacement operation concurrently
  against that run.
- A bounded lock-acquisition timeout configured for the storage layer.

## When / Then, by required test

Each numbered item below is one required automated test, numbered exactly
as `CONTRACT-STORAGE-CONCURRENCY` §12 numbers them. All eight source items
are specified here — including item 5, whose applicability is conditional
and stated in place, the same way that contract handles §7/§8.

### 1. Concurrent read-modify-write loses nothing

**When** N processes each run a `record_execution_outcome_entry`/
`record_assurance_entry`-shaped read-modify-write against the same run's
`config.json` concurrently, each merging a distinct attempt-entry key.
**Then** every process's mutation is present in the final `config.json` —
none is silently overwritten by a later writer's read-before-my-write race
— and `config.json` parses as valid JSON at every point an external
reader might open it (never a torn intermediate state).

### 2. Concurrent JSONL appenders preserve every record

**When** N processes each append one or more distinct, complete journal
records to the same run's `journal.jsonl` concurrently.
**Then** every appended record is present, in some deterministic total
order recorded as `seq` (`PORT-JOURNAL-ENVELOPE`), every line in the final
file parses as one complete JSON object, and no record is partially
interleaved with another (never two records' bytes merged onto one line,
never one record's bytes split across two lines).

### 3. Crash while holding the lock recovers without manual cleanup

**When** a process acquires the run's `.state.lock`, then terminates
(SIGKILL, uncatchable) before releasing it.
**Then** a subsequent process from a fresh invocation successfully
acquires the same lock and proceeds — no stale-lock file blocks it, no
operator or script needs to delete anything by hand (`CONTRACT-STORAGE-CONCURRENCY`
§11's "MUST NOT require manual stale-lock cleanup" clause, guaranteed by
kernel-managed (`flock`/`fcntl`) locking releasing automatically when the
crashed process's file descriptor closes on process death).

### 4. Crash mid-replacement leaves a valid snapshot

**When** a process is terminated mid-way through the atomic-replacement
sequence for `config.json` (after the temp file is written but before, or
during, `os.replace`) or, separately, mid-way through `_persist_effective_config`'s
future lock-and-atomic-replace form.
**Then** the target file, read by any subsequent process, is either the
complete old snapshot or the complete new snapshot — never a partially
written, truncated, or otherwise invalid file. A leftover temp file (if the
crash lands before `os.replace`) is inert and never mistaken for the
target by any reader.

### 5. Many simultaneous SQLite writers produce the expected final state

No SQLite storage implementation currently exists in Orc Werk
(`CONTRACT-STORAGE-CONCURRENCY` §7); this item binds any future one. It is
kept in place, at the source's number, rather than dropped or renumbered.
**When** (for any future SQLite-backed adapter) N processes each perform a
transactional read-then-modify write (`BEGIN IMMEDIATE ... COMMIT`, §7's
preferred pattern) against the same database concurrently.
**Then** the final database state is exactly what serial execution of the
same N operations would produce — no lost update, no constraint bypass,
no partial transaction visible — and the test lands with, not after, the
first such adapter.

### 6. Lock timeout surfaces `ERR-BUSY`, never an unlocked fallback

**When** a process holds the run's lock for longer than another process's
configured bounded timeout, and the second process attempts a
lock-requiring operation during that window.
**Then** the second process fails fast with the canonical structured
`ERR-BUSY` (`CONTRACT-ERRORS`) — never silently proceeding without the
lock, never corrupting state, never hanging past the bound.

### 7. Multiple-resource locking never deadlocks

**When** an operation legitimately requires more than one lock (an
out-of-scope case for ordinary single-run operations under A1, but
exercised here as a forward-looking conformance case per
`CONTRACT-STORAGE-CONCURRENCY` §4).
**Then** every participant acquires canonicalized, lexicographically
sorted lock paths in that sorted order and releases them in reverse order;
running many such multi-lock operations concurrently, with overlapping
resource sets across participants, never deadlocks.

### 8. Malformed/incomplete final JSONL or WAL records recover cleanly

This is Orc Werk's strongest already-existing behavior in the whole
battery: the torn-tail truncate-heal rule is implemented and shipping
today (`orc_werk.adapters.jsonl.tailsafe`, factored out of `JSONLJournal`
for reuse by any same-shape log), so this item mostly codifies what exists
rather than demanding new machinery — what is new is exercising it under
this scenario's separate-OS-process concurrency conditions rather than the
single-writer crash conditions it was built for.
**When** a run's `journal.jsonl` (or any WAL-shaped log this contract
governs) ends in a malformed or incomplete final line, with at least one
valid record preceding it — whether left by a crash mid-append or by a
concurrent-writer interleaving fault.
**Then** a reader treats the final line as a torn write and ignores it,
continuing from the last good record, and the torn bytes are truncated
away on the next append so the file returns to
one-valid-JSON-object-per-line form (heal-while-use) — the existing
`PORT-JOURNAL` durable-journal recovery rule. Any malformed NON-final
record remains real corruption and fails closed with `ERR-VALIDATION`,
and a file with zero valid records is rejected with `ERR-VALIDATION`
rather than presented as empty history, exactly per that rule.

## Mutation check

Any of the following makes this scenario fail: a lost update under
concurrent read-modify-write (item 1); an interleaved, truncated, or
duplicated record under concurrent appenders (item 2); a stale lock that
blocks a subsequent process indefinitely, or requires manual cleanup,
after the holder crashes (item 3); a config or journal file observably
torn (neither the complete old nor complete new snapshot) after a
mid-replacement crash (item 4); a future SQLite adapter landing without
item 5's simultaneous-writer test, or silently dropping/renumbering item 5
from this battery (item 5); a lock-timeout path that falls back to an
unlocked write instead of returning `ERR-BUSY` (item 6); a multi-lock
operation that deadlocks or acquires locks out of the canonical sorted
order (item 7); a malformed non-final record silently skipped instead of
failing closed with `ERR-VALIDATION`, or a torn final line that is not
healed away on the next append (item 8, `PORT-JOURNAL`'s existing rule);
or any test in this battery passing only under threads/async tasks while
failing under real separate OS processes.

## Verifies

- `CONTRACT-STORAGE-CONCURRENCY` — the numbered items above map one-to-one,
  keeping the source numbering, onto that contract's §12 required-test
  list, and exercise its §2, §5, §6, §7 (conditionally, item 5), §10, and
  §11 rules plus the A1 lock-identity amendment.
- `PORT-JOURNAL` — the durable-journal torn-tail recovery rule (item 8)
  and the `seq` ordering identity (item 2).
- `CONTRACT-ERRORS` — `ERR-BUSY` (item 6).
- `INV-020` — idempotent, deterministic replay is unaffected by concurrent
  storage access: re-dispatch after any of the above recovers cleanly
  because idempotency keys derive from durable canonical state, never
  process identity or timing.
- `CONTRACT-DURABILITY` — this scenario exercises concurrency safety only;
  it does not raise or lower Orc Werk's declared process-crash durability
  level (`CONTRACT-STORAGE-CONCURRENCY` §9).

## Not yet implemented

As of this scenario's registration, no lock-acquiring code exists in
`src/` (`CONTRACT-STORAGE-CONCURRENCY`'s "Current gaps at adoption" list).
This scenario specifies the conformance bar the implementation PR must
satisfy; it does not itself land a passing automated test in this PR.
