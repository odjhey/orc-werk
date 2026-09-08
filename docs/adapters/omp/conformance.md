---
id: ADAPTER-OMP-CONFORMANCE
type: conformance-report
status: current
authority: informative
description: OMP conformance status -- CONF-EXT-001 through CONF-EXT-006 for executor-identity/v1, plus TASK-M5-001's landed harness capability-test evidence.
---

# OMP conformance

OMP implements no `PORT-WORK-GRAPH`, `PORT-EXECUTION`, `PORT-ASSURANCE`,
or `PORT-CANDIDATE` interface (`README.md`), so `CONF-WORK-*`,
`CONF-EXEC-*`, `CONF-ASSURE-*`, and `CONF-CAND-*` are **not applicable**
as literally written — there is no adapter code for the shared
conformance mixins to drive (unlike `ADAPTER-BEADS-CONFORMANCE`, which at
least mirrors `CONF-WORK-*` against a real projection; OMP has no
projection to mirror either). The only canonical surface an OMP-run seat
touches is the `executor-identity/v1` extension it supplies to `orc
record`.

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-EXT-001` (portable payload) | Pass | `tests/conformance/test_extension_producer_conformance.py::ExecutorIdentityV1EmissionTest` — both roles' payloads are plain JSON strings, validated against the registered schema. |
| `CONF-EXT-002` (unknown-extension safety) | Pass via generic kernel proof | `tests/conformance/test_extensions_conformance.py` (core-ignorance suite) proves canonical projection is unaffected by extension presence/absence for any producer, OMP included — nothing OMP-specific is exercised because nothing OMP-specific exists at this layer. |
| `CONF-EXT-003` (lossless preservation) | Pass | Same `ExecutorIdentityV1EmissionTest`: the config-entry payload round-trips byte-identical into `FACT-EXEC-SETTLED`/`FACT-ASSURE-SETTLED`'s `extensions`, regardless of which harness invoked `orc record`. |
| `CONF-EXT-004` (canonical fields win) | Pass via generic kernel proof | The reducer's existing foreign-fingerprint rejection and extension-transport tests do not special-case a producer identity; an OMP-supplied `executor-identity/v1` payload has no path to override candidate/verdict/outcome fields any more than a hand-typed one does. |
| `CONF-EXT-005` (capability honesty) | Not applicable | This requirement gates a provider's *advertised* capability against a named extension (e.g. `CAP-ASSURE-STRUCTURED-FINDINGS` for `review-findings/v1`). OMP advertises no `CAP-*` at all (`capabilities.md`), so this gating condition is never met, mirroring `ADAPTER-BEADS-CONFORMANCE`'s `CONF-WORK-004` "not applicable" row. |
| `CONF-EXT-006` (core ignorance) | Pass via generic kernel proof | Same core reducer/state-machine suite as `CONF-EXT-002`; an `executor-identity/v1` payload's `role`/`model`/`session_ref`/`seat_ref` values never change a canonical transition regardless of producer. |

All six rows are proven by the same harness-independent test suite that
already covers every `orc record` invoker (`test_extension_producer_
conformance.py`, `test_extensions_conformance.py`); no OMP-specific test
exists or is needed, because there is no OMP-specific code path to test —
per `README.md`, an OMP-run seat calls the identical `orc record` CLI
surface any other executor does.

## `TASK-M5-001`'s harness capability-test evidence

The task-card contract for this document additionally calls for citing
`TASK-M5-001`'s capability-test evidence. That report
(`docs/reports/2026-09-07-omp-capability-test.md`) has no corresponding
registered `CONF-*` requirement — it tests properties of the *harness*
(tool-call blocking, worktree fencing, schema rejection, timeout
lifecycle, transcript durability, role-identity), not of a canonical Port
this repository's conformance registry (`docs/conformance/README.md`)
defines requirements for. See `capabilities.md`'s findings table for the
current per-point status (filled since `TASK-M5-001`'s report landed
2026-09-07, PR #277, and reconciled 2026-09-08 per issue #287); that
table is this document's only home for those points; no new `CONF-*`
family is declared here since none is registered in
`docs/conformance/`.

## Related

- `TASK-M5-001`
- `docs/conformance/README.md`, `docs/conformance/extensions.md`
- `docs/adapters/beads/conformance.md` (the "not applicable"/analog
  precedent for a non-Port-implementing adapter)
