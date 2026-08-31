---
id: ADAPTER-COMMAND-CONFORMANCE
type: adapter-conformance
status: current
authority: informative
description: Conformance evidence for CommandAssurance.
---

# command assurance conformance

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-ASSURE-001` | Pass | Shared assurance mixin re-proof in `tests/conformance/test_command_assurance_conformance.py`. |
| `CONF-ASSURE-002` | Pass | Shared mixin and immutable-settlement tests in the command conformance and unit suites. |
| `CONF-ASSURE-003` | Pass via generic kernel proof | The adapter reports the request-time fingerprint; the existing reducer conformance test rejects foreign evidence. |
| `CONF-ASSURE-004` | Pass | Shared assurance mixin re-proof across the exit-status mapping. |
| `CONF-ASSURE-005` | Not applicable | This is a real assurance adapter; CLI validation rejects config-scripted assurance entries. |
| `CONF-ASSURE-006` | Pass | Full clean 0/1, other-exit, signal, and timeout table in `tests/conformance/test_command_assurance_unit.py`. |
| `CONF-ASSURE-007` | Pass | Full stdout validation table, including oversized, malformed, non-portable, and non-allowlisted output, in the unit suite. |
| `CONF-EXT-001` | Pass | Portable input and output boundary tests. |
| `CONF-EXT-004` | Pass | Hostile stdout cannot set verdict, state, or candidate fingerprint. |
| `CONF-EXT-005` | Pass by withholding | `CAP-ASSURE-STRUCTURED-FINDINGS` is never advertised; `review-findings/v1` still receives its required-field-floor check. |

`tests/scenarios/test_cli_command_assurance_wiring.py` additionally drives a
real CLI dispatch against fixture scripts and a temporary git repository,
proving config validation, git-candidate combination, cwd containment, and
automatic settlement.
