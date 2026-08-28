"""`orc_werk.cli` import-guard test (`TASK-M0-005`).

`orc_werk.cli` is the one layer permitted to import `orc_werk.adapters`
(composition/bootstrap, `ARCH-REPOSITORY-STRUCTURE`: `cli -> app +
composition/configuration + selected adapters`). This test only proves the
package imports cleanly end-to-end (a real regression class: a stray
`orc_werk.core`-only import left over from refactoring would still import
fine on its own, but a broken `orc_werk.cli -> orc_werk.app -> ...` chain
would not).
"""

from __future__ import annotations

import importlib
import unittest


class CliImportGuardTest(unittest.TestCase):
    def test_cli_is_importable(self) -> None:
        module = importlib.import_module("orc_werk.cli")
        self.assertIsNotNone(module)
        self.assertTrue(hasattr(module, "main"))
        self.assertTrue(hasattr(module, "build_parser"))

    def test_cli_main_module_is_importable(self) -> None:
        module = importlib.import_module("orc_werk.cli.__main__")
        self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
