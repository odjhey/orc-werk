# Test layout

The Python reference implementation mirrors the contract structure:

- `core/` — pure reducer, policy, invariant, state-machine, and portable serialization tests;
- `conformance/` — reusable provider-independent port conformance suites;
- `scenarios/` — executable forms of the normative golden scenarios.

The full M0 test suite must run without Beads, zxro, Git, command-assurance scripts, CI, or other integration dependencies installed.

## Post-MVP test hardening

Mutation testing (mutmut), property-based testing (hypothesis), and lint/typecheck tooling are deliberately deferred until after a working, dogfoodable MVP ships. This is a delivery-sequencing decision, not a quality bar reduction: pre-MVP falsifiability instead relies on scenario docs as executable specs (`docs/README.md` authoring rule: "a scenario is an executable specification and should map directly to an automated test"), negative-space/invariance tests, adversarial review, and a minimal hand-picked mutation smoke at the M0 integration gate.

When mutmut/hypothesis/lint/typecheck tooling is adopted, it is dev-only tooling and never a runtime dependency — the stdlib-only constraint on `src/orc_werk/core` and the M0 suite (see above) stands unchanged.

## Coverage stance (as of the 2026-09-03 coverage-hygiene evaluation)

A coverage-hygiene evaluation dated 2026-09-03 measured 72.9% line / 56.7%
branch coverage over `src/*` and flagged five modules as the least covered.
Two of those gaps are accepted here rather than chased with more tests,
and one measurement artifact is documented rather than "fixed":

- **`cli/show.py`'s rendering-permutation combinations are an accepted
  gap.** Its findings/verdict/provenance/exit-code sections have many
  presentation combinations; this repo is dogfood-ready, not golden-set
  tested, for pre-MVP CLI rendering (`tests/cli/test_show*`-equivalent
  scenario/CLI tests already cover the operator-trust-relevant paths —
  verdict display, blocked/non-accepted exit codes — the remaining gap is
  cosmetic formatting permutations). A hand-picked golden-output-set test
  (recorded expected renders for a fixed catalog of projections, diffed
  byte-for-byte) is the natural post-MVP upgrade if `show.py` regressions
  ever surface in the field; it is not built pre-MVP per this file's
  "Post-MVP test hardening" section above.
- **Superseded-scope items are untested by design, not by omission.**
  `SCN-016`/`CONF-EXEC-005` (the ACP vanished-worker exit-status-honesty
  scenario) governed the `acp` execution adapter, removed in 0.5.0 (ADR-0005,
  issue #206/#214). The requirement text is retained in
  `docs/conformance/README.md` for historical/future-adapter binding
  (explicitly marked `**superseded**`), but there is no live adapter left
  to exercise it against — adding a test here would mean re-building a
  removed adapter solely to assert its own removed behavior. No action.
- **Subprocess CLI coverage is a measurement gap, not a testing gap** — see
  the next section. A large share of the raw coverage numbers reported for
  `cli/main.py` and `cli/jsonview.py` reflects `coverage.py` not observing
  code that only runs inside a spawned `python -m orc_werk.cli ...`
  subprocess (most of `tests/scenarios/`'s CLI-facing tests dispatch this
  way, deliberately, to exercise the real process boundary). Before buying
  more CLI tests to chase a number, re-measure with subprocess coverage
  enabled (below) — this run did exactly that; see "True (subprocess-
  inclusive) coverage" for the resulting numbers, which are the actual
  decision input for any future `cli/main.py`/`cli/jsonview.py` test
  investment (this lane deliberately does not spend on those two modules
  itself: TASK/PR out-of-scope note, per this run's brief).

## Measuring true CLI coverage (subprocess-inclusive)

The ordinary local gate (`scripts/check.sh` → `python3 -m unittest
discover -s tests -t .`) is never run under `coverage.py` — coverage
measurement is dev-only tooling, not part of the required gate, and adding
it there would violate the "no runtime dependency" rule above. When you DO
want a coverage number, the plain `coverage run -m unittest discover -s
tests -t .` command undercounts real behavior: it only observes the parent
test-runner process. A large share of `orc_werk.cli`'s command-routing,
error-envelope, and dispatch/wait/record/cancel logic (and essentially all
of `jsonview.py`'s output-shaping) is only reachable through a `python -m
orc_werk.cli ...` invocation the tests spawn via `subprocess.run`/`Popen`
(deliberately — this exercises the real process boundary the CLI is
actually invoked across) — `coverage.py` cannot see into a plain child
`python` process unless that child process is itself told to start
collecting.

Two ways to make the subprocess visible, both standard `coverage.py`
features (dev-only; no new runtime dependency):

1. **`coverage run --parallel-mode` per invocation** — works if you
   control every subprocess command line (swap `python -m orc_werk.cli`
   for `coverage run --parallel-mode -m orc_werk.cli` in whatever's
   spawning it), then `coverage combine` the resulting `.coverage.*`
   files. Not a good fit here: the subprocess command lines live inside
   ~40 test files as literal `[sys.executable, "-m", "orc_werk.cli",
   ...]` argv lists — rewriting them all is invasive and would drift
   from what real operators actually run.
2. **`COVERAGE_PROCESS_START` + automatic subprocess startup** — the
   technique this run actually used. `coverage.py` ships
   `coverage.process_startup()`, designed to be called from a
   `sitecustomize.py` (or a `.pth` file executing one line) that Python's
   `site` module imports automatically at interpreter startup in EVERY
   process, including subprocess children — no test-file changes needed.
   `coverage.process_startup()` itself checks the `COVERAGE_PROCESS_START`
   env var and no-ops if it's unset, so normal (non-measurement) runs are
   completely unaffected. The one wrinkle specific to this repo: several
   test helpers build the subprocess `env=` argument as a literal
   replacement dict (`{"PYTHONPATH": str(SRC), "PATH": ...}`), not an
   inherited-and-extended `os.environ` copy — so `COVERAGE_PROCESS_START`
   set in the parent shell does NOT reach those children. A `sitecustomize.py`
   dropped directly into the measurement copy's `src/` directory (already
   on every subprocess's `PYTHONPATH` by construction) sidesteps that by
   starting coverage unconditionally with a hardcoded data-file path,
   rather than depending on the env var at all. Sketch:

   ```python
   # src/sitecustomize.py -- measurement-only, never committed/shipped
   import atexit, os, coverage
   _cov = coverage.Coverage(branch=True, data_suffix=True,
                             data_file="/tmp/<run>/.covdata/.coverage",
                             source=["/tmp/<run>/src"])
   _cov.start()
   atexit.register(lambda: (_cov.stop(), _cov.save()))
   ```

   Run the parent suite itself under `coverage run --branch
   --parallel-mode --data-file=.covdata/.coverage -m unittest discover -s
   tests -t .` (parallel-mode so its own data file doesn't collide with
   the subprocesses'), then `coverage combine --data-file=.covdata/.coverage
   .covdata/` and `coverage report`/`coverage json` over the combined file.

This is dev-only, one-off measurement tooling — `sitecustomize.py` above
is never committed, never wired into `scripts/check.sh`/CI, and adds no
runtime dependency; `coverage` itself is installed only in a throwaway
`/tmp` venv for the duration of the measurement, exactly like the
evaluation's own method notes.

### True (subprocess-inclusive) coverage, re-measured 2026-09-03

This run actually re-measured (throwaway `/tmp` copy + venv, same method as
the evaluation's own "Method notes", plus the `sitecustomize.py` technique
above), AFTER this lane's own new tests landed:

| Scope | Line | Branch | Combined (line+branch) |
|---|---:|---:|---:|
| Overall (`src/orc_werk`, 5,369 statements / 1,978 branches — identical statement/branch universe to the evaluation's baseline, confirming zero `src/` changes this lane) | **92.7%** (391 missed) | **84.5%** (307 missed) | **90.5%** |
| `cli/main.py` | **94.3%** (41/722 missed) | **91.1%** (21/236 missed) | **93.5%** |
| `cli/jsonview.py` | **100%** | **100%** | **100%** |
| `adapters/locking.py` (this lane's new tests) | 100% | 100% | 100% |
| `cli/pagination.py` (this lane's new tests) | 100% | 100% | 100% |

Compare against the evaluation's subprocess-blind baseline: **72.9%
line / 56.7% branch / 68.5% combined** overall; `cli/main.py` **35.9%**;
`cli/jsonview.py` **36.0%**. The gap is almost entirely measurement
artifact, not missing tests: `cli/main.py` and `cli/jsonview.py` are
overwhelmingly exercised through `subprocess.run([sys.executable, "-m",
"orc_werk.cli", ...])`-style scenario/CLI tests that were already there —
this run added no `main.py`/`jsonview.py`-targeted tests at all (out of
scope for this coverage-hygiene lane, per its brief), yet
subprocess-inclusive measurement alone moves both from the worst-covered
modules in the repo to two of the best. This is the concrete decision
input for any *future* `cli/main.py`/`jsonview.py` test investment: the
evaluation's 35–36% numbers should not be used to justify new tests there
without first re-measuring this way — the real remaining gaps (`main.py`'s
41 still-missed statements/21 branches) are worth inspecting on their own
terms, not chased to close an illusory ~60-point hole.

`adapters/locking.py` and `cli/pagination.py` are genuinely 100% now (this
lane's own additions, not a measurement artifact — both are covered by
in-process unit tests, no subprocess involved).

