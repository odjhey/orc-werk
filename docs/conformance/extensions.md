---
id: CONFORMANCE-EXTENSIONS
type: contract
status: current
authority: normative
description: Provider-independent conformance requirements for versioned extensions.
---

# Extension conformance

These requirements apply to any component that advertises or transports Orc Werk extensions.

## CONF-EXT-001 — Portable payload

Extension payloads contain only JSON-compatible values and can round-trip without implementation-language-specific objects.

## CONF-EXT-002 — Unknown-extension safety

A consumer that does not understand a supplied extension still processes the canonical object without changing its canonical meaning.

## CONF-EXT-003 — Lossless preservation when promised

A component that advertises lossless extension round-trip preserves unknown extension identifiers and payloads byte-semantically/canonically unchanged according to the published serialization contract.

## CONF-EXT-004 — Canonical fields win

An extension that contains data resembling a canonical field cannot override the canonical value. Conflicting extension data is ignored for canonical behavior or rejected according to policy; it is never treated as authoritative core state.

## CONF-EXT-005 — Capability honesty

A provider advertising `CAP-ASSURE-STRUCTURED-FINDINGS` for `review-findings/v1` produces payloads conforming to `EXT-REVIEW-FINDINGS-V1-SCHEMA`. A provider that cannot do so does not advertise that support.

## CONF-EXT-006 — Core ignorance

Core reducer/state-machine tests prove that changing an extension payload while keeping canonical facts identical does not change generic core transitions or decisions under a policy that does not explicitly consume that extension.

## CONF-EXT-007 — Assurance audit-base opacity

A component transporting `assurance-context/v1` preserves the verifier-attested base canonically unchanged through `FACT-ASSURE-SETTLED.extensions` and journal round-trip. The base never changes canonical projection, verdict binding, transitions, or Decisions when present, absent, or changed. See `SCN-012`.
