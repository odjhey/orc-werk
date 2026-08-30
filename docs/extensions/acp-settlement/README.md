---
id: EXT-ACP-SETTLEMENT-V1
type: extension
status: current
authority: normative
version: 1
description: ACP adapter-local diagnostics for unobservability-determined failed settlements.
---

# `acp-settlement/v1`

`acp-settlement/v1` is an optional adapter-local extension carrying the ACP evidence behind an unobservability-determined failed settlement. It keeps provider diagnostics separate from `execution-session/v1` session provenance.

The ACP adapter emits it only for such settlements, as a sibling key in the settled observation's `extensions`. Consumers may ignore it.

Per `EXT-003`, it never overrides canonical state or outcome. Per `EXT-007`, it is never the sole carrier of canonical information.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `PORT-EXEC-002`
- `EXT-EXECUTION-SESSION-V1`
