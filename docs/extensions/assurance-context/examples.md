---
id: EXT-ASSURANCE-CONTEXT-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example assurance-context/v1 payloads.
---

# `assurance-context/v1` examples

## Git merge-base audit

```json
{
  "extensions": {
    "assurance-context/v1": {
      "base": {
        "identity": "0123456789abcdef0123456789abcdef01234567",
        "ref": "master",
        "relation": "merge-base",
        "derivation_ref": "git merge-base origin/master aabbccddeeff00112233445566778899aabbccdd",
        "trial_merge": "clean"
      }
    }
  }
}
```

The sha is the attested immutable identity. `master` is only a mutable display name; the kernel neither resolves it nor checks the derivation command.

## Non-Git opaque audit base

```json
{
  "extensions": {
    "assurance-context/v1": {
      "base": {
        "identity": "release-snapshot:sha256:7d0f5b8f9d6a",
        "ref": "current-certified-snapshot",
        "relation": "compatibility-baseline",
        "derivation_ref": "artifact://audit-inputs/snapshot-2048"
      }
    }
  }
}
```

No Git vocabulary is required. The producer defines the opaque immutable identity and the consumer may store, display, and compare it without assigning cross-adapter meaning.
