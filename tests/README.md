# Test layout

The Python reference implementation mirrors the contract structure:

- `core/` — pure reducer, policy, invariant, state-machine, and portable serialization tests;
- `conformance/` — reusable provider-independent port conformance suites;
- `scenarios/` — executable forms of the normative golden scenarios.

The full M0 test suite must run without Beads, zxro, ACP/acpx, Git, no-mistakes, CI, or other integration dependencies installed.

## Post-MVP test hardening

Mutation testing (mutmut), property-based testing (hypothesis), and lint/typecheck tooling are deliberately deferred until after a working, dogfoodable MVP ships. This is a delivery-sequencing decision, not a quality bar reduction: pre-MVP falsifiability instead relies on scenario docs as executable specs (`docs/README.md` authoring rule: "a scenario is an executable specification and should map directly to an automated test"), negative-space/invariance tests, adversarial review, and a minimal hand-picked mutation smoke at the M0 integration gate.

When mutmut/hypothesis/lint/typecheck tooling is adopted, it is dev-only tooling and never a runtime dependency — the stdlib-only constraint on `src/orc_werk/core` and the M0 suite (see above) stands unchanged.
