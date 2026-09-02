---
id: ADAPTER-NO-MISTAKES-CAPABILITIES
type: adapter-capabilities
status: superseded
authority: informative
description: no-mistakes assurance capabilities (TASK-M2-001).
---

> **Superseded** (operator ruling ADR-0005, issue #214). The no-mistakes `AssurancePort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/adapters/command/README.md` (`ADAPTER-COMMAND`) for the push-shaped command assurance adapter and `docs/scenarios/SCN-015-command-assurance.md` (issue #194) for its scenario. Retained as historical reference only.

# no-mistakes capabilities

`NoMistakesAssurance` advertises, unconditionally:

- `CAP-ASSURE-CANDIDATE-BOUND` -- `request()` binds `candidate.fingerprint`
  durably (into `assurance_id` itself) at request time; every settled
  observation reports exactly that fingerprint.
- `CAP-ASSURE-STRUCTURED-VERDICT` -- `accepted`/`rejected`/`inconclusive`
  are structurally distinct code paths, never derived from parsing free
  text.
- `CAP-ASSURE-STRUCTURED-FINDINGS`, with exact extension support for
  `review-findings/v1` -- produced whenever a parked review gate has
  findings to map; correctly empty (never fabricated) otherwise.

**Never advertised** (withheld unconditionally, `CONTRACT-CAPABILITIES`
capability-durability rule):

- `CAP-ASSURE-MAY-MUTATE-CANDIDATE` -- the judge-only ruling means this
  adapter never lets `no-mistakes` create fix commits or push, so it
  never mutates the candidate it was asked to assure. Constructing an
  instance that requests this capability raises `ValueError` at
  construction time.

All four claims are proven by the real, stub-subprocess-driven conformance
and unit suites (see `conformance.md`) -- none are aspirational.
