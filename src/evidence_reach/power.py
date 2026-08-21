"""Exact one-sample t-test power calculations."""

import math

from scipy import stats


def _require_finite(value: float, name: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not finite:
        raise ValueError(f"{name} must be finite")


def _validate_common(*, difference_sd: float, n: int, alpha: float) -> None:
    _require_finite(difference_sd, "difference_sd")
    _require_finite(alpha, "alpha")
    if difference_sd <= 0:
        raise ValueError("difference_sd must be greater than zero")
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError("n must be an integer of at least two")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")


def one_sample_t_power(
    *, effect: float, difference_sd: float, n: int, alpha: float
) -> float:
    """Return strict two-sided one-sample t power using a noncentral t."""
    _validate_common(difference_sd=difference_sd, n=n, alpha=alpha)
    _require_finite(effect, "effect")

    df = n - 1
    half_alpha = alpha / 2.0
    if not math.isfinite(half_alpha) or half_alpha <= 0.0:
        raise ArithmeticError("alpha/2 must produce a finite critical value")
    standardized_effect = abs(effect / difference_sd)
    try:
        critical_t = stats.t.isf(half_alpha, df)
        noncentrality = standardized_effect * math.sqrt(n)
        if not math.isfinite(critical_t) or not math.isfinite(noncentrality):
            raise ArithmeticError("unable to produce a finite critical value or effect")
        upper_tail = stats.nct.sf(critical_t, df, noncentrality)
        if not math.isfinite(upper_tail):
            upper_tail = stats.nct.cdf(-critical_t, df, -noncentrality)
        lower_tail = stats.nct.cdf(-critical_t, df, noncentrality)
        if not math.isfinite(lower_tail):
            lower_tail = stats.nct.sf(critical_t, df, -noncentrality)
    except (OverflowError, TypeError, ValueError) as error:
        raise ArithmeticError("SciPy could not evaluate power in its numeric domain") from error
    power = upper_tail + lower_tail
    if not math.isfinite(power) or not 0.0 <= power <= 1.0:
        raise ArithmeticError("SciPy returned a non-finite power")
    return float(power)


def minimum_detectable_effect(
    *, difference_sd: float, n: int, alpha: float, target_power: float
) -> float:
    """Return the non-negative raw-unit MDE boundary for target power."""
    _validate_common(difference_sd=difference_sd, n=n, alpha=alpha)
    _require_finite(target_power, "target_power")
    if not 0 < target_power < 1:
        raise ValueError("target_power must be between zero and one")
    if target_power <= alpha:
        return 0.0

    low = 0.0
    high = difference_sd
    for _ in range(100):
        if one_sample_t_power(
            effect=high, difference_sd=difference_sd, n=n, alpha=alpha
        ) >= target_power:
            break
        high *= 2.0
        if not math.isfinite(high):
            raise ArithmeticError("unable to establish an MDE bracket")
    else:
        raise ArithmeticError("unable to establish an MDE bracket")

    for _ in range(100):
        midpoint = (low + high) / 2.0
        power = one_sample_t_power(
            effect=midpoint, difference_sd=difference_sd, n=n, alpha=alpha
        )
        if abs(power - target_power) <= 1e-10:
            return midpoint
        if power < target_power:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def required_sample_size(
    *, effect: float, difference_sd: float, alpha: float, target_power: float
) -> int:
    """Return the smallest integer n of at least two reaching target power."""
    _require_finite(effect, "effect")
    _require_finite(difference_sd, "difference_sd")
    _require_finite(alpha, "alpha")
    _require_finite(target_power, "target_power")
    if difference_sd <= 0:
        raise ValueError("difference_sd must be greater than zero")
    if effect <= 0:
        raise ValueError("effect must be greater than zero")
    if not 0 < alpha < 1 or not 0 < target_power < 1:
        raise ValueError("alpha and target_power must be between zero and one")

    lower = 2
    upper = 2
    for _ in range(100):
        if one_sample_t_power(
            effect=effect, difference_sd=difference_sd, n=upper, alpha=alpha
        ) >= target_power:
            break
        lower = upper + 1
        upper *= 2
    else:
        raise ArithmeticError("unable to establish a sample-size bracket")

    while lower < upper:
        midpoint = (lower + upper) // 2
        if one_sample_t_power(
            effect=effect, difference_sd=difference_sd, n=midpoint, alpha=alpha
        ) >= target_power:
            upper = midpoint
        else:
            lower = midpoint + 1
    return lower
