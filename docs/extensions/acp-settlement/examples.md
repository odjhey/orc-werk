---
id: EXT-ACP-SETTLEMENT-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example acp-settlement/v1 diagnostics payload.
---

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

The sibling extension records why the ACP adapter considered the outstanding result unobservable. A running observation suppressed by post-result activity instead uses:

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
