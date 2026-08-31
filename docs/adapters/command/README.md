---
id: ADAPTER-COMMAND
type: adapter
status: current
authority: informative
description: Generic command assurance adapter for operator-authored in-repository verifier scripts.
---

# command assurance adapter

`CommandAssurance` implements `PORT-ASSURANCE` by running an operator-authored,
PR-reviewed script from the adopter repository as the verify seat. The script
receives the bound candidate and assurance requirements as versioned JSON on
standard input; its termination status supplies the verdict.

This is an adapter-local mapping. **`PORT-ASSURANCE` is confirmed unchanged**:
its existing opaque requirements, adapter-owned assurance identity, lifecycle,
verdict, evidence, and extension channels are sufficient.

See:

- [Mapping](mapping.md)
- [Capabilities](capabilities.md)
- [Conformance](conformance.md)
- `SCN-015`
