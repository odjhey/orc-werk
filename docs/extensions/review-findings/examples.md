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
