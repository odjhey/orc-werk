---
id: ARCH-REPOSITORY-STRUCTURE
type: architecture
status: current
authority: normative
description: Python reference package layout and dependency rules for Orc Werk.
---

# Repository structure and dependency rules

This document defines the initial Python reference-implementation layout. It constrains source dependencies; it does not make Python part of Orc Werk's product contract. See `ADR-0003` and `P-009`.

## Target layout

```text
src/
└── orc_werk/
    ├── __init__.py
    ├── core/
    │   └── __init__.py
    ├── ports/
    │   └── __init__.py
    ├── app/
    │   └── __init__.py
    ├── adapters/
    │   ├── __init__.py
    │   ├── memory/
    │   │   └── __init__.py
    │   └── scripted/
    │       └── __init__.py
    └── cli/
        └── __init__.py

tests/
├── core/
├── conformance/
└── scenarios/
```

The directories are intentionally coarse during M0. Split modules only when implementation pressure justifies it; do not create a deep framework before the golden scenarios require one.

## Dependency direction

```text
core
  ↓ nothing outside core + Python stdlib

ports
  ↓ core canonical types

app
  ↓ core + ports

adapters
  ↓ ports + core canonical types + provider-specific dependencies

cli
  ↓ app + composition/configuration + selected adapters
```

The following dependencies are forbidden:

```text
core -> ports
core -> app
core -> adapters
core -> cli
core -> Beads/zxro/Git/command/provider SDKs
ports -> adapters
app -> concrete provider internals
```

## Package responsibilities

### `orc_werk.core`

Owns canonical models, facts, decisions, effects, state transitions, deterministic policy mechanics, invariant validation, and portable serialization rules that are part of the reference implementation.

M0 requirement: standard-library-only and fully testable without integration dependencies.

### `orc_werk.ports`

Defines language-level interfaces corresponding to the normative port documents. Port types may depend on canonical core types but must not import provider concepts.

### `orc_werk.app`

Coordinates the pure core with port implementations. It interprets core effects, invokes ports, normalizes resulting observations into canonical facts, and persists/replays the orchestration journal.

The application layer may orchestrate I/O but must not redefine domain semantics.

### `orc_werk.adapters`

Contains provider translations. M0 starts with dependency-free `memory` and `scripted` adapters. Real adapters for Beads, zxro, Git, command assurance, CI, or future systems are added only after the pure contracts are proven. (The `acp` `ExecutionPort` and no-mistakes `AssurancePort` adapters that once lived here were removed in 0.5.0, pre-1.0, no backward compatibility — `ADR-0005`; see `docs/adapters/acp/README.md` and `docs/adapters/no-mistakes/README.md` for the superseded, historical-reference-only docs.)

Provider-native vocabulary stays inside this layer and `docs/adapters/`.

### `orc_werk.cli`

Owns the user-facing command surface and composition bootstrap. It may choose configured adapters and construct application services, but it should read canonical projections rather than directly joining provider-native state.

## Test layout

### `tests/core/`

Pure reducer, policy, invariant, serialization, and state-machine tests. These tests MUST run with no provider installations.

### `tests/conformance/`

Reusable port conformance suites. Memory/scripted adapters run them first; every future real adapter must run the applicable same suite.

### `tests/scenarios/`

Executable forms of `SCN-001` through `SCN-006` and future golden scenarios. Scenarios should exercise the application surface with fake/scripted providers rather than reaching through to implementation details.

## Portability rules

Canonical persisted and interchange shapes must be expressible using portable explicit data: strings, integers, booleans, null, lists, and string-keyed maps with explicit type/schema discriminators where required.

Do not make these canonical:

- pickle or marshal payloads;
- Python import paths or class names;
- exception objects or tracebacks;
- arbitrary dataclass/object serialization;
- callable references;
- object identity or memory addresses.

A future Go implementation should be able to read/replay the canonical journal and implement the same ports/scenarios without importing Python artifacts.

## Idempotency doctrine (informative)

The invariants above compose into one operating stance: **replay is the
universal verb, and the durable record — never anyone's memory — decides
whether something already happened.** Effects are addressable by derived keys
(`INV-020`), so "did this happen?" is a lookup; the app reconciles by key
before dispatching; adapters make each operation idempotent at the provider
boundary from durable state. The boundary is sharp: idempotent *within* an
attempt, deliberately novel *across* attempts (`INV-004` — a retry is a new
identity, never a re-run). Idempotent never means overwrite: replaying the
same operation converges to the same outcome; a conflicting operation is
`ERR-CONFLICT`, not a silent replacement. Bounded retries plus this doctrine
are the safety mechanism — they are why unclassified failures degrade to a
visible, capped, replayable block rather than requiring retry-classification.
Operator-facing consequence (`SCN-007`): re-running the same dispatch is
always safe and is simultaneously the resume, poll, and crash-recovery verb.

## Self-healing boundary

Self-healing in the Python phase must be designed as portable orchestration behavior:

```text
restart
  -> replay durable canonical facts/decisions/effect records
  -> reconstruct projection
  -> reconcile incomplete/uncertain effects with providers
  -> apply idempotent retry, fallback, replan, or escalation policy
  -> continue
```

Python makes these experiments inexpensive; Python-specific introspection is not a substitute for this explicit recovery contract.
