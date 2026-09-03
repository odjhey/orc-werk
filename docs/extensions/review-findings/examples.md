---
id: EXT-REVIEW-FINDINGS-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example review-findings/v1 payloads.
---

# `review-findings/v1` examples

## Blocking correctness finding

```json
{
  "extensions": {
    "review-findings/v1": {
      "findings": [
        {
          "id": "finding-17",
          "severity": "high",
          "disposition": "blocking",
          "category": "correctness",
          "confidence": "high",
          "status": "open",
          "location": {
            "path": "src/cache.py",
            "start_line": 87,
            "end_line": 96
          },
          "evidence": [
            {
              "kind": "test",
              "summary": "Concurrent invalidation reproduces a stale read.",
              "ref": "test_cache_invalidation_race"
            }
          ]
        }
      ]
    }
  }
}
```

The enclosing assurance observation might have canonical verdict `rejected`.

## High-severity non-blocking accepted debt

```json
{
  "id": "finding-22",
  "severity": "high",
  "disposition": "non-blocking",
  "category": "maintainability",
  "confidence": "high",
  "status": "accepted",
  "evidence": [
    {
      "kind": "reference",
      "summary": "The debt is tracked separately and accepted for this delivery.",
      "ref": "issue:123"
    }
  ]
}
```

## Low-severity but blocking contract mismatch

```json
{
  "id": "finding-31",
  "severity": "low",
  "disposition": "blocking",
  "category": "contract",
  "confidence": "high",
  "status": "open",
  "location": {
    "path": "schema/output.json"
  },
  "evidence": [
    {
      "kind": "contract",
      "summary": "Required field `request_id` is missing.",
      "ref": "CONTRACT-OUTPUT-17"
    }
  ]
}
```

These examples intentionally demonstrate that severity and disposition are independent.

## Unstructured (string) entries — `orc record --finding` shape

This is the shape `orc record --verdict --finding TEXT` actually emits
(`src/orc_werk/cli/main.py`, `cmd_record`) and what the entire live ledger's
`review-findings/v1` payloads carry as of issue #249's amendment. Each
`--finding` occurrence becomes one plain-string entry; there is no
structured object involved.

```json
{
  "extensions": {
    "review-findings/v1": {
      "findings": [
        "looks good",
        "nit: consider renaming this variable for clarity"
      ]
    }
  }
}
```

## Mixed entries

A single `findings` array MAY combine unstructured and structured entries;
both forms are independently valid per entry.

```json
{
  "extensions": {
    "review-findings/v1": {
      "findings": [
        "looks good overall",
        {
          "id": "finding-9",
          "severity": "medium",
          "disposition": "non-blocking",
          "category": "style",
          "confidence": "medium",
          "status": "open",
          "evidence": [
            {
              "kind": "explanation",
              "summary": "Naming is inconsistent with the surrounding module."
            }
          ]
        }
      ]
    }
  }
}
```
