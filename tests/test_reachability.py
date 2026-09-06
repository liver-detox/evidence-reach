import unittest
from datetime import date

from evidence_reach.reachability import (
    PendingBatch,
    Scenario,
    build_reachability_rows,
    build_summary_rows,
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

    def test_zero_rate_without_pending_is_unreachable(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 31),
            maturity_lag_days=28,
            current_matured_n=5,
            pending_batches=(),
            horizons_days=(90,),
            scenarios=(Scenario(id="ZERO", eligible_units_per_30_days=0.0),),
            required_n=6,
        )
        self.assertEqual(rows[0]["state"], "SCENARIO_NOT_REACHABLE_WITHIN_TERM")
        self.assertIsNone(rows[0]["earliest_target_date"])

    def test_pending_batch_after_collection_end_is_in_search_term(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 10),
            maturity_lag_days=10,
            current_matured_n=0,
            pending_batches=(PendingBatch(count=3, maturity_date=date(2030, 1, 15)),),
            horizons_days=(14,),
            scenarios=(Scenario(id="ZERO", eligible_units_per_30_days=0.0),),
            required_n=3,
        )
        self.assertEqual(rows[0]["state"], "SCENARIO_REACHABLE_WITHIN_TERM")
        self.assertEqual(rows[0]["earliest_target_date"], "2030-01-15")

    def test_summary_uses_the_full_term_not_the_last_requested_horizon(self) -> None:
        summary_rows = build_summary_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 31),
            maturity_lag_days=10,
            current_matured_n=2,
            pending_batches=(),
            scenarios=(
                Scenario(id="REACHES", eligible_units_per_30_days=30.0),
                Scenario(id="DOES_NOT_REACH", eligible_units_per_30_days=0.0),
            ),
            required_n=12,
        )
        self.assertEqual(
            summary_rows,
            [
                {
                    "scenario_id": "REACHES",
                    "required_n": 12,
                    "term_end_date": "2030-02-10",
                    "mature_n_at_term_end": 32,
                    "mature_n_gap": 0,
                    "earliest_target_date": "2030-01-21",
                },
                {
                    "scenario_id": "DOES_NOT_REACH",
                    "required_n": 12,
                    "term_end_date": "2030-02-10",
                    "mature_n_at_term_end": 2,
                    "mature_n_gap": 10,
                    "earliest_target_date": None,
                },
            ],
        )

    def test_no_pending_search_ends_at_collection_end_plus_lag(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 2),
            maturity_lag_days=2,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(3,),
            scenarios=(Scenario(id="DAILY", eligible_units_per_30_days=30.0),),
            required_n=1,
        )
        self.assertEqual(rows[0]["earliest_target_date"], "2030-01-04")

    def test_final_collection_date_contributes_and_supply_then_saturates(self) -> None:
        kwargs = dict(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 31),
            maturity_lag_days=5,
            current_matured_n=0,
            pending_batches=(),
            eligible_units_per_30_days=30.0,
        )
        self.assertEqual(implied_matured_n(evaluation_date=date(2030, 2, 4), **kwargs), 29)
        self.assertEqual(implied_matured_n(evaluation_date=date(2030, 2, 5), **kwargs), 30)
        self.assertEqual(implied_matured_n(evaluation_date=date(2030, 3, 1), **kwargs), 30)

    def test_zero_maturity_lag(self) -> None:
        count = implied_matured_n(
            evaluation_date=date(2030, 1, 31),
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 1, 31),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            eligible_units_per_30_days=30.0,
        )
        self.assertEqual(count, 30)

    def test_counts_are_monotonic_across_increasing_horizons(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 12, 31),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(30, 60, 90),
            scenarios=(Scenario(id="BASE", eligible_units_per_30_days=4.0),),
            required_n=99,
        )
        counts = [row["scenario_implied_matured_n"] for row in rows]
        self.assertEqual(counts, sorted(counts))

    def test_earliest_target_date_is_first_passing_date(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 2, 1),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(2,),
            scenarios=(Scenario(id="DAILY", eligible_units_per_30_days=30.0),),
            required_n=1,
        )
        self.assertEqual(rows[0]["earliest_target_date"], "2030-01-02")

    def test_scenario_rate_flooring_never_creates_fractional_units(self) -> None:
        count = implied_matured_n(
            evaluation_date=date(2030, 1, 31),
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 12, 31),
            maturity_lag_days=0,
            current_matured_n=1,
            pending_batches=(),
            eligible_units_per_30_days=2.9,
        )
        self.assertEqual(count, 3)
        self.assertIsInstance(count, int)

    def test_decimal_rate_flooring_sets_the_exact_first_passing_date(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 4, 11),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(100,),
            scenarios=(Scenario(id="DECIMAL", eligible_units_per_30_days=5.1),),
            required_n=17,
        )
        self.assertEqual(
            rows[0],
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

    def test_horizon_date_uses_exact_calendar_day_addition(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(2030, 1, 1),
            collection_end_date=date(2030, 12, 31),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(31,),
            scenarios=(Scenario(id="ZERO", eligible_units_per_30_days=0.0),),
            required_n=1,
        )
        self.assertEqual(rows[0]["horizon_date"], "2030-02-01")

    def test_search_at_date_max_does_not_advance_past_inclusive_end(self) -> None:
        rows = build_reachability_rows(
            as_of_date=date(9999, 12, 30),
            collection_end_date=date(9999, 12, 31),
            maturity_lag_days=0,
            current_matured_n=0,
            pending_batches=(),
            horizons_days=(1,),
            scenarios=(Scenario(id="ZERO", eligible_units_per_30_days=0.0),),
            required_n=1,
        )
        self.assertEqual(rows[0]["state"], "SCENARIO_NOT_REACHABLE_WITHIN_TERM")

    def test_positive_lag_at_date_min_has_zero_eligible_days(self) -> None:
        count = implied_matured_n(
            evaluation_date=date.min,
            as_of_date=date.min,
            collection_end_date=date.min,
            maturity_lag_days=1,
            current_matured_n=0,
            pending_batches=(),
            eligible_units_per_30_days=30.0,
        )
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
