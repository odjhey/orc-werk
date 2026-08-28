---
id: EXT-EXECUTION-SESSION-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for execution-session/v1.
---

# `execution-session/v1` schema

The extension payload has this conceptual shape:

```text
ExecutionSessionV1 {
    provider: string            # opaque, provider-defined
    native_session_id: string   # opaque, provider-defined
    resume?: ResumeProvenance
    transcript_ref?: string     # opaque reference, ref-only — see semantics.md
    profile?: SessionProfile
}

ResumeProvenance {
    strength: "exact" | "best-effort"
    ref: string                 # opaque reference the adapter's resume operation consumes
}

SessionProfile {
    model?: string               # opaque, provider-defined
    effort?: string               # opaque, provider-defined
    permission_mode?: string      # opaque, provider-defined
    fast?: boolean
}
```

Canonical transport example:

```json
{
  "extensions": {
    "execution-session/v1": {
      "provider": "opaque-provider-id",
      "native_session_id": "opaque-session-id",
      "resume": {
        "strength": "exact",
        "ref": "opaque-resume-ref"
      },
      "transcript_ref": "opaque-transcript-ref",
      "profile": {
        "model": "opaque-model-id",
        "effort": "opaque-effort-level",
        "permission_mode": "opaque-permission-mode",
        "fast": false
      }
    }
  }
}
```

This transports on the existing `extensions` slots already defined by `PORT-EXEC-002`'s execution observation and `PORT-JOURNAL-ENVELOPE`'s journal record envelope; no core or envelope field changes (`TASK-M1-004`'s "must not change" constraint).

## Required fields

The payload MUST contain:

- `provider`;
- `native_session_id`.

These two fields identify the session; everything else is present only when the adapter has it and chooses to preserve it.

`resume`, `transcript_ref`, and `profile` are each independently optional. A provider that cannot produce one of them simply omits it (`EXT-005`); omission is not an error.

## Field rules

### `provider`, `native_session_id`

Opaque strings. See the opaque-strings rule below. `native_session_id` MUST be stable for the life of the underlying provider-native session — the same session yields the same `native_session_id` across repeated `inspect` calls and across journal replay.

### `resume`

When present, `resume.strength` MUST be exactly `"exact"` or `"best-effort"`; no other value is valid. `resume.ref` MUST be an opaque reference the adapter's own `resume` operation (`PORT-EXEC-005`) can consume — it is not required to be human-readable or to have any meaning outside that adapter.

`resume.strength` corresponds to, but is a payload-level field distinct from, the `capability` value a caller supplies on a `PORT-EXEC-005` resume request. The explicit mapping: `"exact"` corresponds to `CAP-EXEC-RESUME-EXACT`, and `"best-effort"` corresponds to `CAP-EXEC-RESUME-BEST-EFFORT`. The payload vocabulary and the capability identifiers remain distinct namespaces — they are checked against each other, never merged. See [Semantics](semantics.md) for how that check works.

### `transcript_ref`

When present, an opaque reference only. It MUST NOT carry transcript content. See the ref-only rule below.

### `profile`

When present, every field inside it (`model`, `effort`, `permission_mode`) is an independently optional opaque string, and `fast` is an independently optional boolean. Any subset may be present; absence of a field means the adapter does not preserve that dimension of the profile, not that the dimension had a default value.

## Opaque-strings rule (`INV-014`)

`provider`, `native_session_id`, and every string field inside `profile` are free-form, provider-defined strings. This schema deliberately does not enumerate a closed set of valid providers or model identifiers, and never will without a version bump that is itself provider vocabulary creeping into a shared contract — which `INV-014` forbids outright. Consumers:

- MUST treat these fields as uninterpreted values for storage, display, transport, and equality comparison;
- MUST NOT branch generic core or cross-provider policy behavior on their specific value;
- MAY have adapter-local or policy-local code that interprets a known value for a specific provider, per `EXT-002` ("policy or extension-aware application code MAY interpret a known extension").

## Ref-only rule (`transcript_ref` and artifact provenance)

`transcript_ref` is a reference, never a content payload. Per `PORT-JOURNAL`'s "not an artifact store" boundary, transcript (or other artifact) content never rides this extension, the enclosing execution observation, or the journal envelope. A consumer that needs the transcript resolves the reference against the provider-specific store it names; that store and its access contract are out of scope for this schema and for every core Orc Werk contract.

## Dispatcher/watchtower provenance is out of scope

`dispatcher` (watchtower/preset/policy attribution: which watchtower dispatched this, which preset/policy version, policy hash) is explicitly not a field of `execution-session/v1`. It is orchestration provenance, not session provenance, and is recorded in `CONTRACT-DURABILITY`'s ownership matrix as a planned, separate, currently unregistered extension.

This exclusion binds producers and validators, not transports: an `execution-session/v1` producer MUST NOT emit a `dispatcher` field, and a validator MAY reject a payload containing one. A component that promises lossless extension round-trip still preserves an unknown `dispatcher` key unchanged per `EXT-005` and `CONF-EXT-003` — transport-level tolerance of unknown keys is not producer-level permission to emit them.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## CONF-EXT obligations

- `CONF-EXT-001`: the payload contains only JSON-compatible values and round-trips without implementation-language-specific objects.
- `CONF-EXT-002`: a consumer that does not understand `execution-session/v1` still processes the enclosing execution observation or journal record without change to canonical meaning.
- `CONF-EXT-003`: a component that advertises lossless extension round-trip (for example, `PORT-JOURNAL` persisting an execution observation's `extensions`) preserves this payload unchanged, including unknown future fields within it, per `EXT-005`.
- `CONF-EXT-004`: nothing in this payload can override canonical execution outcome, work identity, candidate identity, or decision identity, per `EXT-003`.
- `CONF-EXT-005` (capability honesty): a provider advertising `CAP-EXEC-RESUME-EXACT` produces, for every execution it claims exact resume for, an `execution-session/v1` payload with `resume.strength = "exact"` and a `resume.ref` that its own `PORT-EXEC-005` resume operation can consume. A provider that cannot durably persist that provenance does not advertise `CAP-EXEC-RESUME-EXACT` — this is also the `CONTRACT-CAPABILITIES` capability-durability rule applied to this specific extension.

## Versioning

Adding a new required field, changing an existing field's meaning, or adding the `dispatcher` block into this schema requires a new extension version (`execution-session/v2`) rather than a silent change to `v1`.
