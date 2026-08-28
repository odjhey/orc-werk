"""Idempotency-key derivation (INV-020).

Keys are deterministically derived from durable canonical state only --
never from randomness, wall-clock time, or process/runtime identity -- so
that journal replay (PORT-JOURNAL-005) reproduces identical keys.

Key form per effect, verbatim from INV-020:
  - FX-CREATE-WORK: (delivery_run_id, effect_id) -- precedes any attempt,
    creates all Work records for one plan; v0 permits exactly one plan
    creation per DeliveryRun.
  - FX-CLAIM-WORK, FX-START-EXECUTION, FX-SEND-EXECUTION, FX-CANCEL-EXECUTION,
    FX-IDENTIFY-CANDIDATE, FX-COMPLETE-WORK, FX-BLOCK-WORK: the standard
    tuple (delivery_run_id, work_id, attempt_number, effect_id).
  - FX-START-ASSURANCE: the standard tuple plus candidate_fingerprint.
"""

from __future__ import annotations

from orc_werk.core.effects import ALL_EFFECT_IDS, FX_CREATE_WORK, FX_START_ASSURANCE

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
) -> str:
    """Derive the INV-020 idempotency key for one effect instance."""
    if effect_id not in ALL_EFFECT_IDS:
        raise ValueError(f"unknown effect id: {effect_id!r}")

    if effect_id == FX_CREATE_WORK:
        return _join(delivery_run_id, effect_id)

    if work_id is None or attempt_number is None:
        raise ValueError(
            f"{effect_id} requires work_id and attempt_number for the standard tuple (INV-020)"
        )

    standard = (delivery_run_id, work_id, attempt_number, effect_id)

    if effect_id == FX_START_ASSURANCE:
        if not candidate_fingerprint:
            raise ValueError("FX-START-ASSURANCE requires candidate_fingerprint (INV-020)")
        return _join(*standard, candidate_fingerprint)

    return _join(*standard)
