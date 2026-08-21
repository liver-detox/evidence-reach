# EvidenceReach

Copyright 2026 liver-detox

## What EvidenceReach answers

EvidenceReach helps plan a two-sided one-sample t-test: given an explicit
effect, target power, and named evidence-supply scenarios, it calculates the
minimum mature sample size and whether that threshold is reachable before
the collection-and-maturity term ends. New collection stops at the configured
end date, while already collected units may mature afterward. One-sample
observations and precomputed paired differences use the same calculation.

## What it does not claim

This is a planning and audit aid, not statistical advice or a judgement about
evidence validity or independence. Reachability is scenario-implied,
deterministic arithmetic—not a forecast. It makes no claim of user adoption,
external validation, or any return outcome.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Run the synthetic example

```bash
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out result
```

The example uses invented values and creates `result/assessment.json`,
`result/reachability.csv`, and `result/summary.md`.

## Output files and states

`assessment.json` is the complete machine-readable assessment;
`reachability.csv` has one row per scenario and horizon; `summary.md` is a
short interpretation. States are `ALREADY_AT_REQUIRED_N`,
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

## Statistical method and public comparison references

EvidenceReach evaluates two-sided one-sample t power with SciPy’s noncentral-t
distribution. It uses `nct.sf(critical_t, df, noncentrality)` plus the lower
tail `nct.cdf(-critical_t, df, noncentrality)`; required N is the smallest
integer meeting target power. A user-declared fixed comparison family receives
a Bonferroni adjustment.

The frozen external references in `tests/test_power.py` were independently
evaluated on 2026-08-21 by webR npm 0.6.0 using R 4.6.0 / stats 4.6.0 in a
local Node R/Wasm runtime (not native macOS R/Rscript), with
`type="one.sample"`, `alternative="two.sided"`, and `strict=TRUE`:

```r
power.t.test(n=12, delta=0.3, sd=1, sig.level=0.10,
  type="one.sample", alternative="two.sided", strict=TRUE)$power
# observed: 0.256067159085451; frozen expected: 0.256067159085
power.t.test(n=25, delta=2, sd=5, sig.level=0.05,
  type="one.sample", alternative="two.sided", strict=TRUE)$power
# observed: 0.484018280695609; frozen expected: 0.484018280696
power.t.test(n=50, delta=1.5, sd=3, sig.level=0.01,
  type="one.sample", alternative="two.sided", strict=TRUE)$power
# observed: 0.799336911002067; frozen expected: 0.799336911002
```

The required-N reference is 34 for standardized effect 0.5, alpha 0.05, and
target power 0.8. It was independently evaluated in the same webR npm 0.6.0 /
R 4.6.0 / stats 4.6.0 environment: R returned continuous
`n=33.367129103906585`, whose whole-sample ceiling is 34. A second public
comparison route is statsmodels
`statsmodels.stats.power.TTestPower.solve_power`, for example:

```python
from statsmodels.stats.power import TTestPower

TTestPower().solve_power(
    effect_size=0.5, alpha=0.05, power=0.8, alternative="two-sided"
)
```

The R commands above were run locally through the recorded R/Wasm environment;
the three power values agree with the 12-decimal frozen expected values within
the test's `2e-6` tolerance, and the required-N result gives the tested ceiling
of 34. The statsmodels command was not run locally and is not represented as an
exact, bit-for-bit verification.

## Privacy and synthetic-data boundary

Use only information you are permitted to handle. Do not put secrets, personal
data, account information, holdings, trades, or private evidence into plans,
paths, or issue reports. The included plan is synthetic. EvidenceReach has no
market adapter and performs no network access.

## Dependency and license

The runtime dependency is SciPy, which is BSD-licensed. EvidenceReach is
licensed under the Apache License 2.0; see `LICENSE`.
