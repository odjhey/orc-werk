# Test layout

The Python reference implementation mirrors the contract structure:

- `core/` — pure reducer, policy, invariant, state-machine, and portable serialization tests;
- `conformance/` — reusable provider-independent port conformance suites;
- `scenarios/` — executable forms of the normative golden scenarios.

The full M0 test suite must run without Beads, zxro, ACP/acpx, Git, no-mistakes, CI, or other integration dependencies installed.
