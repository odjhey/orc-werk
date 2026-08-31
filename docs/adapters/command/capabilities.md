---
id: ADAPTER-COMMAND-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: CommandAssurance capability claims and deliberate withholding.
---

# command assurance capabilities

Advertised unconditionally:

- `CAP-ASSURE-CANDIDATE-BOUND`: `request()` binds the candidate fingerprint
  into `assurance_id`; settlement reports that exact value.
- `CAP-ASSURE-STRUCTURED-VERDICT`: the explicit process-termination table maps
  clean exit 0, clean exit 1, and every other termination to distinct canonical
  verdict paths.

Withheld unconditionally under the `CONTRACT-CAPABILITIES` durability rule:

- `CAP-ASSURE-MAY-MUTATE-CANDIDATE`: the script contract is judge-only.
  Construction cannot opt into this capability.
- `CAP-ASSURE-STRUCTURED-FINDINGS`: arbitrary operator scripts cannot be
  vouched for as producers of `EXT-REVIEW-FINDINGS-V1-SCHEMA`. Even when
  `review-findings/v1` passes the required-field floor and is transported
  opaquely, `CONF-EXT-005` and `EXT-004` forbid claiming stronger semantic
  support than the adapter proves. Construction cannot opt into this
  capability.
