"""Pure Orc Werk domain and orchestration semantics.

`orc_werk.core` is stdlib-only and integration-free (P-006, ADR-0001,
ARCH-REPOSITORY-STRUCTURE): canonical identities/models, Fact/Decision/
Effect value types, the delivery state-machine reducer (`STATE-DELIVERY`),
the deterministic v0 policy, retry-budget/idempotency-key derivation
(INV-018/INV-019/INV-020), and portable serialization to/from
`PORT-JOURNAL-ENVELOPE`. Canonical behavior is defined by the normative
documentation under `docs/`, not by this Python implementation.
"""

from orc_werk.core import (
    decisions,
    effects,
    errors,
    facts,
    idempotency,
    models,
    policy,
    portable,
    reducer,
    serialization,
    state,
)
from orc_werk.core.decisions import Decision
from orc_werk.core.effects import Effect
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import Fact
from orc_werk.core.models import AssuranceRun, Candidate, DeliveryRun, Execution, Work
from orc_werk.core.policy import PolicyOutcome, decide
from orc_werk.core.reducer import apply_fact, reduce
from orc_werk.core.state import DeliveryProjection, WorkProjection

__all__ = [
    "decisions",
    "effects",
    "errors",
    "facts",
    "idempotency",
    "models",
    "policy",
    "portable",
    "reducer",
    "serialization",
    "state",
    "Decision",
    "Effect",
    "CoreError",
    "Fact",
    "AssuranceRun",
    "Candidate",
    "DeliveryRun",
    "Execution",
    "Work",
    "PolicyOutcome",
    "decide",
    "apply_fact",
    "reduce",
    "DeliveryProjection",
    "WorkProjection",
]
