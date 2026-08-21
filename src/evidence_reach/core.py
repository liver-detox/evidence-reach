"""Strict plan validation and pure EvidenceReach assessment composition."""

from datetime import date, timedelta
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import sys
from typing import Any

from .power import (
    minimum_detectable_effect,
    one_sample_t_power,
    required_sample_size,
)
from .reachability import PendingBatch, Scenario, build_reachability_rows


class PlanValidationError(ValueError):
    """A field location and short reason safe to show to a CLI user."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


_ROOT_FIELDS = {
    "schema_version",
    "as_of_date",
    "analysis",
    "sampling",
    "horizons_days",
    "scenarios",
}
_ANALYSIS_FIELDS = {
    "effect",
    "difference_sd",
    "alpha",
    "target_power",
    "comparison_count",
}
_SAMPLING_FIELDS = {
    "current_matured_n",
    "pending_batches",
    "maturity_lag_days",
    "collection_end_date",
}
_PENDING_BATCH_FIELDS = {"count", "maturity_date"}
_SCENARIO_FIELDS = {"id", "eligible_units_per_30_days"}
_MAX_SCENARIO_RATE = Decimal.from_float(sys.float_info.max)


def _reject(field: str, reason: str) -> None:
    raise PlanValidationError(field, reason)


def _require_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _reject(field, "must be an object")
    return value


def _require_fields(value: object, field: str, allowed: set[str]) -> dict[str, Any]:
    obj = _require_object(value, field)
    missing = allowed - obj.keys()
    if missing:
        _reject(f"{field}.{sorted(missing)[0]}" if field else sorted(missing)[0], "is required")
    unknown = obj.keys() - allowed
    if unknown:
        _reject(f"{field}.{sorted(unknown)[0]}" if field else sorted(unknown)[0], "is not allowed")
    return obj


def _require_number(value: object, field: str, *, positive: bool = False,
                    unit_interval: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        _reject(field, "must be a finite number")
    try:
        number = float(value)
    except OverflowError:
        _reject(field, "must be a finite number")
    if not math.isfinite(number):
        _reject(field, "must be a finite number")
    if positive and number <= 0:
        _reject(field, "must be greater than zero")
    if nonnegative and number < 0:
        _reject(field, "must not be negative")
    if unit_interval and not 0 < number < 1:
        _reject(field, "must be between zero and one")
    return number


def _require_scenario_rate(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        _reject(field, "must be a finite number")
    if isinstance(value, Decimal):
        rate = value
    elif isinstance(value, int):
        rate = Decimal(value)
    else:
        if not math.isfinite(value):
            _reject(field, "must be a finite number")
        rate = Decimal(str(value))
    if not rate.is_finite():
        _reject(field, "must be a finite number")
    if rate < 0:
        _reject(field, "must not be negative")
    if rate > _MAX_SCENARIO_RATE:
        _reject(field, "must be a finite number")
    return rate


def _require_nonnegative_int(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(field, "must be an integer")
    if positive and value <= 0:
        _reject(field, "must be greater than zero")
    if not positive and value < 0:
        _reject(field, "must not be negative")
    return value


def _require_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        _reject(field, "must be an ISO calendar date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _reject(field, "must be an ISO calendar date")
    if parsed.isoformat() != value:
        _reject(field, "must be an ISO calendar date")
    return parsed


def _require_representable_date_addition(base: date, days: int, field: str) -> None:
    try:
        base + timedelta(days=days)
    except OverflowError:
        _reject(field, "must produce an ISO calendar date")


def _require_finite_current_power_n(current_matured_n: int) -> None:
    if current_matured_n < 2:
        return
    if current_matured_n > sys.maxsize:
        _reject("sampling.current_matured_n", "must support finite power calculation")
    try:
        root_n = math.sqrt(current_matured_n)
    except OverflowError:
        _reject("sampling.current_matured_n", "must support finite power calculation")
    if not math.isfinite(root_n):
        _reject("sampling.current_matured_n", "must support finite power calculation")


def _require_finite_standardized_effect(effect: float, difference_sd: float) -> None:
    standardized_effect = effect / difference_sd
    if not math.isfinite(standardized_effect) or standardized_effect <= 0:
        _reject("analysis", "must support finite statistical calculation")


def _decode_plan(plan_bytes: bytes) -> dict[str, Any]:
    if not isinstance(plan_bytes, bytes):
        _reject("plan", "must be bytes")
    try:
        decoded = plan_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _reject("plan", "must be valid UTF-8 JSON")

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                _reject("plan", "must not contain duplicate object fields")
            obj[key] = value
        return obj

    try:
        decoded_plan = json.loads(
            decoded,
            object_pairs_hook=reject_duplicate,
            parse_float=Decimal,
        )
    except PlanValidationError:
        raise
    except (ValueError, RecursionError, DecimalException):
        _reject("plan", "must be valid JSON")
    return _require_object(decoded_plan, "plan")


def _validate_plan(plan: dict[str, Any]) -> dict[str, object]:
    root = _require_fields(plan, "", _ROOT_FIELDS)
    if root["schema_version"] != "1":
        _reject("schema_version", "must equal 1")
    as_of_date = _require_date(root["as_of_date"], "as_of_date")

    analysis = _require_fields(root["analysis"], "analysis", _ANALYSIS_FIELDS)
    effect = _require_number(analysis["effect"], "analysis.effect", positive=True)
    difference_sd = _require_number(
        analysis["difference_sd"], "analysis.difference_sd", positive=True
    )
    _require_finite_standardized_effect(effect, difference_sd)
    alpha = _require_number(analysis["alpha"], "analysis.alpha", unit_interval=True)
    target_power = _require_number(
        analysis["target_power"], "analysis.target_power", unit_interval=True
    )
    comparison_count = _require_nonnegative_int(
        analysis["comparison_count"], "analysis.comparison_count", positive=True
    )

    sampling = _require_fields(root["sampling"], "sampling", _SAMPLING_FIELDS)
    current_matured_n = _require_nonnegative_int(
        sampling["current_matured_n"], "sampling.current_matured_n"
    )
    _require_finite_current_power_n(current_matured_n)
    maturity_lag_days = _require_nonnegative_int(
        sampling["maturity_lag_days"], "sampling.maturity_lag_days"
    )
    collection_end_date = _require_date(
        sampling["collection_end_date"], "sampling.collection_end_date"
    )
    if collection_end_date < as_of_date:
        _reject("sampling.collection_end_date", "must not be before as_of_date")
    _require_representable_date_addition(
        collection_end_date, maturity_lag_days, "sampling.maturity_lag_days"
    )
    pending_value = sampling["pending_batches"]
    if not isinstance(pending_value, list):
        _reject("sampling.pending_batches", "must be an array")
    pending_batches: list[PendingBatch] = []
    cumulative_matured_n = current_matured_n
    for index, batch_value in enumerate(pending_value):
        location = f"sampling.pending_batches[{index}]"
        batch = _require_fields(batch_value, location, _PENDING_BATCH_FIELDS)
        count = _require_nonnegative_int(batch["count"], f"{location}.count", positive=True)
        if count > sys.maxsize - cumulative_matured_n:
            _reject(f"{location}.count", "must support finite count calculation")
        cumulative_matured_n += count
        maturity_date = _require_date(batch["maturity_date"], f"{location}.maturity_date")
        if maturity_date <= as_of_date:
            _reject(f"{location}.maturity_date", "must be later than as_of_date")
        pending_batches.append(PendingBatch(count=count, maturity_date=maturity_date))

    horizons_value = root["horizons_days"]
    if not isinstance(horizons_value, list) or not horizons_value:
        _reject("horizons_days", "must be a non-empty array")
    horizons: list[int] = []
    for index, value in enumerate(horizons_value):
        location = f"horizons_days[{index}]"
        horizon = _require_nonnegative_int(value, location, positive=True)
        _require_representable_date_addition(as_of_date, horizon, location)
        horizons.append(horizon)
    if len(set(horizons)) != len(horizons):
        _reject("horizons_days", "must not contain duplicates")
    if horizons != sorted(horizons):
        _reject("horizons_days", "must be strictly increasing")

    scenarios_value = root["scenarios"]
    if not isinstance(scenarios_value, list) or not scenarios_value:
        _reject("scenarios", "must be a non-empty array")
    scenarios: list[Scenario] = []
    scenario_ids: set[str] = set()
    for index, scenario_value in enumerate(scenarios_value):
        location = f"scenarios[{index}]"
        scenario = _require_fields(scenario_value, location, _SCENARIO_FIELDS)
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id:
            _reject(f"{location}.id", "must be a non-empty string")
        if scenario_id in scenario_ids:
            _reject(f"{location}.id", "must be unique")
        scenario_ids.add(scenario_id)
        rate = _require_scenario_rate(
            scenario["eligible_units_per_30_days"],
            f"{location}.eligible_units_per_30_days",
        )
        scenarios.append(Scenario(id=scenario_id, eligible_units_per_30_days=rate))

    return {
        "as_of_date": as_of_date,
        "effect": effect,
        "difference_sd": difference_sd,
        "alpha": alpha,
        "target_power": target_power,
        "comparison_count": comparison_count,
        "current_matured_n": current_matured_n,
        "pending_batches": tuple(pending_batches),
        "maturity_lag_days": maturity_lag_days,
        "collection_end_date": collection_end_date,
        "horizons_days": tuple(horizons),
        "scenarios": tuple(scenarios),
    }


def _round_floats(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        if math.isfinite(value) and value != 0.0 and rounded == 0.0:
            return value
        return rounded
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def assess(plan_bytes: bytes) -> dict[str, object]:
    """Validate exact UTF-8 JSON bytes and return a deterministic assessment."""
    if not isinstance(plan_bytes, bytes):
        _reject("plan", "must be bytes")
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    plan = _validate_plan(_decode_plan(plan_bytes))

    effect = plan["effect"]
    difference_sd = plan["difference_sd"]
    alpha = plan["alpha"]
    target_power = plan["target_power"]
    comparison_count = plan["comparison_count"]
    current_matured_n = plan["current_matured_n"]
    try:
        adjusted_alpha = alpha / comparison_count
    except OverflowError:
        _reject("analysis.comparison_count", "must produce a positive adjusted alpha")
    if not math.isfinite(adjusted_alpha) or adjusted_alpha <= 0:
        _reject("analysis.comparison_count", "must produce a positive adjusted alpha")
    try:
        required_n = required_sample_size(
            effect=effect,
            difference_sd=difference_sd,
            alpha=adjusted_alpha,
            target_power=target_power,
        )
        power_at_required_n = one_sample_t_power(
            effect=effect,
            difference_sd=difference_sd,
            n=required_n,
            alpha=adjusted_alpha,
        )
        if current_matured_n < 2:
            current_power: float | None = None
            current_mde: float | None = None
        else:
            current_power = one_sample_t_power(
                effect=effect,
                difference_sd=difference_sd,
                n=current_matured_n,
                alpha=adjusted_alpha,
            )
            current_mde = minimum_detectable_effect(
                difference_sd=difference_sd,
                n=current_matured_n,
                alpha=adjusted_alpha,
                target_power=target_power,
            )
    except (ArithmeticError, ValueError):
        _reject("analysis", "must support finite statistical calculation")
    except TypeError as error:
        if "ufunc" not in str(error):
            raise
        _reject("analysis", "must support finite statistical calculation")

    as_of_date = plan["as_of_date"]
    collection_end_date = plan["collection_end_date"]
    reachability = build_reachability_rows(
        as_of_date=as_of_date,
        collection_end_date=collection_end_date,
        maturity_lag_days=plan["maturity_lag_days"],
        current_matured_n=current_matured_n,
        pending_batches=plan["pending_batches"],
        horizons_days=plan["horizons_days"],
        scenarios=plan["scenarios"],
        required_n=required_n,
    )
    result: dict[str, object] = {
        "schema_version": "1",
        "plan_sha256": plan_sha256,
        "method": {
            "test": "two-sided one-sample t on observations or precomputed paired differences",
            "power_distribution": "noncentral t",
            "multiple_comparisons": "Bonferroni adjustment for a user-declared fixed family",
            "reachability": "deterministic scenario arithmetic",
        },
        "assumptions": {
            "as_of_date": as_of_date.isoformat(),
            "effect": effect,
            "difference_sd": difference_sd,
            "alpha": alpha,
            "target_power": target_power,
            "comparison_count": comparison_count,
            "maturity_lag_days": plan["maturity_lag_days"],
            "collection_end_date": collection_end_date.isoformat(),
        },
        "statistics": {
            "adjusted_alpha": adjusted_alpha,
            "current_matured_n": current_matured_n,
            "current_power": current_power,
            "current_mde": current_mde,
            "required_n": required_n,
            "power_at_required_n": power_at_required_n,
        },
        "reachability": reachability,
        "limitations": [
            "Scenario-implied reachability is not a probability forecast or promise.",
            "EvidenceReach does not validate evidence quality, eligibility, independence, or truth.",
            "Bonferroni applies only to the fixed comparison family declared by the caller.",
            "This assessment is a planning aid, not statistical, financial, or investment advice.",
        ],
    }
    return _round_floats(result)
