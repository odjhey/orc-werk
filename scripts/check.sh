#!/usr/bin/env bash
# Local gate. Mirrors .github/workflows/ci-required.yml's workspace-suite
# exactly, so a green run here means a green PR remotely. Cheapest checks
# first.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== docs_check =="
python3 scripts/docs_check.py

echo "== compileall =="
python3 -m compileall -q src tests scripts

echo "== unittest (tests/) =="
unittest_log="$(mktemp)"
trap 'rm -f "$unittest_log"' EXIT
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v 2>&1 | tee "$unittest_log"

# V5 (nother-guide): a skipped check is loud and counted. Derive the
# skipped set from this run's real output -- never a hardcoded string --
# so a green gate can never silently hide what it did not cover.
not_covered="$(python3 - "$unittest_log" <<'PY'
import re
import sys

# unittest -v prints "<name> (<qualified.id>) ... skipped '<reason>'" for
# every skipped test. Collect the qualified id (stable, comma-safe) of
# each one, deduplicated, so re-running the same skipped check twice in
# one invocation still names it once.
pattern = re.compile(r"^\S+ \(([\w.]+)\) \.\.\. skipped\b")
seen: set[str] = set()
ordered: list[str] = []
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        match = pattern.match(line)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            ordered.append(match.group(1))
print(", ".join(sorted(ordered)) if ordered else "none")
PY
)"

echo "check: green. NOT covered: ${not_covered}"
