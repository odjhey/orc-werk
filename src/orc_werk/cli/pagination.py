"""Shared "last N, with a definitive size hint" pagination (issue #43's
pagination addendum: axi principle #3, progressive disclosure/content
truncation with an escape hatch; axi #5, hints must be definitive -- exact
counts, never ambiguous truncation).

One helper backs every paginated CLI list (`orc history`, the bare-`orc`
run index) so the truncation math and hint wording never drift between
them. CLI-owned presentation only (CLAUDE.md #6/#7): no canonical
semantics, nothing recorded.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

from orc_werk.core.errors import validation_error

T = TypeVar("T")

# ~30 is the shared default across `history` and the bare index. Rationale
# (issue #43 comment: "defaults chosen for agent token
# budgets AND human scanability"): each record/run line here is one short
# line of plain text (well under 200 chars in the common case), so 30 lines
# stays a small, legible fraction of even a modest agent context-window
# turn while still reading as a complete "recent activity" snapshot to a
# human scanning a terminal. `--limit 0` is always one step away for the
# full set -- the axi #3 escape hatch.
DEFAULT_LIMIT = 30


def paginate(items: Sequence[T], *, limit: int) -> tuple[Sequence[T], int, bool]:
    """Return `(window, total, truncated)`.

    `window` is the last `limit` items of `items` (chronological/append
    order preserved), or all of them when `limit == 0` ("0 for all", the
    documented escape hatch) or when `total <= limit` (nothing to truncate).
    `total` is the exact original count -- callers render `total` verbatim
    in their size hint, never an approximation (axi #5: "definitive... never
    ambiguous truncation").
    """
    if limit < 0:
        raise validation_error(
            "limit must be greater than or equal to 0",
            limit=limit,
            next_steps=["pass --limit 0 to show all rows, or a positive integer to bound the listing"],
        )
    total = len(items)
    if limit == 0 or total <= limit:
        return items, total, False
    return items[-limit:], total, True


def size_hint(shown: int, total: int, *, limit_flag: str = "--limit 0", noun: str = "records") -> str:
    """The definitive truncation hint line: exact counts, and the exact
    flag that shows everything -- never "...N more" ambiguity."""
    return f"... showing last {shown} of {total} {noun}; {limit_flag} for all"


__all__ = ["DEFAULT_LIMIT", "paginate", "size_hint"]
