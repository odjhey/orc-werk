---
id: ADAPTER-COMMAND-MAPPING
type: adapter-mapping
status: current
authority: informative
description: Operator-script-to-AssurancePort mapping for CommandAssurance.
---

# command assurance mapping

`CommandAssurance` runs one configured verifier script synchronously on the
first `inspect()` call and snapshots the resulting observation. This mapping is
adapter-local: **`PORT-ASSURANCE` is confirmed unchanged**.

## Judge-only script contract

The script is a read-only judge of the exact candidate supplied on standard
input. It MUST NOT mutate the candidate. The adapter never advertises
`CAP-ASSURE-MAY-MUTATE-CANDIDATE`; choosing a script that changes the worktree
violates the operator-facing script contract even if the process returns a
verdict.

## Trust boundary and invocation

**Trusted to execute:** the script is operator-authored, PR-reviewed, versioned
in the adopter repository, carried by reference in config rather than inline,
and confined to the configured `cwd`.

**Untrusted:** (a) everything entering the script, including candidate
`subject_identity` read from journal data, and (b) everything emitted by the
script. Input crosses only as JSON on standard input, which is then closed. The
script is spawned as the one-element argv list `[resolved_script]` with
`shell=False`; candidate data is never placed in argv, environment variables,
or shell interpolation. Output crosses back only through the validation chain
below; no stdout content can set verdict, lifecycle state, or candidate
fingerprint (`CONF-EXT-004`). Stderr is never journaled verbatim.

This differs deliberately from the `orc refs` hostile-input precedent: refs
allowlists *which* commands run because journal data chooses them. Here trusted
configuration chooses the command, so the allowlist moves to the output side.

The resolved script path (relative paths are resolved against `cwd`) MUST be
inside resolved `cwd`, using path containment rather than textual prefix
matching. Escape is `ERR-VALIDATION`. The script MUST exist and be executable at
`request()` time; absence or inability to execute is
`ERR-PROVIDER-UNAVAILABLE`. Configuration has no inline-script-text, args, or
environment key.

## Input schema

The adapter writes exactly one portable JSON document, then closes standard
input:

```json
{
  "schema": "command-assurance-input/v1",
  "candidate": {
    "id": "candidate-id",
    "work_id": "work-id",
    "execution_id": "execution-id",
    "fingerprint": "fp-...",
    "subject_identity": {}
  },
  "requirements": {},
  "assurance_id": "command:fp-...:0123456789abcdef"
}
```

`command-assurance-input/v1` is a registered, adapter-owned interchange schema.
The candidate fingerprint is bound at request time into the durable
`assurance_id`; the final observation always reports that request-time value,
never a script-derived value (`INV-007`, `INV-008`). Requirements remain opaque
per `PORT-ASSURE-001` and must be portable for this JSON interchange.

## Exit-status mapping

| Process termination | Verdict |
|---|---|
| Clean exit `0` | `accepted` |
| Clean exit `1` | `rejected` |
| Any other exit code | `inconclusive` |
| Signal termination (negative return code) | `inconclusive` |
| Timeout | `inconclusive` after killing the process group |

This table is total and fail-honest (`CONF-ASSURE-006`): no crash, signal, or
timeout is guessed toward acceptance or rejection. Spawn failure is not a
verdict; it raises `ERR-PROVIDER-UNAVAILABLE` and leaves the delivery pending.
The timeout defaults to 300 seconds, is positive, and the subprocess starts a
new session so expiry can kill its process group.

## Standard-output contract

Empty stdout is valid. Otherwise the script MAY emit one JSON object with
exactly these top-level keys:

```json
{"evidence_refs": [], "extensions": {}}
```

Validation order is fixed:

1. read at most 256 KiB plus one byte, dropping enrichment on overflow;
2. decode and `json.loads`;
3. require an object;
4. require the exact top-level allowlist `evidence_refs`, `extensions`;
5. require portable JSON (`CONF-EXT-001`);
6. require `evidence_refs` to be a list;
7. require `extensions` to be an object whose keys are versioned identifier
   strings of the form `<namespace>/v<positive-integer>`;
8. additionally require every `review-findings/v1` finding to contain the
   required-field floor from `EXT-REVIEW-FINDINGS-V1-SCHEMA`, including a
   non-empty evidence list.

Any malformed, oversized, non-portable, or non-allowlisted output drops the
whole enrichment only. The exit-code verdict stands, and evidence gains
`{"stdout_enrichment":"dropped","reason":"..."}` (`CONF-ASSURE-007`).
Extensions are transported opaquely after this schema-floor check and can never
override canonical fields (`CONF-EXT-004`).

The adapter always synthesizes a separate evidence entry containing the
resolved `script`, its run-time content `script_sha256`, `exit_code`,
a non-negative `duration_s`, and `timed_out`. This makes the exact
PR-reviewed verifier content auditable from the journal.

## Config and candidate combination

```json
{
  "candidate": {"adapter": "git", "repo_path": "/abs/repo"},
  "assurance": {
    "adapter": "command",
    "script": "scripts/assure-candidate.sh",
    "cwd": "/abs/repo",
    "timeout_s": 300
  }
}
```

`script` and `cwd` are required non-empty strings. `cwd` has no default.
`timeout_s` is a positive number and defaults to 300. No other keys are
accepted. `assurance.adapter == "command"` requires
`candidate.adapter == "git"`: a real verdict cannot honestly bind to a
config-predicted scripted candidate.

A real assurance adapter derives its own verdict, so attempt entries cannot
also carry scripted `assurance` data. The existing real-assurance narrowing in
CLI config therefore prevents a self-recorded verdict from coexisting with the
command verify seat.

## Idempotency and settlement

Repeated `request()` with one idempotency key returns the same `AssuranceRun`.
The id is `command:<candidate-fingerprint>:<first-16-hex-of-key-sha256>`.
`request()` validates and binds but does not run the verifier. First
`inspect()` executes synchronously and snapshots a settled observation; later
inspections return that immutable snapshot (`CONF-ASSURE-002`).

## Canonical error translation

| Condition | Result |
|---|---|
| Escaped script path, malformed config, non-portable input | `ERR-VALIDATION` |
| Script absent, non-executable, unreadable for hashing, or subprocess spawn fails | `ERR-PROVIDER-UNAVAILABLE` |
| Malformed assurance identity | `ERR-NOT-FOUND` |
| Crash, signal, timeout | Settled `inconclusive`, not an error — re-requested within the assurance budget, `INV-021` |
| Invalid stdout enrichment | Exit-derived settlement plus recorded enrichment drop |

## Lossy mappings and limitations

- Stdout beyond the narrow allowlist, and the whole payload on any validation
  failure, is intentionally discarded; stderr is never evidence.
- Arbitrary script findings cannot be vouched for, so
  `CAP-ASSURE-STRUCTURED-FINDINGS` is withheld even when an opaque
  `review-findings/v1` extension passes its required-field floor
  (`CONF-EXT-005`).
- The adapter proves process termination and script bytes, not that an arbitrary
  script obeyed the judge-only no-mutation promise. Repository protections and
  review remain the enforcement boundary for script behavior.
- Settlement is snapshotted in process. The command has no provider-native
  durable run to reconstruct after process loss; ordinary journal replay is the
  durable path once the settlement Fact has been appended.
