"""Deterministic scenario-based mature-evidence reachability."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class PendingBatch:
    count: int
    maturity_date: date


@dataclass(frozen=True)
class Scenario:
    id: str
    eligible_units_per_30_days: Decimal | float


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
    eligible_days = min(
        (collection_end_date - as_of_date).days,
        max(0, (evaluation_date - as_of_date).days - maturity_lag_days),
    )
    if isinstance(eligible_units_per_30_days, Decimal):
        decimal_rate = eligible_units_per_30_days
    else:
        decimal_rate = Decimal(str(eligible_units_per_30_days))
    if (
        eligible_days == 0
        or decimal_rate.is_zero()
        or (
            decimal_rate > 0
            and decimal_rate.adjusted() + len(str(eligible_days)) <= 0
        )
    ):
        new_matured = 0
    else:
        new_matured = Fraction(decimal_rate) * eligible_days // 30
    pending_matured = sum(
        batch.count for batch in pending_batches if batch.maturity_date <= evaluation_date
    )
    return current_matured_n + pending_matured + new_matured


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
    search_end = collection_end_date + timedelta(days=maturity_lag_days)
    if pending_batches:
        search_end = max(search_end, max(batch.maturity_date for batch in pending_batches))

    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        earliest_target_date: date | None = None
        if current_matured_n >= required_n:
            state = "ALREADY_AT_REQUIRED_N"
            earliest_target_date = as_of_date
        else:
            evaluation_date = as_of_date
            while evaluation_date <= search_end:
                if implied_matured_n(
                    evaluation_date=evaluation_date,
                    as_of_date=as_of_date,
                    collection_end_date=collection_end_date,
                    maturity_lag_days=maturity_lag_days,
                    current_matured_n=current_matured_n,
                    pending_batches=pending_batches,
                    eligible_units_per_30_days=scenario.eligible_units_per_30_days,
                ) >= required_n:
                    earliest_target_date = evaluation_date
                    break
                if evaluation_date == search_end:
                    break
                evaluation_date += timedelta(days=1)
            state = (
                "SCENARIO_REACHABLE_WITHIN_TERM"
                if earliest_target_date is not None
                else "SCENARIO_NOT_REACHABLE_WITHIN_TERM"
            )

        for horizon_days in horizons_days:
            horizon_date = as_of_date + timedelta(days=horizon_days)
            implied_count = implied_matured_n(
                evaluation_date=horizon_date,
                as_of_date=as_of_date,
                collection_end_date=collection_end_date,
                maturity_lag_days=maturity_lag_days,
                current_matured_n=current_matured_n,
                pending_batches=pending_batches,
                eligible_units_per_30_days=scenario.eligible_units_per_30_days,
            )
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "horizon_days": horizon_days,
                    "horizon_date": horizon_date.isoformat(),
                    "scenario_implied_matured_n": implied_count,
                    "required_n": required_n,
                    "state": state,
                    "earliest_target_date": (
                        earliest_target_date.isoformat()
                        if earliest_target_date is not None
                        else None
                    ),
                }
            )
    return rows
