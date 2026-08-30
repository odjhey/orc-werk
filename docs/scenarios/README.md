---
id: SCENARIOS-INDEX
type: index
status: current
authority: normative
description: Golden end-to-end executable specifications.
---

# Golden scenarios

The pure core must pass these scenarios with scripted/in-memory adapters before real provider integration begins.

1. [`SCN-001`](SCN-001-happy-path.md) happy path
2. [`SCN-002`](SCN-002-assurance-retry.md) assurance rejection and retry
3. [`SCN-003`](SCN-003-execution-failure.md) execution failure and retry
4. [`SCN-004`](SCN-004-attempt-budget.md) retry budget exhaustion
5. [`SCN-005`](SCN-005-fanin.md) dependency fan-in
6. [`SCN-006`](SCN-006-capability-failure.md) unsupported stronger capability
7. [`SCN-007`](SCN-007-pending-settlement.md) pending execution / operator-recorded settlement
8. [`SCN-008`](SCN-008-replay-budget.md) replay under the run's own retry budget
9. [`SCN-009`](SCN-009-verdict-inheritance.md) verdict inheritance on candidate re-observation
10. [`SCN-010`](SCN-010-abandon-attempt.md) abandoned-attempt recovery
11. [`SCN-011`](SCN-011-cancel-work.md) operator cancellation
12. [`SCN-012`](SCN-012-assurance-audit-base.md) assurance audit base
