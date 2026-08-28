"""`MemoryJournal` runs the shared `CONF-JOURNAL-001`..`003` suite
(`tests/conformance/journal_suite.py`)."""

from __future__ import annotations

import unittest

from orc_werk.adapters.memory.journal import MemoryJournal

from tests.conformance.journal_suite import JournalConformanceSuite


class MemoryJournalConformanceTest(JournalConformanceSuite):
    def setUp(self) -> None:
        self.journal_factory = MemoryJournal
        super().setUp()


if __name__ == "__main__":
    unittest.main()
