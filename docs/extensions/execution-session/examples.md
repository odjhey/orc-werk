---
id: EXT-EXECUTION-SESSION-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example execution-session/v1 payloads.
---

# `execution-session/v1` examples

## Exact-resume-capable session, full provenance

```json
{
  "extensions": {
    "execution-session/v1": {
      "provider": "opaque-provider-a",
      "native_session_id": "opaque-session-9f2c",
      "resume": {
        "strength": "exact",
        "ref": "opaque-resume-ref-9f2c"
      },
      "transcript_ref": "opaque-transcript-ref-9f2c",
      "profile": {
        "model": "opaque-model-x",
        "effort": "opaque-effort-high",
        "permission_mode": "opaque-mode-auto",
        "fast": false
      }
    }
  }
}
```

An adapter advertising `CAP-EXEC-RESUME-EXACT` for this session persisted exactly this shape (at minimum `resume.strength = "exact"` and a resolvable `resume.ref`) before it may make that claim.

## Best-effort resume only, no transcript

```json
{
  "provider": "opaque-provider-b",
  "native_session_id": "opaque-session-11ab",
  "resume": {
    "strength": "best-effort",
    "ref": "opaque-resume-ref-11ab"
  }
}
```

`transcript_ref` and `profile` are both omitted — the adapter does not preserve either, which is valid per `EXT-005`. A resume request for `CAP-EXEC-RESUME-EXACT` against this session MUST fail per `INV-013`; only `CAP-EXEC-RESUME-BEST-EFFORT` is honest here.

## Minimal identification only, no resume support

```json
{
  "provider": "opaque-provider-c",
  "native_session_id": "opaque-session-55zz"
}
```

Useful for operator inspection/debugging even when the adapter offers neither `CAP-EXEC-RESUME-BEST-EFFORT` nor `CAP-EXEC-RESUME-EXACT` for this provider.

## Producer violation: dispatcher field present

```json
{
  "provider": "opaque-provider-a",
  "native_session_id": "opaque-session-9f2c",
  "dispatcher": {
    "watchtower": "opaque-watchtower-id"
  }
}
```

A producer MUST NOT emit this — `dispatcher` belongs to the planned, separate provenance extension, not this schema — and a validator MAY reject it. A component promising lossless round-trip nevertheless preserves the unknown `dispatcher` key unchanged per `EXT-005`/`CONF-EXT-003`.
