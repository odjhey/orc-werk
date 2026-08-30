---
id: EXT-ACP-SETTLEMENT-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for acp-settlement/v1 diagnostics.
---

# `acp-settlement/v1` schema

```text
AcpSettlementV1 {
    unobservability: UnobservabilityEvidence
}

UnobservabilityEvidence {
    lastAgentExitCode?: opaque portable JSON
    lastAgentExitSignal?: opaque portable JSON
    status?: opaque portable JSON
    pidAlive?: opaque portable JSON
    exitCode?: opaque portable JSON
    signal?: opaque portable JSON
}
```

`unobservability` is required when the extension is emitted. Every evidence field is optional and opaque; values MUST be portable JSON-compatible data (`EXT-006`). Absence means only that the adapter did not observe that field.

The payload travels under `extensions["acp-settlement/v1"]`. It does not add or alter canonical fields. Unknown consumers may ignore it, and transports promising lossless extension handling preserve it unchanged.
