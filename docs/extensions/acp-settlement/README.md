---
id: EXT-ACP-SETTLEMENT-V1
type: extension
status: superseded
authority: normative
version: 1
description: ACP adapter-local diagnostics for settlement and suppression decisions.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` and `docs/adapters/acp/README.md`. Retained as historical reference only.

# `acp-settlement/v1`

`acp-settlement/v1` is an optional adapter-local extension carrying ACP evidence behind an unobservability-determined failed settlement or a terminal-quiescence suppression that leaves an observation running. It keeps provider diagnostics separate from `execution-session/v1` session provenance.

The ACP adapter emits it as a sibling key in the observation's `extensions`. Consumers may ignore it.

Per `EXT-003`, it never overrides canonical state or outcome. Per `EXT-007`, it is never the sole carrier of canonical information.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `PORT-EXEC-002`
- `EXT-EXECUTION-SESSION-V1`
