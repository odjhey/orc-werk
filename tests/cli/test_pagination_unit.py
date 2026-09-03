"""`orc_werk.cli.pagination` unit lane (issue #43's pagination addendum,
axi #3/#5): every executable branch of `paginate`, `window_before`, and
`size_hint`, with exact-output assertions -- the shared helper backing
`orc history` and the bare-`orc` run index, so drift here silently drifts
both callers at once.
"""

from __future__ import annotations

import unittest

from orc_werk.cli.pagination import paginate, size_hint, window_before
from orc_werk.core.errors import CoreError


class PaginateTest(unittest.TestCase):
    def test_negative_limit_raises_canonical_validation_error(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            paginate(["a", "b"], limit=-1)
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], "ERR-VALIDATION")
        self.assertEqual(canonical["message"], "limit must be greater than or equal to 0")
        self.assertEqual(canonical["details"], {"limit": -1})
        self.assertEqual(
            canonical["next"],
            ["pass --limit 0 to show all rows, or a positive integer to bound the listing"],
        )

    def test_large_negative_limit_is_still_the_same_canonical_shape(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            paginate([], limit=-100)
        self.assertEqual(ctx.exception.to_canonical()["details"]["limit"], -100)

    def test_zero_limit_returns_everything_untruncated(self) -> None:
        items = ["a", "b", "c"]
        window, total, truncated = paginate(items, limit=0)
        self.assertEqual(window, ["a", "b", "c"])
        self.assertEqual(total, 3)
        self.assertFalse(truncated)

    def test_zero_limit_on_empty_input(self) -> None:
        window, total, truncated = paginate([], limit=0)
        self.assertEqual(window, [])
        self.assertEqual(total, 0)
        self.assertFalse(truncated)

    def test_limit_equal_to_total_is_untruncated(self) -> None:
        items = ["a", "b", "c"]
        window, total, truncated = paginate(items, limit=3)
        self.assertEqual(window, ["a", "b", "c"])
        self.assertEqual(total, 3)
        self.assertFalse(truncated)

    def test_limit_over_total_is_untruncated(self) -> None:
        items = ["a", "b"]
        window, total, truncated = paginate(items, limit=10)
        self.assertEqual(window, ["a", "b"])
        self.assertEqual(total, 2)
        self.assertFalse(truncated)

    def test_limit_under_total_truncates_to_the_tail_preserving_append_order(self) -> None:
        items = ["a", "b", "c", "d", "e"]
        window, total, truncated = paginate(items, limit=2)
        self.assertEqual(window, ["d", "e"])
        self.assertEqual(total, 5)
        self.assertTrue(truncated)

    def test_limit_one_under_total_returns_exactly_the_last_element(self) -> None:
        items = ["a", "b", "c"]
        window, total, truncated = paginate(items, limit=1)
        self.assertEqual(window, ["c"])
        self.assertEqual(total, 3)
        self.assertTrue(truncated)


class WindowBeforeTest(unittest.TestCase):
    @staticmethod
    def _items():
        return [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}, {"id": "r4"}]

    def test_no_cursor_delegates_directly_to_paginate(self) -> None:
        window, total, truncated = window_before(
            self._items(), limit=2, before=None, cursor_of=lambda r: r["id"], cursor_name="before"
        )
        self.assertEqual(window, [{"id": "r3"}, {"id": "r4"}])
        self.assertEqual(total, 4)
        self.assertTrue(truncated)

    def test_unknown_cursor_raises_canonical_validation_error(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            window_before(
                self._items(), limit=2, before="does-not-exist", cursor_of=lambda r: r["id"], cursor_name="before"
            )
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], "ERR-VALIDATION")
        self.assertEqual(canonical["message"], "unknown before cursor")
        self.assertEqual(canonical["details"], {"cursor": "does-not-exist"})
        self.assertEqual(
            canonical["next"],
            ["omit --before to list the most-recent page, then use its next-page command"],
        )

    def test_unknown_cursor_error_names_the_actual_cursor_flag(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            window_before(
                self._items(), limit=2, before="ghost", cursor_of=lambda r: r["id"], cursor_name="cursor"
            )
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["message"], "unknown cursor cursor")
        self.assertEqual(canonical["next"], ["omit --cursor to list the most-recent page, then use its next-page command"])

    def test_known_cursor_windows_the_prefix_strictly_before_it(self) -> None:
        window, total, truncated = window_before(
            self._items(), limit=10, before="r3", cursor_of=lambda r: r["id"], cursor_name="before"
        )
        # Eligible corpus is everything strictly before r3: r1, r2.
        self.assertEqual(window, [{"id": "r1"}, {"id": "r2"}])
        self.assertEqual(total, 2)
        self.assertFalse(truncated)

    def test_cursor_at_the_first_item_yields_an_empty_window(self) -> None:
        window, total, truncated = window_before(
            self._items(), limit=10, before="r1", cursor_of=lambda r: r["id"], cursor_name="before"
        )
        self.assertEqual(window, [])
        self.assertEqual(total, 0)
        self.assertFalse(truncated)

    def test_cursor_combined_with_a_truncating_limit(self) -> None:
        window, total, truncated = window_before(
            self._items(), limit=1, before="r4", cursor_of=lambda r: r["id"], cursor_name="before"
        )
        # Eligible corpus before r4 is r1, r2, r3; limit=1 keeps only r3.
        self.assertEqual(window, [{"id": "r3"}])
        self.assertEqual(total, 3)
        self.assertTrue(truncated)

    def test_append_stable_cursoring_unaffected_by_items_appended_after_the_cursor(self) -> None:
        # Stateless-cursor guarantee: paging "before r2" must return the
        # same window whether or not newer items have since been appended
        # after r2 -- the cursor identifies an item, not an offset.
        base = self._items()[:2]  # r1, r2
        cursor_of = lambda r: r["id"]  # noqa: E731
        before_append = window_before(base, limit=10, before="r2", cursor_of=cursor_of, cursor_name="before")

        appended = base + [{"id": "r3"}, {"id": "r4"}]
        after_append = window_before(appended, limit=10, before="r2", cursor_of=cursor_of, cursor_name="before")

        self.assertEqual(before_append, after_append)
        self.assertEqual(after_append[0], [{"id": "r1"}])


class SizeHintTest(unittest.TestCase):
    def test_default_wording(self) -> None:
        self.assertEqual(
            size_hint(5, 30),
            "... showing last 5 of 30 records; --limit 0 for all",
        )

    def test_custom_limit_flag_and_noun(self) -> None:
        self.assertEqual(
            size_hint(2, 9, limit_flag="--before none", noun="runs"),
            "... showing last 2 of 9 runs; --before none for all",
        )


if __name__ == "__main__":
    unittest.main()
