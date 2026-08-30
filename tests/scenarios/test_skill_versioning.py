"""CI enforcement for the distributed orc-ledger skill version registry."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "src" / "orc_werk" / "skills" / "orc-ledger" / "SKILL.md"
CHANGELOG = SKILL.with_name("CHANGELOG.md")
ENTRY_RE = re.compile(
    r"^## v(?P<version>[0-9]+) -- (?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})$"
    r"(?P<body>.*?)(?=^## v|\Z)",
    re.MULTILINE | re.DOTALL,
)
HASH_RE = re.compile(r"^content-sha256: ([0-9a-f]{64})$", re.MULTILINE)


class SkillVersioningTest(unittest.TestCase):
    def test_current_version_and_hash_match_newest_changelog_entry(self):
        skill_bytes = SKILL.read_bytes()
        skill_text = skill_bytes.decode("utf-8")
        version_match = re.search(r"^version: ([0-9]+)$", skill_text, re.MULTILINE)
        self.assertIsNotNone(version_match, "SKILL.md frontmatter must carry an integer version")

        entries = list(ENTRY_RE.finditer(CHANGELOG.read_text(encoding="utf-8")))
        self.assertTrue(entries, "CHANGELOG.md must contain at least one version entry")
        newest = entries[0]
        newest_hash = HASH_RE.search(newest.group("body"))
        self.assertIsNotNone(newest_hash)
        self.assertEqual(int(version_match.group(1)), int(newest.group("version")))
        self.assertEqual(hashlib.sha256(skill_bytes).hexdigest(), newest_hash.group(1))

    def test_changelog_is_a_well_formed_strictly_descending_hash_registry(self):
        text = CHANGELOG.read_text(encoding="utf-8")
        entries = list(ENTRY_RE.finditer(text))
        versions = []
        hashes = set()
        for entry in entries:
            version = int(entry.group("version"))
            dt.date.fromisoformat(entry.group("date"))
            digest_match = HASH_RE.search(entry.group("body"))
            self.assertIsNotNone(digest_match, f"v{version} must have content-sha256")
            self.assertRegex(entry.group("body"), r"(?m)^- .+", f"v{version} must explain what and why")
            self.assertNotIn(digest_match.group(1), hashes, "content hashes must identify one release")
            hashes.add(digest_match.group(1))
            versions.append(version)
        self.assertEqual(versions, sorted(versions, reverse=True))
        self.assertEqual(len(versions), len(set(versions)))
        self.assertTrue(all(a > b for a, b in zip(versions, versions[1:])))


if __name__ == "__main__":
    unittest.main()
