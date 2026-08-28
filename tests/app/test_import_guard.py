"""`orc_werk.app` import-guard tests (`TASK-M0-005`).

Extends the `orc_werk.core`/`orc_werk.ports` import-guard pattern
(`tests/core/test_package_imports.py`, `tests/core/test_ports_interfaces.
py`) one layer further: `orc_werk.app` MUST import only the standard
library plus `orc_werk.core`/`orc_werk.ports` -- never
`orc_werk.adapters`/`orc_werk.cli` (`ARCH-REPOSITORY-STRUCTURE`'s
`app -> core + ports` dependency rule, and the explicit "forbidden
dependencies" table: `app -> concrete provider internals`).
"""

from __future__ import annotations

import importlib
import sys
import unittest


class AppImportGuardTest(unittest.TestCase):
    def test_app_is_importable(self) -> None:
        module = importlib.import_module("orc_werk.app")
        self.assertIsNotNone(module)
        self.assertTrue(hasattr(module, "Orchestrator"))

    def test_app_import_pulls_in_no_third_party_modules(self) -> None:
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        before = set(sys.modules)
        importlib.import_module("orc_werk.app")
        after = set(sys.modules)

        new_modules = after - before
        stdlib_names = sys.stdlib_module_names
        third_party = {
            name
            for name in new_modules
            if not name.startswith("orc_werk") and name.split(".")[0] not in stdlib_names
        }
        self.assertEqual(third_party, set(), f"orc_werk.app pulled in non-stdlib modules: {third_party}")

    def test_app_import_pulls_in_no_forbidden_orc_werk_packages(self) -> None:
        # ARCH-REPOSITORY-STRUCTURE: app -> core + ports only; never
        # adapters/cli.
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        importlib.import_module("orc_werk.app")

        forbidden_prefixes = ("orc_werk.adapters", "orc_werk.cli")
        leaked = {name for name in sys.modules if name.startswith(forbidden_prefixes)}
        self.assertEqual(leaked, set(), f"orc_werk.app pulled in forbidden orc_werk packages: {leaked}")

    def test_app_imports_core_and_ports(self) -> None:
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        importlib.import_module("orc_werk.app")

        self.assertIn("orc_werk.core", sys.modules)
        self.assertIn("orc_werk.ports", sys.modules)


if __name__ == "__main__":
    unittest.main()
