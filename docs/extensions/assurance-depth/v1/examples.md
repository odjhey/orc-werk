---
id: EXT-ASSURANCE-DEPTH-V1-EXAMPLES
type: example
status: draft
authority: informative
version: 1
description: assurance-depth/v1 examples across verdicts and depths.
---

# `assurance-depth/v1` examples

**Status: draft proposal** (see `EXT-ASSURANCE-DEPTH-V1`).

## Accepted after exercising the real surface

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:258", "file:.verify/258-cli-session.log"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "live",
      "surface": "orc CLI, scratch journal, resolve affordances driven end to end",
      "derivation_ref": "file:.verify/258-cli-session.log"
    },
    "assurance-context/v1": {
      "base": {"identity": "3151a35d0d4f0b8f2b3d3e1c9c0a7c6b5a4f3e2d", "ref": "master", "relation": "merge-base"}
    }
  }
}
```

The verify seat ran the shipped command surface itself and watched it behave. The three extensions answer three independent questions: how deeply (`assurance-depth/v1`), against what base (`assurance-context/v1`), and — had there been any — what was found (`review-findings/v1`). None of them alters `verdict`.

## Accepted on tests only

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:259"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "test",
      "derivation_ref": "bash scripts/check.sh @ 3efa9b3"
    }
  }
}
```

Canonically identical to the previous example: both are `accepted`. A policy with a `live` floor for behavior-changing work may treat this one as insufficient for *its* purposes; the kernel does not.

## Rejected after a live check found the defect

```json
{
  "verdict": "rejected",
  "evidence_refs": ["gh-pr:244", "file:.verify/244-repro.log"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "live",
      "surface": "orc dispatch against a run whose candidate identification returned null"
    },
    "review-findings/v1": {
      "findings": ["dispatch raises instead of resting at EXECUTING when FX-IDENTIFY-CANDIDATE returns no subject"]
    }
  }
}
```

Depth is `live` even though the verdict is `rejected`: the verifier exercised the behavior and it was wrong. "Failed" is the canonical verdict's job, not a depth value.

## Static inspection is the ceiling for documentation work

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:99"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "static",
      "surface": "docs diff + python3 scripts/docs_check.py",
      "derivation_ref": "python3 scripts/docs_check.py @ 348c010"
    }
  }
}
```

For a documentation-only candidate, `static` is an honest and complete depth. Whether it satisfies a given policy floor is that policy's declaration.

## Inconclusive: verifier blocked

```json
{
  "verdict": "inconclusive",
  "evidence_refs": ["file:.verify/230-env-failure.log"]
}
```

The environment prevented evaluation. No `assurance-depth/v1` payload is recorded because no method completed; the payload MUST NOT be used to say "blocked". (Whether the Work continues after `inconclusive` is decided by the assurance budget, `ADR-0006`/`INV-021`, not by this extension.)
