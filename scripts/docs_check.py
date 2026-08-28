#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
ID_LINE_RE = re.compile(r"^id:\s*([^\s#]+)\s*$", re.M)
STABLE_PREFIXES = "P|INV|ENT|PORT|FACT|DEC|FX|CAP|ERR|SCN|CONF|ADR|M|TASK|ARCH|EXT"
REF_RE = re.compile(rf"`((?:{STABLE_PREFIXES})-[A-Z0-9-]+)`")


def main() -> int:
    ids: dict[str, Path] = {}
    refs: list[tuple[str, Path]] = []
    problems: list[str] = []

    files = sorted(DOCS.rglob("*.md"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            problems.append(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
            continue
        fm = match.group(1)
        id_match = ID_LINE_RE.search(fm)
        if not id_match:
            problems.append(f"{path.relative_to(ROOT)}: missing id in frontmatter")
            continue
        doc_id = id_match.group(1)
        if doc_id in ids:
            problems.append(
                f"duplicate document id {doc_id}: {ids[doc_id].relative_to(ROOT)} and {path.relative_to(ROOT)}"
            )
        else:
            ids[doc_id] = path
        refs.extend((ref, path) for ref in REF_RE.findall(text))

    # Stable sub-IDs may intentionally live inside registry docs rather than frontmatter.
    declared_inline: set[str] = set()
    declaration_re = re.compile(rf"^##+\s+((?:{STABLE_PREFIXES})-[A-Z0-9-]+)\b", re.M)
    table_id_re = re.compile(rf"`((?:{STABLE_PREFIXES})-[A-Z0-9-]+)`")
    for path in files:
        text = path.read_text(encoding="utf-8")
        declared_inline.update(declaration_re.findall(text))
        # Registry-style tables intentionally declare stable IDs in code formatting.
        if any(part in path.parts for part in ("contracts", "protocol", "conformance", "extensions")):
            declared_inline.update(table_id_re.findall(text))

    known = set(ids) | declared_inline
    for ref, path in refs:
        if ref not in known:
            problems.append(f"{path.relative_to(ROOT)}: unresolved stable ID reference {ref}")

    if problems:
        print("docs_check: FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"docs_check: PASS ({len(files)} markdown files, {len(known)} stable IDs discovered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
