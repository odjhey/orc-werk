---
id: EXT-ACP-SETTLEMENT-V1-EXAMPLES
type: example
status: superseded
authority: informative
version: 1
description: Example acp-settlement/v1 diagnostics payload.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` and `docs/adapters/acp/README.md`. Retained as historical reference only.

# `acp-settlement/v1` examples

```json
{
  "extensions": {
    "execution-session/v1": {
      "provider": "acpx-pi",
      "native_session_id": "opaque-session-id",
      "resume": {
        "strength": "best-effort",
        "ref": "opaque-session-ref"
      }
    },
    "acp-settlement/v1": {
      "unobservability": {
        "lastAgentExitCode": 137,
        "lastAgentExitSignal": null
      }
    }
  }
}
```

The sibling extension records why the ACP adapter considered the outstanding result unobservable. A vanished worker after substantive turn activity uses:

```json
{
  "extensions": {
    "acp-settlement/v1": {
      "unobservability": {
        "reason": "worker-vanished-mid-turn",
        "status": "no-session",
        "prompted": true,
        "stream_activity_seen": true
      }
    }
  }
}
```

The same `no-session` observation with an empty/no-substantive stream remains running and does not emit this evidence. A running observation suppressed by post-result activity instead uses:

```json
{
  "extensions": {
    "acp-settlement/v1": {
      "suppression": {
        "stopReason": "end_turn",
        "resultRecord": 3,
        "laterRecord": 4,
        "laterRecordClass": "agent_message_chunk"
      }
    }
  }
}
```

The enclosing observation's canonical `state` and `outcome` remain the authority; consumers may ignore either diagnostic payload.
