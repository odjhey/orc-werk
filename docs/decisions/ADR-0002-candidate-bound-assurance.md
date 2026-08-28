---
id: ADR-0002
type: decision
status: current
authority: informative
description: Bind all assurance evidence to an exact canonical candidate fingerprint.
---

# ADR-0002 — Candidate-bound assurance

## Context

Software delivery frequently changes a candidate after review, testing, rebasing, auto-fixing, or integration. Evidence from an old subject can otherwise be accidentally treated as current.

## Decision

Every settled AssuranceRun and Evidence record names the exact canonical Candidate fingerprint evaluated. Candidate changes invalidate non-matching assurance.

## Consequences

Assurance providers that cannot prove subject identity cannot return canonical `accepted`; they must be inconclusive or unsupported according to policy.

Related: `INV-005` through `INV-010`.
