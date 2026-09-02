---
id: EXT-ACP-SETTLEMENT-V1-SCHEMA
type: contract
status: superseded
authority: normative
version: 1
description: Portable schema for acp-settlement/v1 diagnostics.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` and `docs/adapters/acp/README.md`. Retained as historical reference only.

# `acp-settlement/v1` schema

```text
AcpSettlementV1 {
    unobservability?: UnobservabilityEvidence
    suppression?: SettlementSuppressionEvidence
}

UnobservabilityEvidence {
    reason?: "worker-vanished-mid-turn"
    prompted?: boolean
    stream_activity_seen?: boolean
    lastAgentExitCode?: opaque portable JSON
    lastAgentExitSignal?: opaque portable JSON
    status?: opaque portable JSON
    pidAlive?: opaque portable JSON
    exitCode?: opaque portable JSON
    signal?: opaque portable JSON
}

SettlementSuppressionEvidence {
    stopReason: string
    resultRecord: integer
    laterRecord: integer
    laterRecordClass: string
}
```

At least one of `unobservability` or `suppression` is required when the extension is emitted; both may appear when post-result activity suppresses a candidate and daemon death is subsequently corroborated. Unobservability evidence fields are optional; absence means only that the adapter did not observe that field. For `reason: "worker-vanished-mid-turn"`, `status` MUST be `"no-session"` and both `prompted` and `stream_activity_seen` MUST be `true`. Other evidence values remain opaque. Suppression fields identify the candidate result's stop reason and one-based stream-record position plus the first later record that was not positively classified as passive bookkeeping. `laterRecordClass` is an adapter-owned portable label such as `agent_message_chunk`, `session/prompt`, `malformed`, or `unknown`.

All values MUST be portable JSON-compatible data (`EXT-006`).

The payload travels under `extensions["acp-settlement/v1"]`. It does not add or alter canonical fields. Unknown consumers may ignore it, and transports promising lossless extension handling preserve it unchanged.
