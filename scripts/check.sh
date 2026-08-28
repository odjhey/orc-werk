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
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
