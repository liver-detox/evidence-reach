# EvidenceReach validation notes

## Statistical method

EvidenceReach evaluates two-sided one-sample t power with SciPy’s noncentral-t
distribution. It uses `nct.sf(critical_t, df, noncentrality)` plus the lower
tail `nct.cdf(-critical_t, df, noncentrality)`; required N is the smallest
integer meeting target power. A user-declared fixed comparison family receives
a Bonferroni adjustment.

## Frozen public comparison references

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
comparison route is statsmodels `statsmodels.stats.power.TTestPower.solve_power`:

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
