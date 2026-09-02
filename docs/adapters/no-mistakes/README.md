---
id: ADAPTER-NO-MISTAKES
type: adapter
status: superseded
authority: informative
description: no-mistakes assurance adapter (TASK-M2-001).
---

> **Superseded** (operator ruling ADR-0005, issue #214). The no-mistakes `AssurancePort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/adapters/command/README.md` (`ADAPTER-COMMAND`) for the push-shaped command assurance adapter and `docs/scenarios/SCN-015-command-assurance.md` (issue #194) for its scenario. Retained as historical reference only.

# no-mistakes adapter

`no-mistakes` is a candidate assurance provider (an operator's local
automated code-review/gate pipeline), not an Orc Werk core dependency.

`NoMistakesAssurance` (`src/orc_werk/adapters/no_mistakes/assurance.py`,
`TASK-M2-001`) implements `PORT-ASSURANCE` as a **read-only judge** of the
exact observed candidate: it requests a real `no-mistakes` pipeline run
against the current `repo_path`, never lets it fix findings or push
(`--yes` is never passed, `axi respond`/`axi sync` are never called), and
derives its own canonical `accepted`/`rejected`/`inconclusive` verdict from
what it observes.

Where `no-mistakes` exposes structured, attributable code-review findings
(a parked review gate), the adapter additionally produces the
`review-findings/v1` extension (`CAP-ASSURE-STRUCTURED-FINDINGS`). That
extension is not required for generic assurance and does not make
`no-mistakes` the owner of Orc Werk's review-finding schema.

See:

- [Mapping](mapping.md) -- full provider-to-port mapping, verdict table,
  judge-only ruling, limitations.
- [Capabilities](capabilities.md)
- [Conformance](conformance.md)
- `EXT-REVIEW-FINDINGS-V1`
- `docs/delivery/task-cards/TASK-M2-001-no-mistakes-assurance.md`
