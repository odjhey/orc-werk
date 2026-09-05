"""Idempotency-key derivation (INV-020).

Keys are deterministically derived from durable canonical state only --
never from randomness, wall-clock time, or process/runtime identity -- so
that journal replay (PORT-JOURNAL-005) reproduces identical keys.

Key form per effect, verbatim from INV-020:
  - FX-CREATE-WORK: (delivery_run_id, effect_id) -- precedes any attempt,
    creates all Work records for one plan; v0 permits exactly one plan
    creation per DeliveryRun.
  - FX-CLAIM-WORK: the reduced form (delivery_run_id, work_id, effect_id)
    with NO attempt_number component -- a claim is once per Work lineage,
    held by its claimant across all retry attempts and never re-acquired
    on retry, analogous to FX-CREATE-WORK's reduced form.
  - FX-START-EXECUTION, FX-SEND-EXECUTION, FX-CANCEL-EXECUTION,
    FX-IDENTIFY-CANDIDATE, FX-COMPLETE-WORK, FX-BLOCK-WORK: the standard
    tuple (delivery_run_id, work_id, attempt_number, effect_id).
  - FX-START-ASSURANCE: the standard tuple plus candidate_fingerprint,
    plus the INV-021 `assurance_number` component when that number is
    greater than 1. The FIRST assurance of a candidate within an execution
    attempt keeps the pre-INV-021 form (no `assurance_number` component),
    so every journal written before assurance re-request existed
    (`ADR-0006`) replays under identical keys:

        assurance 1: <run>|<work>|<attempt>|FX-START-ASSURANCE|<fingerprint>
        assurance n: <run>|<work>|<attempt>|FX-START-ASSURANCE|<fingerprint>|<n>
"""

from __future__ import annotations

from orc_werk.core.effects import ALL_EFFECT_IDS, FX_CLAIM_WORK, FX_CREATE_WORK, FX_START_ASSURANCE

_SEP = "|"


def _join(*parts: object) -> str:
    return _SEP.join(str(part) for part in parts)


def idempotency_key(
    effect_id: str,
    *,
    delivery_run_id: str,
    work_id: str | None = None,
    attempt_number: int | None = None,
    candidate_fingerprint: str | None = None,
    assurance_number: int = 1,
) -> str:
    """Derive the INV-020 idempotency key for one effect instance."""
    if effect_id not in ALL_EFFECT_IDS:
        raise ValueError(f"unknown effect id: {effect_id!r}")

    if effect_id == FX_CREATE_WORK:
        return _join(delivery_run_id, effect_id)

    if effect_id == FX_CLAIM_WORK:
        # INV-020: FX-CLAIM-WORK is once per Work lineage -- keyed on the
        # reduced form (delivery_run_id, work_id, effect_id), with no
        # attempt_number component, mirroring FX-CREATE-WORK's reduced form.
        if work_id is None:
            raise ValueError("FX-CLAIM-WORK requires work_id for the reduced form (INV-020)")
        return _join(delivery_run_id, work_id, effect_id)

    if work_id is None or attempt_number is None:
        raise ValueError(
            f"{effect_id} requires work_id and attempt_number for the standard tuple (INV-020)"
        )

    standard = (delivery_run_id, work_id, attempt_number, effect_id)

    if effect_id == FX_START_ASSURANCE:
        if not candidate_fingerprint:
            raise ValueError("FX-START-ASSURANCE requires candidate_fingerprint (INV-020)")
        if isinstance(assurance_number, bool) or not isinstance(assurance_number, int) or assurance_number < 1:
            raise ValueError("FX-START-ASSURANCE assurance_number must be a positive integer (INV-021)")
        if assurance_number == 1:
            # INV-020 as amended by ADR-0006: the first assurance keeps the
            # pre-INV-021 key form verbatim, so pre-decision journals
            # replay under identical keys.
            return _join(*standard, candidate_fingerprint)
        return _join(*standard, candidate_fingerprint, assurance_number)

    return _join(*standard)
