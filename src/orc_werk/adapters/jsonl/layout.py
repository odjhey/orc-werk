"""Per-run directory layout resolution, shared by `JSONLJournal` and the
observed-at time sidecar (issue #55, H1).

## New layout (the only layout any run created under this code ever writes)

```
<directory>/<run_id>/journal.jsonl   -- canonical JournalPort file (was <run_id>.jsonl)
<directory>/<run_id>/times.jsonl     -- observed-at sidecar (was <run_id>+times.jsonl)
<directory>/<run_id>/report.html     -- orc report's default output for this run
<directory>/<run_id>/config.json     -- persisted effective dispatch config (issue #55 H2)
```

Run lifecycle = directory lifecycle for the new layout: the run's own
directory holds every artifact that belongs to it, disambiguated by a fixed
filename rather than a filename suffix, so the `+` sidecar-separator rule
(`CONTRACT-DURABILITY`) is moot inside a run directory -- there is no
run-id-derived filename collision to guard against when every artifact
already lives under a directory scoped to exactly one run.

## Legacy flat layout (read-fallback only, never written by new code)

```
<directory>/<run_id>.jsonl           -- canonical journal
<directory>/<run_id>+times.jsonl     -- observed-at sidecar
<directory>/<run_id>.report.html     -- orc report's default output
```

Pre-#55 `.orc` directories keep working unmodified: every read path in this
adapter package and `orc_werk.cli` resolves through the helpers below,
which fall back to the legacy flat file whenever it is the one that
actually exists on disk.

A legacy `<run_id>+reports.jsonl` `crew-report/v1` sidecar (the removed
`EXT-CREW-REPORT-V1` fallback log, `docs/extensions/crew-report/README.md`,
superseded) may still exist on disk from before the removal (issue #100
part 2). This module deliberately no longer resolves a path for it -- no
code in this package or `orc_werk.cli` reads or writes it any more, so any
such file is simply inert. Its `+` name still keeps it correctly excluded
from `discover_run_ids`'s run-id sweep below (the sidecar-separator rule
still applies structurally even though this specific sidecar kind is no
longer produced or consumed).

## The discriminator is per-artifact, not per-run

Each artifact's own legacy filename is the ONLY thing that decides whether
THAT artifact reads/writes legacy or new layout -- `journal_path` checks
whether `<run_id>.jsonl` already exists, `times_path` checks
`<run_id>+times.jsonl`, independently of one another. What every one of
these functions guarantees on its own is the thing that actually matters:
ONE artifact never splits ITS OWN history across both layouts mid-run --
once `<run_id>.jsonl` (or `+times.jsonl`) exists on disk, that specific
artifact keeps being read from and appended to at that exact path for the
rest of its life. A brand-new artifact (no legacy file yet) always gets the
new layout.
"""

from __future__ import annotations

from pathlib import Path

JOURNAL_FILENAME = "journal.jsonl"
TIMES_FILENAME = "times.jsonl"
REPORT_HTML_FILENAME = "report.html"
CONFIG_FILENAME = "config.json"


def run_dir(directory: Path, run_id: str) -> Path:
    """The new-layout per-run directory, `<directory>/<run_id>`. Callers
    that need one specific artifact's path should use the dedicated
    `*_path` helpers below (which apply the legacy-fallback rule); this is
    exposed for config persistence, whose `config.json` has no legacy
    counterpart to fall back to."""
    return directory / run_id


def _resolve_artifact(directory: Path, run_id: str, *, legacy_name: str, new_filename: str) -> Path:
    """Shared per-artifact resolution (module docstring's "The
    discriminator is per-artifact" section): `legacy_name` existing on disk
    wins; otherwise the new-layout path under this run's own directory."""
    legacy_path = directory / legacy_name
    if legacy_path.exists():
        return legacy_path
    return run_dir(directory, run_id) / new_filename


def journal_path(directory: Path, run_id: str) -> Path:
    return _resolve_artifact(
        directory, run_id, legacy_name=f"{run_id}.jsonl", new_filename=JOURNAL_FILENAME
    )


def times_path(directory: Path, run_id: str) -> Path:
    return _resolve_artifact(
        directory, run_id, legacy_name=f"{run_id}+times.jsonl", new_filename=TIMES_FILENAME
    )


def report_html_path(directory: Path, run_id: str) -> Path:
    """`orc report <run>`'s default `--out` destination (issue #55 H1:
    "report default output lands inside the run dir"). This is an OUTPUT
    location, not something with its own pre-existing legacy file to check
    -- it follows the run's JOURNAL layout instead (the artifact this
    report is actually rendering), so a legacy-layout run's report keeps
    landing beside its flat journal by default, and a new-layout run's
    report lands inside that run's own directory."""
    journal = journal_path(directory, run_id)
    if journal.parent == directory:
        # journal_path resolved to the legacy flat file (its parent is the
        # journal root directory itself, not a per-run subdirectory).
        return directory / f"{run_id}.report.html"
    return run_dir(directory, run_id) / REPORT_HTML_FILENAME


def config_path(directory: Path, run_id: str) -> Path:
    """The durable in-run-dir dispatch config path (issue #55 H2, config
    persistence). Always under the new-layout run directory regardless of
    whether this run's journal itself is legacy or new -- config
    persistence has no legacy counterpart to fall back to (it did not
    exist before this task), so every run, old or new, gets it in the one
    place it can unambiguously live."""
    return run_dir(directory, run_id) / CONFIG_FILENAME


def discover_run_ids(directory: Path) -> list[str]:
    """Every run id under `directory`, new-layout and legacy, sorted.
    New-layout runs are subdirectories that actually contain a
    `journal.jsonl` (not just any subdirectory -- a run dir holding only a
    not-yet-dispatched `config.json`, or an unrelated directory, is not a
    run); legacy runs are `*.jsonl` files whose stem contains no `+` (the
    existing sidecar-exclusion rule). Read-only: never creates or opens
    anything beyond directory listing and `Path.exists`/`Path.is_dir`
    checks. A missing `directory` returns `[]` rather than raising."""
    if not directory.is_dir():
        return []
    run_ids: set[str] = set()
    for entry in directory.iterdir():
        if entry.is_dir() and (entry / JOURNAL_FILENAME).exists():
            run_ids.add(entry.name)
    for entry in directory.glob("*.jsonl"):
        if "+" not in entry.stem:
            run_ids.add(entry.stem)
    return sorted(run_ids)


__all__ = [
    "CONFIG_FILENAME",
    "JOURNAL_FILENAME",
    "REPORT_HTML_FILENAME",
    "TIMES_FILENAME",
    "config_path",
    "discover_run_ids",
    "journal_path",
    "report_html_path",
    "run_dir",
    "times_path",
]
