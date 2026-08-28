# Findings

## Issue #93: requested model provenance

Part 2 was not implemented. `EXT-EXECUTION-SESSION-V1-SCHEMA` defines the
`SessionProfile` producer fields as `model`, `effort`, `permission_mode`, and
`fast`; it does not permit an adapter producer to add `requested_model` to the
v1 profile. Adding that field requires a canonical extension-schema change (or
a new extension version), which is outside this task's allowed documentation
scope. Part 1 still prevents silent substitution by validating and resolving the
requested model before submission and failing closed if the resolved model
cannot be pinned.
