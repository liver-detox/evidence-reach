# EvidenceReach

Copyright 2026 liver-detox

EvidenceReach helps researchers decide whether a stated evidence-supply plan
can reach the mature sample size required for a two-sided one-sample test.

**On the first run:** get the required N, each
scenario's reachability state, and JSON, CSV, and Markdown results.

## Quickstart

From a local checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out result
```

The example uses invented values and creates `result/assessment.json`,
`result/reachability.csv`, and `result/summary.md`: the complete
machine-readable assessment, one row per scenario and horizon, and a short
interpretation.

## The decision it supports

Given an explicit effect, target power, and named evidence-supply scenarios,
EvidenceReach calculates the minimum mature sample size and whether that
threshold is reachable before the collection-and-maturity term ends. New
collection stops at the configured end date, while already collected units may
mature afterward. One-sample observations and precomputed paired differences
use the same calculation.

## Output files and states

`assessment.json`, `reachability.csv`, and `summary.md` provide the results
described above. States are `ALREADY_AT_REQUIRED_N`,
`SCENARIO_REACHABLE_WITHIN_TERM`, and
`SCENARIO_NOT_REACHABLE_WITHIN_TERM`. “Reachable” means only that the supplied
scenario arithmetic reaches the calculated N within its defined term.

## Python API

```python
from pathlib import Path

from evidence_reach import assess

plan_bytes = Path("examples/SYNTHETIC_plan.json").read_bytes()
result = assess(plan_bytes)
```

`assess` is pure: it accepts plan bytes and performs no file or network I/O.

## Boundaries and data handling

EvidenceReach is a planning and audit aid, not statistical advice. Its result
is deterministic arithmetic under the supplied scenarios—not a forecast or a
judgement about evidence validity or independence.

The included plan is synthetic. Use only data you are permitted to handle;
do not place sensitive or private material in plans, paths, or issue reports.
EvidenceReach has no network or market adapter and makes no adoption,
external-validation, or return claim.

## Statistical method and public comparison references

EvidenceReach uses SciPy's noncentral-t distribution and both tails of the
two-sided test. Required N is the smallest whole sample meeting target power;
a declared fixed comparison family receives a Bonferroni adjustment.

[`tests/test_power.py`](tests/test_power.py) freezes three power comparisons
and one required-N comparison evaluated with webR 0.6.0 / R 4.6.0 on
2026-08-21. The power values matched to 12 decimal places within the recorded
`2e-6` tolerance; the required-N case produced a ceiling of 34. The test file
also identifies statsmodels as a second public comparison route, but does not
claim an exact local statsmodels verification.

## Dependency and license

The runtime dependency is SciPy, which is BSD-licensed. EvidenceReach is
licensed under the Apache License 2.0; see `LICENSE`.
