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

`assurance-depth/v1` is not yet emitted by any orc code path, so no real
`FACT-ASSURE-SETTLED` carries it. The envelope shape below — `verdict`,
`evidence_refs`, and a sibling-extension `extensions` map — is not invented:
it matches a real recorded settlement, `.orc/docs-pstack-assurance-depth/journal.jsonl`
seq 16 (`assurance_id: assure-a49662c47f9b7001`, this extension's own
proposal PR #261, `verdict: accepted`, `evidence_refs: ["gh-pr:261",
"head:578c5f0..."]`, sibling `executor-identity/v1` and `review-findings/v1`
payloads). Every PR number, sha, and `assurance-depth/v1` payload below is a
synthetic placeholder, not a real observation — this repo's discipline is to
never fabricate a recorded observation, so no real merged PR is credited
with a depth it never actually recorded.

## Accepted after exercising the real surface

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:9001", "file:.verify/9001-cli-session.log"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "live",
      "surface": "orc CLI, scratch journal, resolve affordances driven end to end",
      "derivation_ref": "file:.verify/9001-cli-session.log"
    },
    "assurance-context/v1": {
      "base": {"identity": "0123456789abcdef0123456789abcdef01234567", "ref": "master", "relation": "merge-base"}
    }
  }
}
```

The verify seat ran the shipped command surface itself and watched it
behave. Two extensions answer two independent questions here: how deeply
(`assurance-depth/v1`) and against what base (`assurance-context/v1`). A
third — what was found (`review-findings/v1`) — would ride alongside had
the audit surfaced anything to report; none of the three alters `verdict`.

## Accepted on tests only

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:9002"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "test",
      "derivation_ref": "bash scripts/check.sh @ 0000000"
    }
  }
}
```

Canonically identical to the previous example: both are `accepted`. A
policy with a `live` floor for behavior-changing work may treat this one as
insufficient for *its* purposes; the kernel does not.

## Rejected after a live check found the defect

```json
{
  "verdict": "rejected",
  "evidence_refs": ["gh-pr:9003", "file:.verify/9003-repro.log"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "live",
      "surface": "the candidate's CLI entry point, exercised against the exact input path the audit covered"
    },
    "review-findings/v1": {
      "findings": ["the candidate raised instead of producing the documented output for this input"]
    }
  }
}
```

Depth is `live` even though the verdict is `rejected`: the verifier
exercised the behavior and it was wrong. "Failed" is the canonical verdict's
job, not a depth value.

## Static inspection is the ceiling for documentation work

```json
{
  "verdict": "accepted",
  "evidence_refs": ["gh-pr:9004"],
  "extensions": {
    "assurance-depth/v1": {
      "depth": "static",
      "surface": "docs diff + python3 scripts/docs_check.py",
      "derivation_ref": "python3 scripts/docs_check.py @ 0000000"
    }
  }
}
```

For a documentation-only candidate, `static` is an honest and complete
depth. Whether it satisfies a given policy floor is that policy's
declaration.

## Inconclusive: verifier blocked

```json
{
  "verdict": "inconclusive",
  "evidence_refs": ["file:.verify/9005-env-failure.log"]
}
```

The environment prevented evaluation. No `assurance-depth/v1` payload is
recorded because no method completed; the payload MUST NOT be used to say
"blocked". (Whether the Work continues after `inconclusive` is decided by
the assurance budget, `ADR-0006`/`INV-021`, not by this extension.)
