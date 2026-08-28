---
id: ADAPTER-NO-MISTAKES-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: no-mistakes assurance capabilities (TASK-M2-001).
---

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
