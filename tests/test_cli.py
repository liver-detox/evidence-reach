import csv
import io
import hashlib
import json
import math
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidence_reach import PlanValidationError, assess
from evidence_reach.cli import main
from evidence_reach.power import one_sample_t_power


def synthetic_plan() -> dict[str, object]:
    return {
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


def synthetic_plan_bytes() -> bytes:
    return json.dumps(
        synthetic_plan(), separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def plan_bytes(plan: object) -> bytes:
    return json.dumps(plan, separators=(",", ":"), allow_nan=True).encode("utf-8")


def scenario_rate_plan_bytes(rate_lexeme: str) -> bytes:
    plan = synthetic_plan()
    plan["sampling"].update(
        {
            "current_matured_n": 0,
            "pending_batches": [],
            "maturity_lag_days": 0,
            "collection_end_date": "2030-02-01",
        }
    )
    plan["horizons_days"] = [31]
    plan["scenarios"] = [
        {"id": "ADVERSARIAL", "eligible_units_per_30_days": "RATE_LEXEME"}
    ]
    encoded = plan_bytes(plan)
    return encoded.replace(b'"RATE_LEXEME"', rate_lexeme.encode("ascii"))


def pending_count_plan_bytes(count_lexeme: str) -> bytes:
    plan = synthetic_plan()
    plan["sampling"].update(
        {
            "current_matured_n": 1,
            "pending_batches": [
                {"count": "COUNT_LEXEME", "maturity_date": "2030-01-02"}
            ],
            "maturity_lag_days": 0,
            "collection_end_date": "2030-01-02",
        }
    )
    plan["horizons_days"] = [1]
    plan["scenarios"] = [
        {"id": "ZERO", "eligible_units_per_30_days": 0.0}
    ]
    encoded = plan_bytes(plan)
    return encoded.replace(b'"COUNT_LEXEME"', count_lexeme.encode("ascii"))


class AssessContractTest(unittest.TestCase):
    def test_assess_hashes_exact_input_bytes_and_returns_required_sections(self) -> None:
        raw = synthetic_plan_bytes()
        result = assess(raw)
        self.assertEqual(result["plan_sha256"], hashlib.sha256(raw).hexdigest())
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
        self.assertEqual(
            list(result["statistics"]),
            [
                "adjusted_alpha",
                "current_matured_n",
                "current_power",
                "current_mde",
                "required_n",
                "power_at_required_n",
            ],
        )
        self.assertEqual(
            list(result["assumptions"]),
            [
                "as_of_date",
                "effect",
                "difference_sd",
                "alpha",
                "target_power",
                "comparison_count",
                "maturity_lag_days",
                "collection_end_date",
            ],
        )
        self.assertEqual(
            list(result["reachability"][0]),
            [
                "scenario_id",
                "horizon_days",
                "horizon_date",
                "scenario_implied_matured_n",
                "required_n",
                "state",
                "earliest_target_date",
            ],
        )

    def test_fixed_method_limitations_and_recursive_float_rounding(self) -> None:
        plan = synthetic_plan()
        plan["analysis"]["effect"] = 1.2345678901239
        result = assess(plan_bytes(plan))
        self.assertEqual(
            result["method"],
            {
                "test": "two-sided one-sample t on observations or precomputed paired differences",
                "power_distribution": "noncentral t",
                "multiple_comparisons": "Bonferroni adjustment for a user-declared fixed family",
                "reachability": "deterministic scenario arithmetic",
            },
        )
        self.assertEqual(
            result["limitations"],
            [
                "Scenario-implied reachability is not a probability forecast or promise.",
                "EvidenceReach does not validate evidence quality, eligibility, independence, or truth.",
                "Bonferroni applies only to the fixed comparison family declared by the caller.",
                "This assessment is a planning aid, not statistical, financial, or investment advice.",
            ],
        )
        self.assertEqual(result["assumptions"]["effect"], 1.234567890124)

    def test_tiny_alpha_and_equal_extreme_scales_are_legal_api_inputs(self) -> None:
        tiny_alpha_plan = synthetic_plan()
        tiny_alpha_plan["analysis"]["alpha"] = 1e-16
        tiny_alpha_result = assess(plan_bytes(tiny_alpha_plan))
        self.assertGreaterEqual(tiny_alpha_result["statistics"]["required_n"], 2)
        self.assertEqual(tiny_alpha_result["assumptions"]["alpha"], 1e-16)
        self.assertEqual(tiny_alpha_result["statistics"]["adjusted_alpha"], 1e-16)

        extreme_scale_plan = synthetic_plan()
        extreme_scale_plan["analysis"].update(
            {
                "effect": 1e308,
                "difference_sd": 1e308,
                "target_power": 0.04,
            }
        )
        extreme_scale_plan["sampling"]["current_matured_n"] = 4
        extreme_scale_result = assess(plan_bytes(extreme_scale_plan))
        self.assertAlmostEqual(
            extreme_scale_result["statistics"]["current_power"],
            0.288752416402,
            places=12,
        )

    def test_decimal_scenario_rates_keep_json_number_flooring_semantics(self) -> None:
        decimal_plan = synthetic_plan()
        decimal_plan["analysis"].update({"effect": 0.73, "difference_sd": 1.0})
        decimal_plan["sampling"].update(
            {
                "current_matured_n": 0,
                "pending_batches": [],
                "maturity_lag_days": 0,
                "collection_end_date": "2030-04-11",
            }
        )
        decimal_plan["horizons_days"] = [100]
        decimal_plan["scenarios"] = [
            {"id": "DECIMAL", "eligible_units_per_30_days": 5.1}
        ]
        decimal_result = assess(plan_bytes(decimal_plan))
        self.assertEqual(decimal_result["statistics"]["required_n"], 17)
        self.assertEqual(
            decimal_result["reachability"][0],
            {
                "scenario_id": "DECIMAL",
                "horizon_days": 100,
                "horizon_date": "2030-04-11",
                "scenario_implied_matured_n": 17,
                "required_n": 17,
                "state": "SCENARIO_REACHABLE_WITHIN_TERM",
                "earliest_target_date": "2030-04-11",
            },
        )

        huge_rate_plan = synthetic_plan()
        huge_rate_plan["analysis"].update(
            {"effect": 1.0, "difference_sd": 1.0, "target_power": 0.1}
        )
        huge_rate_plan["sampling"].update(
            {
                "current_matured_n": 0,
                "pending_batches": [],
                "maturity_lag_days": 0,
                "collection_end_date": "2030-02-01",
            }
        )
        huge_rate_plan["horizons_days"] = [31]
        huge_rate_plan["scenarios"] = [
            {"id": "FINITE_HUGE", "eligible_units_per_30_days": 1e308}
        ]
        huge_rate_result = assess(plan_bytes(huge_rate_plan))
        self.assertEqual(
            huge_rate_result["reachability"][0]["scenario_implied_matured_n"],
            10**308 * 31 // 30,
        )

    def test_scenario_rate_above_binary64_domain_is_field_safe(self) -> None:
        raw = scenario_rate_plan_bytes("1e5000")
        with self.assertRaises(PlanValidationError) as caught:
            assess(raw)
        self.assertEqual(
            str(caught.exception),
            "scenarios[0].eligible_units_per_30_days: must be a finite number",
        )
        self.assertNotIn("1e5000", str(caught.exception))

    def test_decimal_parser_extreme_exponent_is_field_safe(self) -> None:
        raw = scenario_rate_plan_bytes("1e9999999999999999999")
        with self.assertRaises(PlanValidationError) as caught:
            assess(raw)
        self.assertEqual(str(caught.exception), "plan: must be valid JSON")

    def test_tiny_decimal_rate_returns_zero_without_fraction_construction(self) -> None:
        raw = scenario_rate_plan_bytes("1e-1000000000000000000")
        with patch(
            "evidence_reach.reachability.Fraction",
            side_effect=AssertionError("tiny rate must be short-circuited"),
        ):
            result = assess(raw)
        self.assertEqual(
            result["reachability"][0]["scenario_implied_matured_n"], 0
        )
        json.dumps(result)

    def test_current_statistics_are_unavailable_below_two_mature_units(self) -> None:
        plan = synthetic_plan()
        plan["sampling"]["current_matured_n"] = 1
        result = assess(plan_bytes(plan))
        self.assertIsNone(result["statistics"]["current_power"])
        self.assertIsNone(result["statistics"]["current_mde"])
        self.assertGreaterEqual(result["statistics"]["required_n"], 2)

    def test_bonferroni_uses_declared_fixed_family(self) -> None:
        plan = synthetic_plan()
        plan["analysis"]["comparison_count"] = 4
        result = assess(plan_bytes(plan))
        statistics = result["statistics"]
        self.assertEqual(statistics["adjusted_alpha"], 0.0125)
        self.assertAlmostEqual(
            statistics["current_power"],
            one_sample_t_power(
                effect=2.0, difference_sd=8.0, n=5, alpha=0.0125
            ),
            places=12,
        )
        self.assertAlmostEqual(
            statistics["power_at_required_n"],
            one_sample_t_power(
                effect=2.0,
                difference_sd=8.0,
                n=statistics["required_n"],
                alpha=0.0125,
            ),
            places=12,
        )

    def test_current_mde_is_zero_when_target_does_not_exceed_adjusted_alpha(self) -> None:
        plan = synthetic_plan()
        plan["analysis"].update({"alpha": 0.2, "target_power": 0.1})
        result = assess(plan_bytes(plan))
        self.assertEqual(result["statistics"]["current_mde"], 0.0)

    def test_reachability_rows_preserve_scenario_then_horizon_order(self) -> None:
        plan = synthetic_plan()
        plan["horizons_days"] = [30, 60]
        plan["scenarios"] = [
            {"id": "SECOND", "eligible_units_per_30_days": 2.0},
            {"id": "FIRST", "eligible_units_per_30_days": 4.0},
        ]
        result = assess(plan_bytes(plan))
        self.assertEqual(
            [
                (row["scenario_id"], row["horizon_days"])
                for row in result["reachability"]
            ],
            [("SECOND", 30), ("SECOND", 60), ("FIRST", 30), ("FIRST", 60)],
        )

    def test_unknown_field_is_rejected_without_echoing_plan(self) -> None:
        plan = synthetic_plan()
        plan["private_note"] = "SENSITIVE_SENTINEL"
        with self.assertRaises(PlanValidationError) as caught:
            assess(plan_bytes(plan))
        self.assertIn("private_note", str(caught.exception))
        self.assertNotIn("SENSITIVE_SENTINEL", str(caught.exception))


class PlanValidationTest(unittest.TestCase):
    def assert_rejected(
        self,
        payload: object,
        field: str,
        rejected_value: object | None = None,
        *,
        raw_input: bool = False,
    ) -> None:
        assessment_input = payload if raw_input or isinstance(payload, bytes) else plan_bytes(payload)
        with self.assertRaises(PlanValidationError) as caught:
            assess(assessment_input)
        message = str(caught.exception)
        self.assertIn(field, message)
        if isinstance(assessment_input, bytes):
            raw_plan = assessment_input.decode("utf-8", errors="replace")
        else:
            raw_plan = str(assessment_input)
        self.assertNotIn(raw_plan, message)
        if rejected_value is not None:
            self.assertNotIn(str(rejected_value), message)

    def test_scalar_and_shape_validation(self) -> None:
        cases: list[tuple[str, object, str, object | None]] = []

        invalid_schema = synthetic_plan()
        invalid_schema["schema_version"] = "2"
        cases.append(("schema version", invalid_schema, "schema_version", "2"))
        cases.append(("non-object root", [], "plan", "[]"))

        for key, value in (("effect", math.inf), ("effect", 0), ("effect", -1), ("effect", True),
                           ("difference_sd", math.nan), ("difference_sd", 0),
                           ("difference_sd", -1), ("difference_sd", True)):
            plan = synthetic_plan()
            plan["analysis"][key] = value
            cases.append((f"invalid {key}", plan, f"analysis.{key}", value))

        for key, value in (("alpha", 0), ("alpha", 1), ("target_power", 0),
                           ("target_power", 1), ("alpha", True),
                           ("target_power", True)):
            plan = synthetic_plan()
            plan["analysis"][key] = value
            cases.append((f"invalid {key}", plan, f"analysis.{key}", value))

        for value in (0, -1, True):
            plan = synthetic_plan()
            plan["analysis"]["comparison_count"] = value
            cases.append(("invalid comparison count", plan, "analysis.comparison_count", value))

        for key in ("current_matured_n", "maturity_lag_days"):
            for value in (-1, True):
                plan = synthetic_plan()
                plan["sampling"][key] = value
                cases.append((f"invalid {key}", plan, f"sampling.{key}", value))

        for label, mutate, field, rejected_value in (
            ("zero pending count", lambda p: p["sampling"]["pending_batches"].__setitem__(0, {"count": 0, "maturity_date": "2030-02-15"}), "sampling.pending_batches[0].count", '"count":0'),
            ("negative pending count", lambda p: p["sampling"]["pending_batches"].__setitem__(0, {"count": -1, "maturity_date": "2030-02-15"}), "sampling.pending_batches[0].count", -1),
            ("boolean pending count", lambda p: p["sampling"]["pending_batches"].__setitem__(0, {"count": True, "maturity_date": "2030-02-15"}), "sampling.pending_batches[0].count", "true"),
            ("bad pending date", lambda p: p["sampling"]["pending_batches"].__setitem__(0, {"count": 3, "maturity_date": "2030-02-30"}), "sampling.pending_batches[0].maturity_date", "2030-02-30"),
            ("early pending date", lambda p: p["sampling"]["pending_batches"].__setitem__(0, {"count": 3, "maturity_date": "2030-01-01"}), "sampling.pending_batches[0].maturity_date", "2030-01-01"),
            ("early collection end", lambda p: p["sampling"].__setitem__("collection_end_date", "2029-12-31"), "sampling.collection_end_date", "2029-12-31"),
        ):
            plan = synthetic_plan()
            mutate(plan)
            cases.append((label, plan, field, rejected_value))

        for value, rejected_value in (
            ([], None),
            ([90, 90], 90),
            ([180, 90], 90),
            ([0], '"horizons_days":[0]'),
            ([-1], -1),
            ([True], "true"),
        ):
            plan = synthetic_plan()
            plan["horizons_days"] = value
            cases.append(("invalid horizons", plan, "horizons_days", rejected_value))

        for value, rejected_value in (
            ([], None),
            ([{"id": "", "eligible_units_per_30_days": 1.0}], '"id":""'),
            (
                [
                    {"id": "A", "eligible_units_per_30_days": 1.0},
                    {"id": "A", "eligible_units_per_30_days": 2.0},
                ],
                "A",
            ),
            ([{"id": "A", "eligible_units_per_30_days": -1}], -1),
            ([{"id": "A", "eligible_units_per_30_days": math.inf}], "Infinity"),
            ([{"id": "A", "eligible_units_per_30_days": True}], "true"),
        ):
            plan = synthetic_plan()
            plan["scenarios"] = value
            cases.append(("invalid scenarios", plan, "scenarios", rejected_value))

        for label, plan, field, rejected_value in cases:
            with self.subTest(label=label):
                self.assert_rejected(plan, field, rejected_value)

    def test_missing_and_unknown_fields_are_rejected_at_each_object_level(self) -> None:
        cases: list[tuple[str, object, str, object | None]] = []
        locations = (
            ((), "schema_version"),
            (("analysis",), "effect"),
            (("sampling",), "current_matured_n"),
            (("sampling", "pending_batches", 0), "count"),
            (("scenarios", 0), "id"),
        )
        for path, key in locations:
            plan = synthetic_plan()
            target = plan
            for component in path:
                target = target[component]
            del target[key]
            cases.append((f"missing {key}", plan, key, None))

            plan = synthetic_plan()
            target = plan
            for component in path:
                target = target[component]
            target["unexpected"] = "SECRET"
            cases.append((f"unknown {key} object", plan, "unexpected", "SECRET"))

        for label, plan, field, rejected_value in cases:
            with self.subTest(label=label):
                self.assert_rejected(plan, field, rejected_value)

    def test_decoding_and_json_errors_are_safe(self) -> None:
        for label, payload, field, rejected_value, raw_input in (
            ("invalid utf8", b"\xff", "plan", "\ufffd", False),
            ("malformed json", b'{"schema_version":"1"', "plan", "schema_version", False),
            ("non-bytes", "NON_BYTES_SENTINEL", "plan", "NON_BYTES_SENTINEL", True),
        ):
            with self.subTest(label=label):
                self.assert_rejected(
                    payload, field, rejected_value, raw_input=raw_input
                )

    def test_json_parser_value_errors_and_duplicate_keys_stay_field_safe(self) -> None:
        too_many_digits = b"9" * 4301
        self.assert_rejected(
            b'{"value":' + too_many_digits + b"}",
            "plan",
            too_many_digits.decode("ascii"),
        )
        with self.assertRaises(PlanValidationError) as caught:
            assess(b'{"schema_version":"1","schema_version":"1"}')
        self.assertEqual(
            str(caught.exception),
            "plan: must not contain duplicate object fields",
        )

    def test_noncanonical_iso_date_is_rejected(self) -> None:
        plan = synthetic_plan()
        plan["as_of_date"] = "20300101"
        self.assert_rejected(plan, "as_of_date", "20300101")


class BoundaryValidationTest(unittest.TestCase):
    assert_rejected = PlanValidationTest.assert_rejected

    def test_pending_count_carry_stays_in_computable_domain(self) -> None:
        raw_digits = "9" * 4300
        self.assert_rejected(
            pending_count_plan_bytes(raw_digits),
            "sampling.pending_batches[0].count",
            raw_digits,
        )

    def test_individually_valid_pending_counts_cannot_overflow_aggregate(self) -> None:
        plan = synthetic_plan()
        plan["sampling"].update(
            {
                "current_matured_n": 0,
                "pending_batches": [
                    {"count": sys.maxsize, "maturity_date": "2030-01-02"},
                    {"count": 1, "maturity_date": "2030-01-03"},
                ],
            }
        )
        self.assert_rejected(
            plan,
            "sampling.pending_batches[1].count",
        )

    def test_unrepresentable_numeric_and_date_inputs_are_field_safe(self) -> None:
        huge_integer = 10**400
        smallest_positive_float = float.fromhex("0x0.0000000000001p-1022")
        cases: list[tuple[str, object, str, object]] = []

        plan = synthetic_plan()
        plan["analysis"]["effect"] = huge_integer
        cases.append(("huge effect", plan, "analysis.effect", huge_integer))

        plan = synthetic_plan()
        plan["analysis"]["comparison_count"] = huge_integer
        cases.append(
            (
                "comparison count conversion overflow",
                plan,
                "analysis.comparison_count",
                huge_integer,
            )
        )

        plan = synthetic_plan()
        plan["analysis"].update(
            {"alpha": smallest_positive_float, "comparison_count": 2}
        )
        cases.append(
            (
                "comparison count alpha underflow",
                plan,
                "analysis.comparison_count",
                smallest_positive_float,
            )
        )

        plan = synthetic_plan()
        plan["sampling"]["current_matured_n"] = huge_integer
        cases.append(
            (
                "current mature count square-root overflow",
                plan,
                "sampling.current_matured_n",
                huge_integer,
            )
        )

        plan = synthetic_plan()
        plan["sampling"].update(
            {"collection_end_date": "9999-12-31", "maturity_lag_days": 1}
        )
        cases.append(
            (
                "collection maturity date overflow",
                plan,
                "sampling.maturity_lag_days",
                1,
            )
        )

        plan = synthetic_plan()
        plan.update({"as_of_date": "9999-12-31", "horizons_days": [1]})
        plan["sampling"].update(
            {"collection_end_date": "9999-12-31", "pending_batches": [], "maturity_lag_days": 0}
        )
        cases.append(
            ("horizon date overflow", plan, "horizons_days[0]", 1)
        )

        for label, plan, field, rejected_value in cases:
            with self.subTest(label=label):
                self.assert_rejected(plan, field, rejected_value)


class DerivedDomainValidationTest(unittest.TestCase):
    assert_rejected = PlanValidationTest.assert_rejected

    def test_zero_collection_term_allows_a_finite_high_rate(self) -> None:
        plan = synthetic_plan()
        plan["sampling"].update(
            {"collection_end_date": "2030-01-01", "pending_batches": []}
        )
        plan["scenarios"] = [
            {"id": "ZERO_TERM", "eligible_units_per_30_days": 1e308}
        ]
        result = assess(plan_bytes(plan))
        self.assertEqual(result["reachability"][0]["scenario_implied_matured_n"], 5)

    def test_finite_derived_domains_are_field_safe(self) -> None:
        smallest_positive_float = float.fromhex("0x0.0000000000001p-1022")
        cases: list[tuple[str, object, str, object]] = []

        plan = synthetic_plan()
        plan["analysis"].update(
            {"effect": 1e308, "difference_sd": smallest_positive_float}
        )
        cases.append(
            (
                "unrepresentable standardized effect",
                plan,
                "analysis",
                smallest_positive_float,
            )
        )

        plan = synthetic_plan()
        plan["sampling"]["current_matured_n"] = 10**308
        cases.append(
            (
                "current mature count outside scipy index range",
                plan,
                "sampling.current_matured_n",
                10**308,
            )
        )

        plan = synthetic_plan()
        plan["analysis"]["effect"] = smallest_positive_float
        plan["sampling"]["current_matured_n"] = 1
        cases.append(
            (
                "unrepresentable required sample search",
                plan,
                "analysis",
                smallest_positive_float,
            )
        )

        for label, plan, field, rejected_value in cases:
            with self.subTest(label=label):
                self.assert_rejected(plan, field, rejected_value)


class CliTest(unittest.TestCase):
    def run_main(self, plan_path: Path, output_path: Path) -> tuple[int, str]:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = main(
                ["assess", "--plan", str(plan_path), "--out", str(output_path)]
            )
        return status, stderr.getvalue()

    def run_main_with_streams(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_top_level_help_shows_the_assess_command(self) -> None:
        status, stdout, stderr = self.run_main_with_streams(["--help"])

        self.assertEqual(status, 0)
        self.assertIn("usage: evidence-reach", stdout)
        self.assertIn("assess", stdout)
        self.assertEqual(stderr, "")

    def test_assess_help_shows_required_options(self) -> None:
        status, stdout, stderr = self.run_main_with_streams(["assess", "--help"])

        self.assertEqual(status, 0)
        self.assertIn("usage: evidence-reach assess", stdout)
        self.assertIn("--plan", stdout)
        self.assertIn("--out", stdout)
        self.assertEqual(stderr, "")

    def test_missing_required_options_name_only_the_missing_option(self) -> None:
        missing_plan = self.run_main_with_streams(
            ["assess", "--out", "OUT_SENTINEL"]
        )
        missing_out = self.run_main_with_streams(
            ["assess", "--plan", "PLAN_SENTINEL"]
        )

        self.assertEqual(missing_plan, (1, "", "evidence-reach: missing required argument: --plan\n"))
        self.assertNotIn("OUT_SENTINEL", missing_plan[2])
        self.assertEqual(missing_out, (1, "", "evidence-reach: missing required argument: --out\n"))
        self.assertNotIn("PLAN_SENTINEL", missing_out[2])

    def test_unknown_option_uses_safe_invalid_arguments_message(self) -> None:
        result = self.run_main_with_streams(
            [
                "assess",
                "--plan",
                "PLAN_SENTINEL",
                "--out",
                "OUT_SENTINEL",
                "--unexpected",
                "UNKNOWN_SENTINEL",
            ]
        )

        self.assertEqual(result, (1, "", "evidence-reach: invalid arguments\n"))
        self.assertNotIn("UNKNOWN_SENTINEL", result[2])

    def test_success_writes_three_deterministic_documented_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan_path.write_bytes(synthetic_plan_bytes())

            first_status, first_error = self.run_main(plan_path, output_path)
            first = {
                path.name: path.read_bytes()
                for path in sorted(output_path.iterdir())
            }
            second_status, second_error = self.run_main(plan_path, output_path)
            second = {
                path.name: path.read_bytes()
                for path in sorted(output_path.iterdir())
            }

            self.assertEqual((first_status, second_status), (0, 0))
            self.assertEqual((first_error, second_error), ("", ""))
            self.assertEqual(
                set(first),
                {"assessment.json", "reachability.csv", "summary.md"},
            )
            self.assertEqual(first, second)

            assessment = first["assessment.json"]
            self.assertTrue(assessment.endswith(b"\n"))
            assessment_text = assessment.decode("utf-8")
            self.assertNotIn(str(plan_path), assessment_text)
            self.assertNotIn(str(output_path), assessment_text)
            self.assertNotIn("timestamp", assessment_text)

            csv_rows = list(csv.reader(io.StringIO(first["reachability.csv"].decode("utf-8"))))
            self.assertEqual(
                csv_rows[0],
                [
                    "scenario_id",
                    "horizon_days",
                    "horizon_date",
                    "scenario_implied_matured_n",
                    "required_n",
                    "state",
                    "earliest_target_date",
                ],
            )
            self.assertEqual(
                [(row[0], row[1]) for row in csv_rows[1:]],
                [
                    ("SYNTHETIC_LOW", "90"),
                    ("SYNTHETIC_LOW", "180"),
                    ("SYNTHETIC_LOW", "365"),
                    ("SYNTHETIC_BASE", "90"),
                    ("SYNTHETIC_BASE", "180"),
                    ("SYNTHETIC_BASE", "365"),
                    ("SYNTHETIC_HIGH", "90"),
                    ("SYNTHETIC_HIGH", "180"),
                    ("SYNTHETIC_HIGH", "365"),
                ],
            )

            summary = first["summary.md"].decode("utf-8").lower()
            self.assertIn("scenario-implied", summary)
            self.assertNotIn("predicted", summary)
            self.assertNotIn("promised", summary)
            self.assertEqual(
                sum(
                    line.startswith("- SYNTHETIC_")
                    for line in first["summary.md"].decode("utf-8").splitlines()
                ),
                3,
            )

    def test_invalid_plan_writes_nothing_and_hides_plan_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan = synthetic_plan()
            plan["private_note"] = "SENTINEL_DO_NOT_ECHO"
            plan_path.write_bytes(plan_bytes(plan))

            status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 1)
            self.assertFalse(output_path.exists())
            self.assertIn("evidence-reach: invalid plan:", error)
            self.assertNotIn("SENTINEL_DO_NOT_ECHO", error)

    def test_json_integer_limit_error_is_short_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            raw_digits = b"9" * 4301
            plan_path.write_bytes(b'{"value":' + raw_digits + b"}")

            status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 1)
            self.assertFalse(output_path.exists())
            self.assertEqual(
                error,
                "evidence-reach: invalid plan: plan: must be valid JSON\n",
            )
            self.assertNotIn(raw_digits.decode("ascii"), error)

    def test_pending_count_carry_is_invalid_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            raw_digits = "9" * 4300
            plan_path.write_bytes(pending_count_plan_bytes(raw_digits))

            status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 1)
            self.assertFalse(output_path.exists())
            self.assertIn(
                "evidence-reach: invalid plan: "
                "sampling.pending_batches[0].count:",
                error,
            )
            self.assertNotIn(raw_digits, error)

    def test_adversarial_decimal_rates_have_safe_cli_results(self) -> None:
        invalid_cases = (
            (
                "1e5000",
                "evidence-reach: invalid plan: "
                "scenarios[0].eligible_units_per_30_days: must be a finite number\n",
            ),
            (
                "1e9999999999999999999",
                "evidence-reach: invalid plan: plan: must be valid JSON\n",
            ),
        )
        for rate_lexeme, expected_error in invalid_cases:
            with self.subTest(rate_lexeme=rate_lexeme):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    plan_path = root / "plan.json"
                    output_path = root / "result"
                    plan_path.write_bytes(scenario_rate_plan_bytes(rate_lexeme))

                    status, error = self.run_main(plan_path, output_path)

                    self.assertEqual(status, 1)
                    self.assertFalse(output_path.exists())
                    self.assertEqual(error, expected_error)
                    self.assertNotIn(rate_lexeme, error)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan_path.write_bytes(
                scenario_rate_plan_bytes("1e-1000000000000000000")
            )
            with patch(
                "evidence_reach.reachability.Fraction",
                side_effect=AssertionError("tiny rate must be short-circuited"),
            ):
                status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 0)
            self.assertEqual(error, "")
            assessment = json.loads(
                (output_path / "assessment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                assessment["reachability"][0]["scenario_implied_matured_n"], 0
            )

    def test_calculation_failure_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan_path.write_bytes(synthetic_plan_bytes())

            with patch("evidence_reach.cli.assess", side_effect=RuntimeError):
                status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 1)
            self.assertFalse(output_path.exists())
            self.assertEqual(error, "evidence-reach: calculation failed\n")

    def test_missing_input_returns_short_generic_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status, error = self.run_main(root / "missing.json", root / "result")

            self.assertEqual(status, 1)
            self.assertEqual(error, "evidence-reach: unable to read plan\n")

    def test_unwritable_output_returns_short_generic_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "not-a-directory"
            plan_path.write_bytes(synthetic_plan_bytes())
            output_path.write_text("not a directory", encoding="utf-8")

            status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 1)
            self.assertEqual(error, "evidence-reach: unable to write results\n")

    def test_invalid_output_path_returns_short_generic_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            plan_path.write_bytes(synthetic_plan_bytes())

            status, error = self.run_main(plan_path, Path("bad\x00path"))

            self.assertEqual(status, 1)
            self.assertEqual(error, "evidence-reach: unable to write results\n")

    def test_preserves_unrelated_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            output_path = root / "result"
            plan_path.write_bytes(synthetic_plan_bytes())
            output_path.mkdir()
            unrelated = output_path / "keep.txt"
            unrelated.write_text("keep this", encoding="utf-8")

            status, error = self.run_main(plan_path, output_path)

            self.assertEqual(status, 0)
            self.assertEqual(error, "")
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep this")
            self.assertEqual(
                {path.name for path in output_path.iterdir()},
                {"assessment.json", "reachability.csv", "summary.md", "keep.txt"},
            )


if __name__ == "__main__":
    unittest.main()
