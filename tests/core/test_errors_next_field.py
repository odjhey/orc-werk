"""issue #94: the additive `next` field on `orc_werk.core.errors`'
canonical error envelope -- unit coverage that `next_steps` is opt-in,
additive, and backward-compatible (a caller that never passes it gets the
unchanged three-key `{error, message, details}` shape)."""

from __future__ import annotations

import unittest

from orc_werk.core.errors import (
    canonical_error,
    conflict_error,
    not_found_error,
    validation_error,
)


class CanonicalErrorNextFieldTest(unittest.TestCase):
    def test_no_next_steps_omits_next_key_entirely(self) -> None:
        error = canonical_error("ERR-VALIDATION", "bad input")
        self.assertNotIn("next", error)
        self.assertEqual(set(error), {"error", "message", "details"})

    def test_empty_next_steps_also_omits_next_key(self) -> None:
        error = canonical_error("ERR-VALIDATION", "bad input", next_steps=())
        self.assertNotIn("next", error)

    def test_next_steps_becomes_additive_next_list(self) -> None:
        error = canonical_error("ERR-VALIDATION", "bad input", next_steps=["do this", "or this"])
        self.assertEqual(error["next"], ["do this", "or this"])
        # additive: error/message/details unchanged in shape.
        self.assertEqual(set(error), {"error", "message", "details", "next"})

    def test_details_kwargs_still_flow_through_next_steps(self) -> None:
        error = canonical_error("ERR-VALIDATION", "bad input", next_steps=["fix it"], path="/a/b")
        self.assertEqual(error["details"], {"path": "/a/b"})
        self.assertEqual(error["next"], ["fix it"])


class HelperFunctionsNextFieldTest(unittest.TestCase):
    """The three CoreError-raising helpers (`validation_error`,
    `conflict_error`, `not_found_error`) all thread `next_steps` through to
    `canonical_error` identically."""

    def test_validation_error_without_next_steps_is_unchanged(self) -> None:
        exc = validation_error("bad")
        self.assertNotIn("next", exc.to_canonical())

    def test_validation_error_with_next_steps(self) -> None:
        exc = validation_error("bad", next_steps=["try again"])
        self.assertEqual(exc.to_canonical()["next"], ["try again"])

    def test_conflict_error_with_next_steps(self) -> None:
        exc = conflict_error("conflict", next_steps=["orc status <run>"])
        self.assertEqual(exc.to_canonical()["error"], "ERR-CONFLICT")
        self.assertEqual(exc.to_canonical()["next"], ["orc status <run>"])

    def test_not_found_error_with_next_steps(self) -> None:
        exc = not_found_error("missing", next_steps=["orc dispatch ..."])
        self.assertEqual(exc.to_canonical()["error"], "ERR-NOT-FOUND")
        self.assertEqual(exc.to_canonical()["next"], ["orc dispatch ..."])


if __name__ == "__main__":
    unittest.main()
