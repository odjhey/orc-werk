"""Smoke tests: the reference-implementation packages import cleanly, and
importing `orc_werk.core` pulls in no third-party modules (rule 8 in
CLAUDE.md/AGENTS.md: core must stay stdlib-only, zero integration
dependencies).
"""

from __future__ import annotations

import importlib
import sys
import unittest


class PackageImportsTest(unittest.TestCase):
    def test_core_imports(self) -> None:
        module = importlib.import_module("orc_werk.core")
        self.assertIsNotNone(module)

    def test_ports_imports(self) -> None:
        module = importlib.import_module("orc_werk.ports")
        self.assertIsNotNone(module)

    def test_adapters_memory_imports(self) -> None:
        module = importlib.import_module("orc_werk.adapters.memory")
        self.assertIsNotNone(module)

    def test_adapters_scripted_imports(self) -> None:
        module = importlib.import_module("orc_werk.adapters.scripted")
        self.assertIsNotNone(module)

    def test_core_import_pulls_in_no_third_party_modules(self) -> None:
        # Drop anything already imported under the orc_werk namespace so a
        # fresh import of orc_werk.core actually exercises its import graph,
        # then compare the newly-imported top-level modules against the
        # stdlib module list.
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        before = set(sys.modules)
        importlib.import_module("orc_werk.core")
        after = set(sys.modules)

        new_modules = after - before
        stdlib_names = sys.stdlib_module_names

        third_party = {
            name
            for name in new_modules
            if not name.startswith("orc_werk")
            and name.split(".")[0] not in stdlib_names
        }

        self.assertEqual(
            third_party,
            set(),
            f"orc_werk.core import pulled in non-stdlib modules: {third_party}",
        )

    def test_core_import_pulls_in_no_forbidden_orc_werk_packages(self) -> None:
        # ARCH-REPOSITORY-STRUCTURE forbids core -> ports/app/adapters/cli.
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        importlib.import_module("orc_werk.core")

        forbidden_prefixes = ("orc_werk.ports", "orc_werk.app", "orc_werk.adapters", "orc_werk.cli")
        leaked = {
            name
            for name in sys.modules
            if name.startswith(forbidden_prefixes)
        }

        self.assertEqual(
            leaked,
            set(),
            f"orc_werk.core import pulled in forbidden orc_werk packages: {leaked}",
        )


if __name__ == "__main__":
    unittest.main()
