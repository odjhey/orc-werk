---
id: CONTRACT-STORAGE-CONCURRENCY
type: contract
status: current
authority: normative
version: 1
description: File-backed CLI concurrency contract — locking, atomic replacement, append safety, durability boundary, and the required test battery for local multi-process state.
---

# File-backed CLI concurrency contract

This contract is an operator ruling (canonical source: the operator-supplied
"File-Backed CLI Concurrency Contract" text, 2026-09-03), adopted here
verbatim in normative substance and adapted only for repo cross-references
and terminology. Where this document and the operator's source text
diverge in wording, the substance below governs for Orc Werk; no `MUST` in
the source text has been weakened.

All Orc Werk CLI code that reads or mutates persistent local state MUST
follow these rules. This is a cross-cutting contract, not core-domain
semantics: `src/orc_werk/core` has no filesystem concerns at all
(`ARCH-REPOSITORY-STRUCTURE`, `CLAUDE.md` rule 8), so every rule below binds
CLI-layer and adapter code — principally `orc_werk.adapters.jsonl` and
`orc_werk.cli.config`/`orc_werk.cli.main` — never the pure reducer/state
machine.

## 1. Scope

This contract assumes:

- multiple `orc` CLI processes may invoke against the same local state concurrently;
- storage is on a local filesystem;
- processes may terminate unexpectedly;
- supported state includes JSON (dispatch config, effective-config copies), JSONL (the run journal, `PORT-JOURNAL`'s durable adapter), and — hypothetically, see §7/§8 — SQLite.

Network/NFS/SMB filesystems are NOT supported by this concurrency contract.
Orc Werk has no SQLite-backed adapter today; §7/§8 are retained for
completeness and for any future adapter that adds one, but are currently
not applicable to any shipped adapter.

## 2. Locking

Every mutable non-SQLite resource MUST have a stable lock identity.

Example:

```
config.json
config.json.lock
```

Lock the `.lock` file, never the replaceable data file itself. Use an OS
advisory exclusive lock for mutations. The lock file MAY remain
permanently on disk. Do not use lock-file existence to indicate whether a
resource is locked, and do not delete the lock file after releasing the OS
lock. Kernel-managed locks MUST be released by closing the associated file
descriptor.

Any read-modify-write operation MUST acquire the exclusive lock BEFORE the
initial read and hold it until the mutation is committed.

Correct:

```
acquire lock
read
calculate
write
commit/rename
release lock
```

Incorrect:

```
read
acquire lock
write
```

See "Orc application amendments" (A1) for the concrete lock-identity
mapping this contract rules for Orc Werk's run/journal/config layout.

## 3. Lock scope

Hold locks only while accessing protected local state. Do NOT perform the
following while holding a lock:

- network calls;
- LLM/agent calls;
- subprocesses that may run indefinitely (this includes command-assurance
  scripts, `SCN-015`, and observer hooks, `SCN-018` — both spawn outside
  any storage lock already, by construction: neither touches journal or
  config state while its subprocess runs);
- interactive prompts;
- sleeping/backoff unrelated to lock acquisition;
- expensive computation that can safely occur beforehand.

Acquire the lock only immediately before the state transaction.

## 4. Multiple locks

Avoid operations requiring multiple locks where practical. If multiple
locks are unavoidable:

1. canonicalize all lock paths;
2. sort them lexicographically;
3. acquire them in sorted order;
4. release them in reverse order.

All application code MUST use the same ordering. Never acquire locks in
arbitrary business-operation order. Never upgrade a shared lock to an
exclusive lock — release and reacquire, or acquire exclusive access from
the start.

Per A1 below, ordinary single-run Orc Werk operations acquire exactly one
lock (the run-group lock), so this section's multi-lock ordering
requirement does not arise in the common case; it remains binding for any
future operation that must legitimately span more than one run or more
than one workspace-level resource.

## 5. JSON / TXT / snapshot files

Never modify an authoritative snapshot file in place. Mutation MUST be:

```
acquire exclusive lock
read current target
construct complete new contents
create unique temporary file in SAME directory
write complete temporary file
flush/close temporary file
fsync temporary file if durable commit is required
atomically rename temporary file over target
fsync parent directory if durable commit is required
release lock
```

Temporary files MUST be on the same filesystem/directory as the
destination so atomic rename can be used. After a successful rename,
readers must observe either the complete old version or complete new
version, never a partially rewritten version. Readers of a single snapshot
normally do not require a shared lock when all writers follow atomic
replacement. Readers requiring consistency across several resources MUST
participate in the corresponding locking protocol.

`orc_werk.cli.config._atomic_replace_config` (same-directory `tempfile.mkstemp`,
`fsync`, `os.replace`) already implements this section's *replacement*
mechanics correctly for `config.json`. What it does not yet do is the
*enclosing lock* — see "Current gaps at adoption" below.

## 6. JSONL / append-only files

Writers MUST:

```
acquire exclusive lock
serialize the entire logical record
open in append mode
append exactly one newline-terminated record
flush
fsync if durable commit is required
release lock
```

Never implement append as seek-to-end-then-write; use operating-system
append mode. Each record SHOULD contain at least an id, a version/type, a
timestamp, and a payload — see A2 below for Orc Werk's normative carve-out
of the `timestamp` element for canonical journal records specifically.

Readers MUST treat an incomplete final line as an uncommitted/torn record
and ignore it. A JSONL file alone is not a fully robust write-ahead log if
recovery from arbitrary partial writes is required; a real WAL SHOULD use
explicit record framing and preferably length/checksum validation.

`PORT-JOURNAL`'s durable-journal recovery rule already implements this
section's *reader* half: a single unparseable FINAL record, with at least
one valid record preceding it, is treated as a torn write and ignored,
while any earlier malformed record fails closed with `ERR-VALIDATION`
(`PORT-JOURNAL`'s "Durable-journal recovery" section). The *writer* half —
acquiring a lock before each append — is not yet implemented; see "Current
gaps at adoption."

## 7. SQLite

Not currently applicable — no shipped Orc Werk adapter uses SQLite.
Retained for a future adapter that adds one.

Do NOT add external filesystem locks around ordinary SQLite reads or
writes. SQLite is responsible for concurrency of its own
`database.sqlite`/`-wal`/`-shm` triad. For local multi-process
applications, use WAL mode; connections SHOULD configure an appropriate
busy timeout. Mutating operations that read and then modify state MUST
perform the entire operation inside one `BEGIN IMMEDIATE ... COMMIT`
transaction, kept short, with no network/agent calls, interactive prompts,
or long-running computation inside it. Prefer UNIQUE/PRIMARY KEY
constraints, UPSERT, and idempotency keys over application-code-only
duplicate detection.

## 8. SQLite plus other files

Not currently applicable in the literal SQLite sense (§7), but its
governing principle already applies to Orc Werk's one adapter that writes
external state alongside canonical storage: the Beads mirror
(`ADAPTER-BEADS-MAPPING`).

If one command must modify SQLite and non-SQLite state as one logical
operation, an outer application lock MAY be used to prevent concurrent
operations — but an outer lock provides concurrency protection only, not
crash-atomicity across independent files. Prefer one of: (1) store all
authoritative related state inside one transaction; (2) make external
files projections that can be regenerated from the authoritative store;
(3) use an explicit WAL/recovery protocol. Do not claim atomicity across
independent files merely because an exclusive lock is held.

The Beads mirror already satisfies option (2)'s spirit without a SQLite
backend to regenerate from: it is a write-only projection of canonical
journal/config state into `bd`'s own store (`INV-014`'s provider-vocabulary
quarantine — mirror content is never read back into orc-werk policy or
canonical state, `docs/adapters/beads/mapping.md`'s "Degraded mirror"
section). Because the mirror is never authoritative and never read back,
no atomicity claim between the journal/config and the mirror is made or
needed; a mirror write that lags, fails, or races a concurrent journal/
config mutation degrades to a stale or missing `bd` reflection, never to
corrupt canonical state. This is the same reasoning `SCN-018` already
applies to observer hooks' pure-egress posture.

## 9. Durability

Concurrency safety and crash durability are different requirements.
Atomic rename protects readers from observing partial snapshot
replacement; OS locks protect cooperating processes from concurrent
races. For state that must survive power loss or kernel crash,
additionally `fsync(file)` and, after file creation/replacement,
`fsync(parent directory)` must be used as appropriate. If the
application's durability requirement is only unexpected process
termination, atomic replacement without forced disk synchronization may be
sufficient. The durability level MUST be explicit in the storage
implementation.

Orc Werk's declared durability level is **process-crash durability**, not
power-loss/kernel-crash durability: `JSONLJournal` flushes every append
(visible to any other reader immediately, survives a process crash) but
does not `fsync`, an explicit accepted M0 stance revisited only alongside
an advertised stronger capability (`orc_werk.adapters.jsonl.journal`'s
module docstring, "Durability stance" section). `CONTRACT-DURABILITY`
governs what non-core information Orc Werk owns durably and who owns it;
this contract does not restate that ledger — see it for the full
ownership matrix. This contract owns only the *safety-under-concurrency*
question; `CONTRACT-DURABILITY` owns the *what-survives-what-crash*
question.

## 10. Canonical lock identity

Different processes MUST resolve the same logical resource to the same
lock. Prefer `<resource>.lock`, or, for a group of resources,
`<workspace>/.state.lock`. Resolve symlinks/canonical parent paths
consistently before deriving lock identities. Do not allow two aliases for
the same state directory to produce unrelated locks.

Orc Werk already canonicalizes journal-directory resolution at a single
choke point (`resolve_journal_dir`, hardened by issue #220's fix refusing
a journal dir that is itself a run directory) — the same canonicalization
step A1's lock-identity derivation builds on, so two aliases for the same
run directory cannot yet produce, and after A1 lands still cannot produce,
unrelated locks.

## 11. Failure behavior

Lock acquisition MUST have a bounded timeout. On timeout, fail with a
structured lock-busy error rather than modifying state without the lock.
Never fall back to an unlocked write. Never delete another process's
kernel lock. A crashed process MUST NOT require manual stale-lock cleanup
when kernel-managed locking is used.

Orc Werk's canonical error taxonomy (`CONTRACT-ERRORS`) is amended
additively to carry this section's structured lock-busy error — see the
"Current gaps at adoption" list's `ERR-BUSY` row and `CONTRACT-ERRORS`
itself.

## 12. Required concurrency tests

Every storage implementation MUST have automated tests covering:

1. many concurrent read-modify-write operations with no lost updates;
2. many concurrent JSONL appenders with every record preserved and parseable;
3. process termination while holding a lock followed by successful acquisition from another process;
4. process termination during snapshot replacement leaving either the old or new valid snapshot;
5. many simultaneous SQLite writers producing the expected final state (not applicable — §7);
6. lock timeout behavior;
7. multiple-resource locking without deadlock;
8. malformed/incomplete final JSONL or WAL records during recovery.

Tests SHOULD run operations in separate OS processes, not merely multiple
async tasks or threads — this is the conformance bar `SCN-019` specifies
as an executable requirement, and PR 2 (implementation) is the vehicle for
the test battery itself.

## 13. Architecture rule

Correctness MUST NOT depend on a daemon, socket server, in-process mutex,
or singleton process existing. The persistence layer itself must remain
safe under multiple independent CLI processes. A future daemon or IPC
layer may improve performance, scheduling, notifications, batching, or
coordination, but it must not be required to prevent storage corruption.
The storage concurrency contract remains the correctness boundary.

See A3 below: this section is precisely why the one-dispatcher-per-run
convention (`PLAYBOOK-AGENT-CLI`) can remain seat semantics but can no
longer be read as this contract's correctness mechanism.

---

## Orc application amendments

Three watchtower rulings apply this contract's generic rules to Orc Werk's
concrete layout. These are binding amendments, not commentary.

### A1 — Lock identity

One lock per run directory: `<journal-dir>/<run_id>/.state.lock`, covering
that run's `journal.jsonl` AND `config.json` as a single group, per §10's
group form (`<workspace>/.state.lock`). Because journal and config for one
run share a single lock, §4's multi-lock ordering requirement never
arises for single-run operations — there is exactly one lock to acquire.

A run under the legacy flat layout (`<run_id>.jsonl` /
`<run_id>+times.jsonl`, pre-issue-#55; `orc_werk.adapters.jsonl.layout`)
has no run directory to hold the lock file; such a run's group lock is
`<journal-dir>/<run_id>.lock` instead — the same canonical-resource form
(§10), scoped by the run id rather than a directory.

Workspace-level mutable files outside any run directory (for example a
future `profile.json` some verb writes) use `<file>.lock` per §2's
single-resource form, not the run-group lock.

### A2 — Timestamp carve-out

§6's per-record `timestamp` SHOULD does NOT apply to canonical journal
records. `PORT-JOURNAL-ENVELOPE` (`PORT-JOURNAL`) carries no `timestamp`
field at all: the determinism hard bar (`DELIVERY-STANCE` — no randomness
or wall-clock in canonical data or idempotency keys; `INV-020`) governs
canonical journal content, and `seq` — the journal adapter's own
monotonically increasing per-run integer, assigned on append — is the
ordering identity `CONF-JOURNAL-001`/`CONF-JOURNAL-003` require, not a
wall-clock stamp. Wall-clock observations live only in non-canonical
sidecars that no replay/projection path ever reads: the `times.jsonl`
observed-at sidecar (`CONTRACT-DURABILITY`'s "Record observation
wall-clock times" row) is the concrete instance today.

Precedence: where §6's generic per-record field list and the determinism
hard bar would otherwise conflict for canonical journal content, the
determinism hard bar wins. §6 remains unamended for any future non-canonical
append-only log this contract governs that carries no such determinism
requirement.

### A3 — Protocol demotion

The one-dispatcher-per-run rule (`PLAYBOOK-AGENT-CLI` §5 "one writer per
run journal at a time," §6 "concurrent `orc dispatch` of the same run is
forbidden") remains in force as **seat semantics** — who may advance a run,
a process-discipline rule agents follow exactly as they follow role
separation (`PLAYBOOK-AGENT-CLI` §2). It is no longer, and after this
contract's implementation lands must no longer be, read as a **correctness
precondition**: §13 requires the storage layer itself be safe without it.
Concurrent dispatches MUST be non-corrupting under this contract even
though they remain non-recommended and out of protocol under that
playbook — a violation of the playbook's discipline is a coordination
defect to fix upstream, never a storage-corruption incident.

### Durability level (§9)

Restated once, pointer-only: Orc Werk's declared durability level is
process-crash durability (flush-no-fsync, torn-tail heal) — see §9 above
and `CONTRACT-DURABILITY`, which this contract does not duplicate.

## Current gaps at adoption

Honest, watchtower-verified inventory as of this contract's adoption
(`v0.7.3`, `07c0209`). This is PR 2's (implementation) checklist — nothing
below is fixed by this docs-only PR.

| Gap | Section(s) violated | Location |
|---|---|---|
| No OS advisory locks exist anywhere in `src/` | §2, §10 | repo-wide |
| The JSONL journal's append path acquires no lock before appending; the adapter's own docstring declares concurrent same-file appenders out of scope | §6 (writer half), §13 | `src/orc_werk/adapters/jsonl/journal.py` |
| `orc record`'s read-modify-write reads the current config before acquiring any lock — the atomic-replace mechanics on the write half already satisfy most of §5, but the enclosing lock required by §2 does not exist | §2, §5 (partial) | `src/orc_werk/cli/config.py` — `_atomic_replace_config`, `record_assurance_entry`, `record_execution_outcome_entry` (~953–1009) |
| `_persist_effective_config` is a plain, non-atomic `Path.write_text` — no temp file, no atomic rename, no lock | §5 (entirely) | `src/orc_werk/cli/main.py` `_persist_effective_config` (~201–219) |
| No bounded lock-timeout or structured busy error exists, because no lock exists to time out | §11 | repo-wide; `ERR-BUSY` (`CONTRACT-ERRORS`) is registered by this PR but unused until PR 2 |
| Concurrency safety today is provided entirely by the one-dispatcher-per-run social convention, not by the storage layer (the gap A3 names explicitly) | §13 | `docs/playbooks/agent-cli-usage.md` |
| No automated concurrency test battery (§12's eight items) exists | §12 | deferred to PR 2 (`SCN-019`) |

The live symptom this contract closes: two seats recording into the same
multi-work run's `config.json` concurrently can lose an update today —
both read the pre-mutation file, both compute a merge, the second
`os.replace` silently wins and the first seat's recorded outcome is gone
from disk with no error raised.

## Related

- `PORT-JOURNAL`
- `CONTRACT-DURABILITY`
- `CONTRACT-ERRORS`
- `CONTRACT-EXTENSIONS`
- `INV-014`
- `INV-020`
- `DELIVERY-STANCE`
- `SCN-019`
- `ADAPTER-BEADS-MAPPING`
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`)
