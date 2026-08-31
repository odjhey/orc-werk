---
id: SCN-015
type: scenario
status: current
authority: normative
description: A confined operator-authored command verifies a bound git candidate with honest exit-status and hostile-output handling.
---

# SCN-015 — Command assurance

## Given

- A real git candidate C1 is bound to `CommandAssurance`.
- Configuration points to an executable, PR-reviewed verifier script whose
  resolved path is inside configured `cwd`.
- The adapter sends `command-assurance-input/v1` JSON on standard input using
  an argv-list subprocess with no shell.

## Then

1. Clean exit 0 settles `accepted`; clean exit 1 settles `rejected`.
2. Any other exit code, signal termination, or timeout settles
   `inconclusive`; no such termination is guessed toward acceptance or
   rejection (`CONF-ASSURE-006`).
3. Spawn failure raises `ERR-PROVIDER-UNAVAILABLE` rather than fabricating a
   verdict.
4. The settled observation names C1's request-time fingerprint and includes
   adapter-synthesized evidence with script path, run-time script hash, exit
   code, duration, and timeout status.
5. Empty or valid allowlisted stdout may enrich evidence and extensions.
   Malformed, oversized, non-portable, or non-allowlisted stdout changes none
   of verdict, state, or candidate fingerprint; the enrichment is dropped and
   that drop is recorded (`CONF-ASSURE-007`, `CONF-EXT-004`).
6. Re-inspection cannot change a settled observation (`CONF-ASSURE-002`).

## Containment and seat checks

- A script resolving outside `cwd` is rejected with `ERR-VALIDATION` before it
  can run.
- `assurance.adapter == "command"` requires `candidate.adapter == "git"`.
- No config-scripted verdict can coexist with the command assurance seat.
- The script is judge-only and the adapter withholds both
  `CAP-ASSURE-MAY-MUTATE-CANDIDATE` and
  `CAP-ASSURE-STRUCTURED-FINDINGS`.

## Mutation check

Accepting crash/timeout as 0 or 1, using stdout to override canonical fields,
executing through a shell, carrying identity in argv/environment, allowing cwd
escape, binding a scripted candidate, or allowing a scripted verdict alongside
the real command seat makes this scenario fail.

Verifies: `PORT-ASSURANCE`, `CONF-ASSURE-001`, `CONF-ASSURE-002`,
`CONF-ASSURE-004`, `CONF-ASSURE-006`, `CONF-ASSURE-007`, `CONF-EXT-001`,
`CONF-EXT-004`, `CONF-EXT-005`, `INV-007`, `INV-008`.
