# EvidenceReach v0.1 Design

- Status: public; v0.1.0 released 2026-08-22
- Date: 2026-08-21
- Public maintainer: `liver-detox`
- License: Apache License 2.0

## 1. Purpose

EvidenceReach is a small local tool for research leads, project managers, and
independent researchers. It answers one planning question:

> Given an explicitly specified effect, target power, and evidence-supply
> scenario, how many mature units are required and can that threshold be
> reached within the collection-and-maturity term?

The tool joins two calculations that are often kept separate:

1. statistical power, minimum detectable effect (MDE), and required sample
   size for a two-sided one-sample t test applied either to observations or
   to precomputed paired differences; and
2. deterministic, scenario-implied reachability of the required sample size.

EvidenceReach is a planning and audit aid. It is not a forecasting engine, a
proof that observations are valid or independent, or a substitute for
statistical advice.

## 2. v0.1 scope

### Included

- Two-sided one-sample t power analysis, including precomputed paired
  differences.
- Exact noncentral-t evaluation through SciPy.
- Current power, current MDE, and minimum required sample size.
- Bonferroni adjustment for one explicitly fixed comparison family.
- Current mature count, dated pending batches, a maturity lag, and a final
  collection date.
- Multiple named supply-rate scenarios and multiple calendar-day horizons.
- One Python API operation and one command-line operation.
- Deterministic JSON, CSV, and short Markdown output.
- One fully synthetic example.

### Excluded

- Independent two-sample tests, proportions, regression, sequential tests,
  simulation power, cluster inference, one-sided tests, and adaptive designs.
- Automatic judgments about evidence quality, eligibility, independence, or
  truth.
- Raw observations, evidence text, personal data, accounts, positions,
  transactions, market data, or provider integrations.
- Network access, scheduled collection, databases, web interfaces, user
  accounts, plugins, and adapters.
- Investment recommendations, performance promises, or authority to act.
- Certification that a user-supplied plan was genuinely preregistered.

Features outside this list require evidence of real user demand and a later
design decision. They are not placeholders for v0.1.

## 3. Architecture

The public package is `evidence_reach`. It has four implementation modules:

- `power.py`: noncentral-t power, MDE, and required-N calculations.
- `reachability.py`: deterministic scenario projection and target-date search.
- `core.py`: plan validation and composition of the two calculations.
- `cli.py`: JSON input and JSON/CSV/Markdown output.

`evidence_reach.assess(plan)` is the single public operation. It performs no
file or network I/O. The CLI is a thin adapter around that operation.

There is one direct runtime dependency: `scipy>=1.18,<2`. The package requires
`python>=3.12,<3.15`, giving an initial compatibility target of Python 3.12
through 3.14. SciPy is used rather than a hand-written noncentral-t
approximation. NumPy is installed transitively by SciPy and is not part of the
public EvidenceReach API.

## 4. Input contract

The CLI accepts one UTF-8 JSON plan. Unknown fields are rejected so that a
misspelled assumption cannot be silently ignored.

```json
{
  "schema_version": "1",
  "as_of_date": "2030-01-01",
  "analysis": {
    "effect": 2.0,
    "difference_sd": 8.0,
    "alpha": 0.05,
    "target_power": 0.8,
    "comparison_count": 1
  },
  "sampling": {
    "current_matured_n": 5,
    "pending_batches": [
      {"count": 3, "maturity_date": "2030-02-15"}
    ],
    "maturity_lag_days": 28,
    "collection_end_date": "2030-07-01"
  },
  "horizons_days": [90, 180, 365],
  "scenarios": [
    {"id": "SYNTHETIC_LOW", "eligible_units_per_30_days": 2.0},
    {"id": "SYNTHETIC_BASE", "eligible_units_per_30_days": 4.0},
    {"id": "SYNTHETIC_HIGH", "eligible_units_per_30_days": 6.0}
  ]
}
```

The effect and difference standard deviation use the same user-defined unit.
For a paired design, the caller first reduces each pair to one difference;
`effect` is the target mean difference and `difference_sd` is the standard
deviation of those differences. For a conventional one-sample design,
`difference_sd` is the standard deviation of the observations. EvidenceReach
does not need a separate design flag because both inputs use the same
one-sample t calculation.

`current_matured_n` is the count the caller has already judged analyzable.
EvidenceReach does not independently validate that judgment. A pending batch
contains only a count and maturity date; no observation identifiers or content
are accepted.

Validation rules are deliberately small:

- `effect` and `difference_sd` are finite positive numbers.
- `alpha` and `target_power` are finite numbers strictly between zero and one.
- `comparison_count` is a positive integer.
- `current_matured_n` and `maturity_lag_days` are non-negative integers.
- Every pending count is positive and every pending maturity date is later
  than `as_of_date`; the current-plus-pending aggregate must not exceed
  `sys.maxsize`, a computational count bound.
- `collection_end_date` is not earlier than `as_of_date`.
- Horizons are unique, strictly increasing positive integers.
- At least one scenario exists; scenario IDs are non-empty and unique; rates
  are finite and non-negative, with magnitude no greater than the maximum
  finite binary64 value. This is a computational-domain bound, not a business
  cap.

## 5. Statistical method

Only a two-sided one-sample t calculation is supported. Paired studies use the
same calculation after the caller forms one value per pair. For each integer
sample size `n >= 2`:

```text
adjusted_alpha = alpha / comparison_count
df             = n - 1
critical_t     = t.isf(adjusted_alpha / 2, df)
noncentrality  = abs(effect / difference_sd) * sqrt(n)
power          = nct.sf(critical_t, df, noncentrality)
                 + nct.cdf(-critical_t, df, noncentrality)
```

The survival function is used for the upper tail to avoid subtraction error.

- Current power evaluates this equation at `current_matured_n`.
- Current MDE numerically inverts the equation for the smallest positive
  effect that reaches `target_power`.
- Required N is the smallest integer `n >= 2` that reaches `target_power` for
  the supplied effect.
- If `current_matured_n < 2`, current power and current MDE are reported as
  unavailable; required N is still computed.

Bonferroni is reported as a conservative adjustment for the user-declared
fixed family. EvidenceReach does not claim family-wise control if the caller
omits or later changes comparisons.

## 6. Reachability method

Reachability is deterministic scenario arithmetic, not a probability forecast.
Each rate means eligible units per 30 calendar days under that named scenario.
Its JSON number lexeme is interpreted as an exact decimal for whole-unit
flooring; it is not first rounded to a binary floating-point value. A positive
rate that is provably too small to yield one whole unit for the available days
returns zero before constructing an exact rational value.

For scenario rate `r` and evaluation date `d`:

```text
eligible_cutoff = min(collection_end_date, d - maturity_lag_days)
eligible_days   = max(0, eligible_cutoff - as_of_date)
new_matured     = floor(exact_decimal(r) * eligible_days / 30)
pending_matured = sum(batch.count where batch.maturity_date <= d)
total_matured   = current_matured_n + pending_matured + new_matured
```

The date interval is half-open at the start: new supply begins after
`as_of_date`. The final collection date is included. No new units enter after
that date, but units already in the pipeline may mature afterward. An explicit
pending batch's `maturity_date` is already its final maturity date; the global
lag is not applied to that batch again.

Each horizon is evaluated at `as_of_date + horizon_days` using calendar-date
addition. For example, with `as_of_date=2030-01-01`, a 30-day horizon is
evaluated on `2030-01-31`. With a 28-day lag and a later collection end, two
days of new supply can have matured by that evaluation date.

For every scenario and requested horizon, the result reports the
scenario-implied whole mature count. It also finds the earliest calendar date
at which `total_matured >= required_n`. The search ends after the later of:

- `collection_end_date + maturity_lag_days`; and
- the latest explicit pending maturity date, when any pending batch exists.

When there is no pending batch, the search end is simply
`collection_end_date + maturity_lag_days`.

If the threshold is not reached by then, the state is
`SCENARIO_NOT_REACHABLE_WITHIN_TERM`. Other states are
`SCENARIO_REACHABLE_WITHIN_TERM` and `ALREADY_AT_REQUIRED_N`.

## 7. CLI and outputs

The only command is:

```text
evidence-reach assess --plan PLAN.json --out RESULT_DIRECTORY
```

After successful validation and calculation, the CLI creates or replaces only
these three named files inside the output directory:

- `assessment.json`: the complete machine-readable result.
- `reachability.csv`: one row per scenario and horizon.
- `summary.md`: a short human-readable interpretation.

`assessment.json` contains these required top-level fields:

- `schema_version`;
- `plan_sha256`;
- `method`;
- `assumptions`;
- `statistics`;
- `reachability`; and
- `limitations`.

`statistics` contains `adjusted_alpha`, `current_matured_n`, `current_power`,
`current_mde`, `required_n`, and `power_at_required_n`. `reachability` contains
the same rows as the CSV. The CSV columns are:

```text
scenario_id,horizon_days,horizon_date,scenario_implied_matured_n,
required_n,state,earliest_target_date
```

The result does not contain the input path, output path, wall-clock timestamp,
host details, or a copy of the raw plan.

JSON keys, CSV rows, and scenario rows have stable ordering. Calculation uses
unrounded floating-point values; final machine-facing values normally use
Python's `round(value, 12)`, but retain the original finite nonzero value when
rounding would produce zero. CSV and Markdown are derived from that normalized
result. The summary uses restrained
human-readable rounding and always says
"scenario-implied", never "predicted" or "promised".

## 8. Errors

The library raises a typed validation error containing only field locations and
short reasons. It does not echo the complete plan. The CLI has two exit
statuses:

- `0`: success;
- `1`: invalid input, I/O failure, or computation failure.

No output files are written when validation or computation fails. The tool has
no logging subsystem, telemetry, retry loop, or automatic correction of user
assumptions.

## 9. Minimal repository

```text
evidence-reach/
  README.md
  LICENSE
  pyproject.toml
  src/evidence_reach/
    __init__.py
    core.py
    power.py
    reachability.py
    cli.py
  tests/
    test_power.py
    test_reachability.py
    test_cli.py
  examples/
    SYNTHETIC_plan.json
  docs/design/
    2026-08-21-evidence-reach-design.md
  .github/workflows/ci.yml
```

The project uses the standard library `unittest` runner. It does not add a
formatter, linter, documentation generator, website, or release automation in
v0.1.

## 10. Verification

### Statistical tests

- Frozen independent reference values across several degrees of freedom,
  alpha levels, powers, effects, and standard deviations.
- Zero effect returns adjusted alpha within numerical tolerance.
- Power increases with effect and N.
- MDE decreases with N.
- MDE inversion returns target power within `1e-6`.
- Required N reaches target power while `N - 1` does not.
- Bonferroni uses exactly `alpha / comparison_count`.

### Reachability tests

- Already reached, zero supply, and unreachable cases.
- Pending batches before and after each horizon.
- Maturity-lag and collection-end boundaries.
- Monotonic counts across horizons and saturation after the final maturity.
- Earliest target-date selection and whole-unit flooring.

### Contract and CLI tests

- Every listed validation rule.
- Unknown-field rejection.
- One end-to-end synthetic CLI run.
- Stable repeated output and absence of machine paths or timestamps.
- Only the three documented result files are created.

CI runs the same tests on supported Python versions. The exact supported matrix
is Python 3.12, 3.13, and 3.14 for the initial source release.

## 11. Isolation, privacy, and licensing

EvidenceReach is built in a new local directory and will not inherit another
project's Git history. The implementation is a clean rewrite of approved
generic behavior. Private source files, generated reports, hashes, identifiers,
dates, market semantics, and datasets are not copied.

The public example uses only invented dates and values and carries a visible
`SYNTHETIC` label. The runtime performs no network access and accepts no raw
evidence content. The README will tell users not to place secrets or personal
data in plans, paths, or issue reports.

The planned project license is Apache License 2.0 under the public identity
`liver-detox`. SciPy's BSD-licensed dependency and version range are disclosed
in the README and package metadata.

## 12. Completion criteria

v0.1 source preparation is complete only when:

1. a new environment can install the project and run the synthetic example;
2. all tests pass on every declared Python version;
3. reference checks support the public statistical claims;
4. repeated runs on identical input produce identical output;
5. the public tree contains only generic code and synthetic material;
6. the README lets a new user run one assessment within five minutes; and
7. a final privacy, dependency-license, and public-file review finds no
   unresolved issue.

A GitHub repository, Git commit, remote push, formal release, package-index
release, users, adoption, or ecosystem impact is not implied by this design.
Each publication step requires separate authorization and evidence.

## 13. Current facts and planned work

Established at design approval:

- The product purpose, audience, scope, architecture, input/output model,
  statistical boundary, reachability semantics, and verification standard are
  approved.
- The public implementation is required to be isolated and synthetic-only.

Not yet established:

- The public package or CLI exists.
- The statistical reference suite passes.
- The synthetic example runs.
- A local Git repository or public GitHub repository exists.
- Any release, user, adoption, or external validation exists.
