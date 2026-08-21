# EvidenceReach v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest complete EvidenceReach v0.1: one pure Python assessment API and one CLI that combine exact one-sample t-test power calculations with deterministic sample-reachability scenarios.

**Architecture:** Keep the approved four-module boundary. `power.py` owns noncentral-t calculations, `reachability.py` owns calendar arithmetic, `core.py` validates one JSON plan and composes a normalized result, and `cli.py` performs file I/O. The public API accepts the exact UTF-8 plan bytes so `plan_sha256` can describe exactly what was assessed without the core reading a file.

**Tech Stack:** Python 3.12–3.14, SciPy 1.18.x, standard-library `unittest`, `argparse`, `json`, `csv`, `datetime`, `hashlib`, and `pathlib`; setuptools build backend; GitHub Actions for the three-version test matrix.

**Spec:** `docs/design/2026-08-21-evidence-reach-design.md`

## Global Constraints

- Work only in the standalone clean EvidenceReach project directory.
- Preserve the already approved design at `docs/design/2026-08-21-evidence-reach-design.md` and this implementation plan; neither is production code.
- Do not read implementation code, data, reports, identifiers, dates, or Git history from the private quantitative-research repository while implementing this plan.
- Keep v0.1 to the four approved production modules, three test files, one synthetic plan, README, license, package metadata, and one CI workflow.
- Do not add market adapters, network access, databases, web interfaces, logging, telemetry, plugin systems, formatters, linters, documentation generators, or release automation.
- Use only invented example values and dates. Do not put personal information, account data, holdings, trades, provider details, API values, or private paths into source, tests, examples, documentation, or Git metadata.
- Calculate with unrounded values. Apply Python `round(value, 12)` only while building the final machine-facing result, retaining a finite nonzero value when rounding would produce zero.
- A local Git repository, local commits, a remote repository, pushes, uploads, and releases remain separate actions. Every Git command shown below is a future checkpoint and must be skipped until the user separately authorizes that action.
- Stop after any failing verification. Diagnose before moving to the next task.

---

## Task 1: Package skeleton and exact power core

**Files:**

- Create: `pyproject.toml`
- Create: `src/evidence_reach/__init__.py`
- Create: `src/evidence_reach/power.py`
- Create: `tests/test_power.py`

- [ ] **Step 1: Create package metadata with one runtime dependency and one CLI entry point**

Use this exact package boundary in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "evidence-reach"
version = "0.1.0"
description = "Join statistical power with deterministic evidence-supply reachability."
readme = "README.md"
requires-python = ">=3.12,<3.15"
license = "Apache-2.0"
authors = [{name = "liver-detox"}]
dependencies = ["scipy>=1.18,<2"]

[project.scripts]
evidence-reach = "evidence_reach.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

Create an initially minimal `src/evidence_reach/__init__.py` that exposes only the version until `assess` exists:

```python
"""EvidenceReach public package."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Write failing power tests first**

Create `tests/test_power.py` with these cases:

```python
import unittest

from evidence_reach.power import (
    minimum_detectable_effect,
    one_sample_t_power,
    required_sample_size,
)


class PowerTest(unittest.TestCase):
    def test_zero_effect_equals_two_sided_alpha(self) -> None:
        result = one_sample_t_power(
            effect=0.0,
            difference_sd=1.0,
            n=20,
            alpha=0.05,
        )
        self.assertAlmostEqual(result, 0.05, places=12)

    def test_reference_required_n_is_smallest_reaching_integer(self) -> None:
        required_n = required_sample_size(
            effect=0.5,
            difference_sd=1.0,
            alpha=0.05,
            target_power=0.8,
        )
        self.assertEqual(required_n, 34)
        self.assertLess(
            one_sample_t_power(
                effect=0.5,
                difference_sd=1.0,
                n=required_n - 1,
                alpha=0.05,
            ),
            0.8,
        )
        self.assertGreaterEqual(
            one_sample_t_power(
                effect=0.5,
                difference_sd=1.0,
                n=required_n,
                alpha=0.05,
            ),
            0.8,
        )

    def test_mde_inverts_target_power(self) -> None:
        mde = minimum_detectable_effect(
            difference_sd=8.0,
            n=40,
            alpha=0.025,
            target_power=0.8,
        )
        recovered = one_sample_t_power(
            effect=mde,
            difference_sd=8.0,
            n=40,
            alpha=0.025,
        )
        self.assertAlmostEqual(recovered, 0.8, delta=1e-6)

    def test_mde_is_zero_when_zero_effect_already_reaches_target(self) -> None:
        self.assertEqual(
            minimum_detectable_effect(
                difference_sd=1.0,
                n=20,
                alpha=0.05,
                target_power=0.04,
            ),
            0.0,
        )

    def test_power_and_mde_are_monotonic(self) -> None:
        self.assertLess(
            one_sample_t_power(effect=0.4, difference_sd=1.0, n=20, alpha=0.05),
            one_sample_t_power(effect=0.4, difference_sd=1.0, n=40, alpha=0.05),
        )
        self.assertGreater(
            minimum_detectable_effect(
                difference_sd=1.0, n=20, alpha=0.05, target_power=0.8
            ),
            minimum_detectable_effect(
                difference_sd=1.0, n=40, alpha=0.05, target_power=0.8
            ),
        )


if __name__ == "__main__":
    unittest.main()
```

The `required_n == 34` case is an independent frozen reference for a two-sided one-sample test with standardized effect `0.5`, alpha `0.05`, and target power `0.8`. During implementation, record its public comparison source in the README: statsmodels `TTestPower.solve_power` and R `stats::power.t.test(..., type="one.sample", strict=TRUE)`.

- [ ] **Step 3: Run the test and confirm the expected import failure**

```bash
python -m unittest tests.test_power -v
```

Expected: `ModuleNotFoundError` or missing-symbol failure because `power.py` does not exist yet.

- [ ] **Step 4: Implement only the three statistical functions**

Create `src/evidence_reach/power.py` with these exact testable internal-module signatures. They are not exported from the package root; `assess` remains the only public operation:

```python
def one_sample_t_power(
    *, effect: float, difference_sd: float, n: int, alpha: float
) -> float:
    """Return strict two-sided one-sample t power using a noncentral t."""


def minimum_detectable_effect(
    *, difference_sd: float, n: int, alpha: float, target_power: float
) -> float:
    """Return the non-negative raw-unit MDE boundary for target power."""


def required_sample_size(
    *, effect: float, difference_sd: float, alpha: float, target_power: float
) -> int:
    """Return the smallest integer n of at least two reaching target power."""
```

Implement the approved equation directly:

```python
df = n - 1
critical_t = scipy.stats.t.isf(alpha / 2.0, df)
noncentrality = abs(effect / difference_sd) * math.sqrt(n)
power = scipy.stats.nct.sf(critical_t, df, noncentrality) + scipy.stats.nct.cdf(
    -critical_t, df, noncentrality
)
```

Implementation rules:

- `one_sample_t_power` accepts zero effect for calibration tests but requires `difference_sd > 0`, `n >= 2`, and `0 < alpha < 1`.
- MDE returns `0.0` when `target_power <= alpha`, because zero effect already reaches the requested power and no smallest strictly positive effect exists. Otherwise it doubles an upper effect bracket until it reaches target power, then performs bisection until the recovered power differs from target by at most `1e-10` or 100 iterations finish.
- Required N doubles an integer upper bracket from 2, then uses integer binary search and returns the first passing N.
- Raise `ValueError` for invalid direct function arguments and `ArithmeticError` if SciPy returns a non-finite result or a bracket cannot be established safely.

- [ ] **Step 5: Run the focused power suite**

```bash
python -m unittest tests.test_power -v
```

Expected: all five tests pass.

- [ ] **Step 6: Add the independent strict-power reference cases and rerun**

Add at least three frozen cases generated outside EvidenceReach from R's standard-library `power.t.test` with `type="one.sample"`, `alternative="two.sided"`, and `strict=TRUE`. Cover different N, alpha, effect, and standard deviation values. Assert with `delta=2e-6`; keep the source command and returned number in a test comment. This is test evidence, not a runtime dependency.

```bash
python -m unittest tests.test_power -v
```

Expected: the complete power suite passes, including frozen references, monotonicity, MDE inversion, minimum N, and zero-effect calibration.

- [ ] **Step 7: Conditional local commit checkpoint**

Run only after separate authorization to initialize Git and commit locally:

```bash
git add pyproject.toml src/evidence_reach/__init__.py src/evidence_reach/power.py tests/test_power.py
git commit -m "feat: add exact one-sample power core"
```

---

## Task 2: Deterministic reachability core

**Files:**

- Create: `src/evidence_reach/reachability.py`
- Create: `tests/test_reachability.py`

- [ ] **Step 1: Write failing date-boundary and scenario tests**

Create `tests/test_reachability.py`. Use `datetime.date` and these core cases:

```python
import unittest
from datetime import date

from evidence_reach.reachability import (
    PendingBatch,
    Scenario,
    build_reachability_rows,
    implied_matured_n,
)


class ReachabilityTest(unittest.TestCase):
    def test_lag_uses_half_open_start_and_whole_unit_flooring(self) -> None:
        count = implied_matured_n(
            evaluation_date=date(2030, 1, 31),
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 12, 31),
            maturity_lag_days=28,
            current_matured_n=5,
            pending_batches=(),
            eligible_units_per_30_days=6.0,
        )
        self.assertEqual(count, 5)

    def test_pending_date_is_final_and_does_not_receive_lag_again(self) -> None:
        pending = (PendingBatch(count=3, maturity_date=date(2030, 2, 15)),)
        before = implied_matured_n(
            evaluation_date=date(2030, 2, 14),
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 7, 1),
            maturity_lag_days=28,
            current_matured_n=5,
            pending_batches=pending,
            eligible_units_per_30_days=0.0,
        )
        on_date = implied_matured_n(
            evaluation_date=date(2030, 2, 15),
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 7, 1),
            maturity_lag_days=28,
            current_matured_n=5,
            pending_batches=pending,
            eligible_units_per_30_days=0.0,
        )
        self.assertEqual((before, on_date), (5, 8))

    def test_already_reached_uses_as_of_date(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 7, 1),
            maturity_lag_days=28,
            current_matured_n=40,
            pending_batches=(),
            horizons_days=(90, 180),
            scenarios=(Scenario(id="SYNTHETIC_ZERO", eligible_units_per_30_days=0.0),),
            required_n=34,
        )
        self.assertTrue(all(row["state"] == "ALREADY_AT_REQUIRED_N" for row in rows))
        self.assertTrue(all(row["earliest_target_date"] == "2030-01-01" for row in rows))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the expected import failure**

```bash
python -m unittest tests.test_reachability -v
```

Expected: missing-module or missing-symbol failure.

- [ ] **Step 3: Implement the two value types and two operations**

Use frozen dataclasses and exact field names. These are internal implementation values, not additional package-root operations:

```python
@dataclass(frozen=True)
class PendingBatch:
    count: int
    maturity_date: date


@dataclass(frozen=True)
class Scenario:
    id: str
    eligible_units_per_30_days: Decimal | float
```

Expose:

```python
def implied_matured_n(
    *,
    evaluation_date: date,
    as_of_date: date,
    collection_end_date: date,
    maturity_lag_days: int,
    current_matured_n: int,
    pending_batches: tuple[PendingBatch, ...],
    eligible_units_per_30_days: Decimal | float,
) -> int:
    """Return the scenario-implied whole mature count on one date."""


def build_reachability_rows(
    *,
    as_of_date: date,
    collection_end_date: date,
    maturity_lag_days: int,
    current_matured_n: int,
    pending_batches: tuple[PendingBatch, ...],
    horizons_days: tuple[int, ...],
    scenarios: tuple[Scenario, ...],
    required_n: int,
) -> list[dict[str, object]]:
    """Return scenario-major, horizon-minor rows in stable input order."""
```

Use only the approved formula. Preserve each JSON scenario-rate lexeme within
the maximum finite binary64 magnitude as an exact decimal and floor
`rate * eligible_days / 30` without an intermediate binary float. Short-circuit
to zero when a cheap exact order bound proves the rate cannot yield one whole
unit, before constructing a rational value. Search for the earliest target
date one calendar day at a time from `as_of_date` through the inclusive search
end. The search end is `collection_end_date + maturity_lag_days`, extended to
the latest explicit pending maturity date when pending batches exist.

Each row has exactly:

```python
{
    "scenario_id": scenario.id,
    "horizon_days": horizon_days,
    "horizon_date": horizon_date.isoformat(),
    "scenario_implied_matured_n": implied_count,
    "required_n": required_n,
    "state": state,
    "earliest_target_date": earliest_date_or_none,
}
```

The state describes reachability within the full approved search term and is therefore repeated across a scenario's horizon rows. A horizon's own count remains explicit in `scenario_implied_matured_n`.

- [ ] **Step 4: Add the remaining boundary tests**

Cover all of these without adding new production features:

- zero rate with no pending batches is unreachable;
- a pending batch can mature after collection ends but before the search ends;
- with no pending batches, the search ends at collection end plus lag;
- the final collection date contributes new supply, and supply saturates after its final maturity;
- zero maturity lag;
- counts are monotonic across increasing horizons;
- earliest date is the first passing date, not one day later;
- scenario rate flooring never creates fractional units;
- horizon date equals `as_of_date + horizon_days` exactly.

- [ ] **Step 5: Run the reachability suite**

```bash
python -m unittest tests.test_reachability -v
```

Expected: every boundary and state test passes.

- [ ] **Step 6: Conditional local commit checkpoint**

Run only after separate authorization:

```bash
git add src/evidence_reach/reachability.py tests/test_reachability.py
git commit -m "feat: add deterministic sample reachability"
```

---

## Task 3: Strict plan validation and pure assessment composition

**Files:**

- Create: `src/evidence_reach/core.py`
- Modify: `src/evidence_reach/__init__.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing API contract tests in `tests/test_cli.py`**

Start with a helper that returns exact JSON bytes for an invented plan. Then add these tests:

```python
import hashlib
import json
import unittest

from evidence_reach import PlanValidationError, assess
from evidence_reach.power import one_sample_t_power


def synthetic_plan_bytes() -> bytes:
    plan = {
        "schema_version": "1",
        "as_of_date": "2030-01-01",
        "analysis": {
            "effect": 2.0,
            "difference_sd": 8.0,
            "alpha": 0.05,
            "target_power": 0.8,
            "comparison_count": 1,
        },
        "sampling": {
            "current_matured_n": 5,
            "pending_batches": [
                {"count": 3, "maturity_date": "2030-02-15"}
            ],
            "maturity_lag_days": 28,
            "collection_end_date": "2030-07-01",
        },
        "horizons_days": [90, 180, 365],
        "scenarios": [
            {"id": "SYNTHETIC_LOW", "eligible_units_per_30_days": 2.0},
            {"id": "SYNTHETIC_BASE", "eligible_units_per_30_days": 4.0},
            {"id": "SYNTHETIC_HIGH", "eligible_units_per_30_days": 6.0},
        ],
    }
    return json.dumps(plan, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class AssessContractTest(unittest.TestCase):
    def test_assess_hashes_exact_input_bytes_and_returns_required_sections(self) -> None:
        plan_bytes = synthetic_plan_bytes()
        result = assess(plan_bytes)
        self.assertEqual(result["plan_sha256"], hashlib.sha256(plan_bytes).hexdigest())
        self.assertEqual(
            list(result),
            [
                "schema_version",
                "plan_sha256",
                "method",
                "assumptions",
                "statistics",
                "reachability",
                "limitations",
            ],
        )

    def test_current_statistics_are_unavailable_below_two_mature_units(self) -> None:
        plan = json.loads(synthetic_plan_bytes())
        plan["sampling"]["current_matured_n"] = 1
        result = assess(json.dumps(plan, separators=(",", ":")).encode("utf-8"))
        self.assertIsNone(result["statistics"]["current_power"])
        self.assertIsNone(result["statistics"]["current_mde"])
        self.assertGreaterEqual(result["statistics"]["required_n"], 2)

    def test_bonferroni_uses_declared_fixed_family(self) -> None:
        plan = json.loads(synthetic_plan_bytes())
        plan["analysis"]["comparison_count"] = 4
        plan_bytes = json.dumps(plan, separators=(",", ":")).encode("utf-8")
        result = assess(plan_bytes)
        self.assertEqual(result["statistics"]["adjusted_alpha"], 0.0125)
        self.assertAlmostEqual(
            result["statistics"]["current_power"],
            one_sample_t_power(
                effect=2.0,
                difference_sd=8.0,
                n=5,
                alpha=0.0125,
            ),
            places=12,
        )
        required_n = result["statistics"]["required_n"]
        self.assertAlmostEqual(
            result["statistics"]["power_at_required_n"],
            one_sample_t_power(
                effect=2.0,
                difference_sd=8.0,
                n=required_n,
                alpha=0.0125,
            ),
            places=12,
        )

    def test_unknown_field_is_rejected_without_echoing_plan(self) -> None:
        plan = json.loads(synthetic_plan_bytes())
        plan["private_note"] = "SENSITIVE_SENTINEL"
        with self.assertRaises(PlanValidationError) as caught:
            assess(json.dumps(plan).encode("utf-8"))
        self.assertIn("private_note", str(caught.exception))
        self.assertNotIn("SENSITIVE_SENTINEL", str(caught.exception))
```

- [ ] **Step 2: Run the focused contract tests and confirm failure**

```bash
python -m unittest tests.test_cli.AssessContractTest -v
```

Expected: missing `assess` and `PlanValidationError` symbols.

- [ ] **Step 3: Implement one safe validation error and exact-byte API**

Create `src/evidence_reach/core.py` with this public surface:

```python
class PlanValidationError(ValueError):
    """A field location and short reason safe to show to a CLI user."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def assess(plan_bytes: bytes) -> dict[str, object]:
    """Validate exact UTF-8 JSON bytes and return a deterministic assessment."""
```

`assess` must:

1. require a `bytes` value;
2. compute SHA-256 before decoding;
3. decode strict UTF-8 and parse one JSON object;
4. validate the complete approved contract;
5. calculate `adjusted_alpha = alpha / comparison_count`;
6. call the power and reachability modules;
7. assemble keys in the approved stable order; and
8. recursively apply `round(value, 12)` to floats only after every calculation is complete, preserving the original finite nonzero value when rounding would produce zero.

Use these fixed method strings:

```python
"method": {
    "test": "two-sided one-sample t on observations or precomputed paired differences",
    "power_distribution": "noncentral t",
    "multiple_comparisons": "Bonferroni adjustment for a user-declared fixed family",
    "reachability": "deterministic scenario arithmetic",
}
```

Use these fixed limitations:

```python
"limitations": [
    "Scenario-implied reachability is not a probability forecast or promise.",
    "EvidenceReach does not validate evidence quality, eligibility, independence, or truth.",
    "Bonferroni applies only to the fixed comparison family declared by the caller.",
    "This assessment is a planning aid, not statistical, financial, or investment advice.",
]
```

Build `statistics` with exactly these keys and use `adjusted_alpha` in every power, MDE, and required-N call:

```python
"statistics": {
    "adjusted_alpha": adjusted_alpha,
    "current_matured_n": current_matured_n,
    "current_power": current_power_or_none,
    "current_mde": current_mde_or_none,
    "required_n": required_n,
    "power_at_required_n": power_at_required_n,
}
```

When `current_matured_n < 2`, both current fields are `None`. When `target_power <= adjusted_alpha` and current N is at least two, `current_mde` is `0.0`; add a direct API test for that legal edge case.

Return only selected scalar assumptions, not the raw plan, paths, host data, or timestamps:

```python
"assumptions": {
    "as_of_date": as_of_date.isoformat(),
    "effect": effect,
    "difference_sd": difference_sd,
    "alpha": alpha,
    "target_power": target_power,
    "comparison_count": comparison_count,
    "maturity_lag_days": maturity_lag_days,
    "collection_end_date": collection_end_date.isoformat(),
}
```

Implement validation with small private helpers. Reject booleans where integers or real numbers are required. Reject all missing and unknown fields at the root and every nested object. Parse dates with `date.fromisoformat` and require `parsed.isoformat() == supplied_text`.

- [ ] **Step 4: Export the public API**

Replace `src/evidence_reach/__init__.py` with:

```python
"""EvidenceReach public package."""

from .core import PlanValidationError, assess

__all__ = ["PlanValidationError", "assess"]
__version__ = "0.1.0"
```

- [ ] **Step 5: Add a table-driven test for every validation rule**

In `tests/test_cli.py`, use `subTest` to cover:

- invalid schema version and non-object JSON root;
- non-finite, zero, or negative effect and difference SD;
- alpha and target power outside the open interval `(0, 1)`;
- non-positive or boolean comparison count;
- negative or boolean current mature count and lag;
- zero/negative pending count, invalid pending date, and pending date not later than as-of;
- current mature N plus cumulative pending counts exceeding the `sys.maxsize` computational count bound;
- collection end before as-of;
- empty, duplicate, unordered, zero, negative, or boolean horizons;
- empty scenarios, empty/duplicate IDs, negative/non-finite/boolean rates;
- missing and unknown fields at each object level;
- invalid UTF-8 and malformed JSON.

For every rejected case, assert that the exception contains a field location and does not echo the rejected value or raw JSON. A rejected field name is expected to appear as its location.

- [ ] **Step 6: Run the API and full unit suites**

```bash
python -m unittest tests.test_cli.AssessContractTest -v
python -m unittest discover -s tests -v
```

Expected: all power, reachability, API, Bonferroni, unavailable-current-statistics, and validation tests pass.

- [ ] **Step 7: Conditional local commit checkpoint**

Run only after separate authorization:

```bash
git add src/evidence_reach/core.py src/evidence_reach/__init__.py tests/test_cli.py
git commit -m "feat: compose validated evidence assessments"
```

---

## Task 4: CLI, deterministic outputs, and synthetic example

**Files:**

- Create: `src/evidence_reach/cli.py`
- Modify: `tests/test_cli.py`
- Create: `examples/SYNTHETIC_plan.json`

- [ ] **Step 1: Add the approved synthetic plan verbatim**

Create `examples/SYNTHETIC_plan.json` from the JSON example in section 4 of the approved design. Keep all identifiers visibly synthetic and end the file with one newline.

- [ ] **Step 2: Write failing end-to-end CLI tests**

Use `tempfile.TemporaryDirectory`, call `main([...])` directly, and assert:

```python
class CliTest(unittest.TestCase):
    def test_success_writes_only_three_stable_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan_path.write_bytes(synthetic_plan_bytes())

            first_status = main(
                ["assess", "--plan", str(plan_path), "--out", str(output_path)]
            )
            first = {
                path.name: path.read_bytes()
                for path in sorted(output_path.iterdir())
            }
            second_status = main(
                ["assess", "--plan", str(plan_path), "--out", str(output_path)]
            )
            second = {
                path.name: path.read_bytes()
                for path in sorted(output_path.iterdir())
            }

            self.assertEqual((first_status, second_status), (0, 0))
            self.assertEqual(
                set(first),
                {"assessment.json", "reachability.csv", "summary.md"},
            )
            self.assertEqual(first, second)
```

Also assert:

- CSV header is exactly the seven approved columns;
- CSV rows are scenario-major and horizon-minor in input order;
- JSON has a final newline and contains no input/output path or timestamp;
- Markdown uses “scenario-implied” and does not use “predicted” or “promised”;
- malformed input returns 1, writes nothing, and does not echo a sentinel from the plan;
- computation failure returns 1 and writes nothing;
- a missing input or unwritable output returns 1 with a short generic error.
- an existing output directory's unrelated files are left untouched; the CLI writes or replaces only the three documented names and never cleans the directory.

- [ ] **Step 3: Run the CLI test and confirm the expected failure**

```bash
python -m unittest tests.test_cli.CliTest -v
```

Expected: missing `evidence_reach.cli` or `main` failure.

- [ ] **Step 4: Implement the thin CLI adapter**

Create `src/evidence_reach/cli.py` with:

```python
def main(argv: Sequence[str] | None = None) -> int:
    """Run the single EvidenceReach command and return 0 or 1."""
```

Implementation order is mandatory:

1. parse `assess --plan PLAN.json --out RESULT_DIRECTORY`;
2. read exact plan bytes;
3. call `assess(plan_bytes)`;
4. render JSON, CSV, and Markdown completely in memory;
5. only after successful validation, computation, and rendering, create the output directory and replace the three documented files.

Serialize JSON with `ensure_ascii=False`, `indent=2`, and one trailing newline. Serialize CSV with `lineterminator="\n"` and this exact header:

```python
CSV_FIELDS = (
    "scenario_id",
    "horizon_days",
    "horizon_date",
    "scenario_implied_matured_n",
    "required_n",
    "state",
    "earliest_target_date",
)
```

The Markdown summary must report current mature N, required N, adjusted alpha, current power/MDE when available, and one short line per scenario. It must label all reachability as scenario-implied and include the four fixed limitations without making a forecast or promise.

Map all failure classes to short messages that do not include raw JSON or path values:

```text
evidence-reach: invalid plan: FIELD: REASON
evidence-reach: unable to read plan
evidence-reach: calculation failed
evidence-reach: unable to write results
```

Make module execution invoke the same entry point:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the focused CLI and full suites**

```bash
python -m unittest tests.test_cli.CliTest -v
python -m unittest discover -s tests -v
```

Expected: success writes exactly the three documented names and leaves unrelated files untouched; validation and computation failures return 1 without writing result files; every unit test passes. An I/O failure also returns 1, but the design does not promise a cross-file transaction if the operating system fails midway through three writes.

- [ ] **Step 6: Run the installed synthetic example twice and compare hashes**

```bash
python -m pip install -e .
python -m evidence_reach.cli assess --plan examples/SYNTHETIC_plan.json --out /tmp/evidence-reach-result-a
python -m evidence_reach.cli assess --plan examples/SYNTHETIC_plan.json --out /tmp/evidence-reach-result-b
shasum -a 256 /tmp/evidence-reach-result-a/assessment.json /tmp/evidence-reach-result-b/assessment.json
shasum -a 256 /tmp/evidence-reach-result-a/reachability.csv /tmp/evidence-reach-result-b/reachability.csv
shasum -a 256 /tmp/evidence-reach-result-a/summary.md /tmp/evidence-reach-result-b/summary.md
```

Expected: each A/B pair has the same hash. The three different formats need not share a hash with each other.

- [ ] **Step 7: Conditional local commit checkpoint**

Run only after separate authorization:

```bash
git add src/evidence_reach/cli.py tests/test_cli.py examples/SYNTHETIC_plan.json
git commit -m "feat: add deterministic CLI assessment outputs"
```

---

## Task 5: Public documentation, license, and CI

**Files:**

- Create: `README.md`
- Create: `LICENSE`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the five-minute README**

Keep one short README with these sections only:

1. what EvidenceReach answers;
2. what it does not claim;
3. installation;
4. one synthetic CLI run;
5. output files and state meanings;
6. Python API using `Path(...).read_bytes()` and `assess(plan_bytes)`;
7. statistical method and public comparison references;
8. privacy and synthetic-data boundary;
9. dependency and license.

Use this run command:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out result
```

State explicitly:

- one-sample observations and precomputed paired differences use the same calculation;
- reachability is scenario-implied deterministic arithmetic, not a forecast;
- users should not put secrets, personal data, account information, holdings, trades, or private evidence into plans, paths, or issue reports;
- EvidenceReach contains no market adapter and performs no network access;
- SciPy is a BSD-licensed runtime dependency;
- there is no claimed release, user adoption, external validation, or return outcome.

Verify manually that the README includes the exact external reference commands, tool/version labels, and frozen values used by `tests/test_power.py`; do not describe an approximate check as exact.

- [ ] **Step 2: Add the canonical Apache License 2.0 text**

Create `LICENSE` with the unmodified canonical Apache License 2.0 text. Public attribution in project metadata and README is `Copyright 2026 liver-detox`.

- [ ] **Step 3: Add the minimal Python-version CI matrix**

Create `.github/workflows/ci.yml` with one job, no publishing permissions, and no external services:

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -e .
      - run: python -m unittest discover -s tests -v
      - run: evidence-reach assess --plan examples/SYNTHETIC_plan.json --out synthetic-result
```

- [ ] **Step 4: Verify documentation commands and package metadata locally**

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out /tmp/evidence-reach-readme-check
python -m pip wheel . --no-deps --wheel-dir /tmp/evidence-reach-wheel-check
```

Expected: installation, all tests, synthetic run, and wheel build succeed.

- [ ] **Step 5: Conditional local commit checkpoint**

Run only after separate authorization:

```bash
git add README.md LICENSE .github/workflows/ci.yml
git commit -m "docs: prepare EvidenceReach public source package"
```

---

## Task 6: Completion audit without publication

**Files:**

- Verify all planned repository files; modify only a file whose failed check requires a correction.

- [ ] **Step 1: Run the complete test suite in a fresh local environment**

```bash
python -m venv /tmp/evidence-reach-verification-venv
source /tmp/evidence-reach-verification-venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

Expected: every test passes. CI must later confirm the same result separately on Python 3.12, 3.13, and 3.14 before a source release is claimed ready.

- [ ] **Step 2: Verify deterministic output and the exact public tree**

```bash
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out /tmp/evidence-reach-final-a
evidence-reach assess --plan examples/SYNTHETIC_plan.json --out /tmp/evidence-reach-final-b
diff -ru /tmp/evidence-reach-final-a /tmp/evidence-reach-final-b
find . -type f -not -path './.git/*' -not -path './.venv/*' -not -path '*/__pycache__/*' | sort
```

Expected: `diff` prints nothing. The public tree contains only the approved source, tests, synthetic example, design, implementation plan, README, license, metadata, and CI workflow.

- [ ] **Step 3: Run a narrow privacy and coupling scan**

Search the candidate tree for private-project names, real securities or account terms, email addresses, absolute home paths, credential-shaped strings, copied report names, and provider/API references. Review every match manually; generic warnings in README are allowed, but private identifiers and operational integrations are not.

Also verify:

- the example contains `SYNTHETIC` identifiers only;
- no file imports a module outside Python, SciPy, or `evidence_reach`;
- no production file opens a network connection;
- `pyproject.toml` has only SciPy as a runtime dependency;
- the clean project is not nested inside or linked to the private repository.

- [ ] **Step 4: Check all seven completion criteria against evidence**

Record each criterion as pass or fail in the implementation handoff:

1. fresh install and synthetic run;
2. supported-version tests;
3. independent statistical reference checks;
4. repeated-output identity;
5. generic and synthetic-only public tree;
6. five-minute README path; and
7. privacy and dependency-license review.

Do not describe v0.1 as complete while any criterion is unverified. Do not claim GitHub publication, release, adoption, ecosystem impact, or OpenAI program eligibility unless separate evidence later establishes it.

- [ ] **Step 5: Present the local source-preparation result and stop for authorization**

Report:

- files created;
- tests and environments actually run;
- deterministic-output result;
- privacy/isolation result;
- unresolved failures, if any; and
- the next separately authorized choice: local Git initialization/commit, GitHub publication preparation, or further review.

Do not initialize Git, commit, create a remote, push, upload, tag, or release as part of this task unless the user has explicitly granted that later authorization.
