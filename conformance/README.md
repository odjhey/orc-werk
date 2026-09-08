# Portable conformance kit

This directory is a versioned, language-neutral JSON fixture corpus. It
lets an implementation of orc-werk's documented `STATE-DELIVERY`
transition contract, written in any language, check its observable
results against the real reference core -- without reading Python
source, importing a Python object, or running a Python fixture
generator.

Normative source: `docs/conformance/portable-kit.md`
(`CONFORMANCE-PORTABLE-KIT`). This README is a landing-page pointer, not
the contract.

```
manifest.json          case index: id, title, mapped contract/scenario IDs
cases/CASE-NNN-*.json  one static, versioned input+expected fixture per case
reference/run_case.py  reference driver (Python; read for its shape only)
checker.py             reference checker/CLI (Python; optional to use)
```

## Quick start

```
python3 checker.py                          # run every case against the reference driver
python3 checker.py CASE-001-happy-path-acceptance   # run one case
python3 checker.py --driver-cmd "your-binary"       # substitute another implementation
python3 checker.py --probe                  # falsification probes
```

No Python is required to *consume* this kit -- `manifest.json` and every
`cases/*.json` file are plain JSON, and the stdin/stdout driver contract
`docs/conformance/portable-kit.md` documents can be implemented in any
language and checked with a hand-rolled subset-equality comparison.
`checker.py`/`reference/run_case.py` exist for convenience and as a
reference; they are not the contract itself.
