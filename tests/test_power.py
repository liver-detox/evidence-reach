import math
import unittest
from unittest.mock import patch

from scipy import stats

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

    def test_tiny_alpha_zero_effect_calibrates_without_quantile_cancellation(self) -> None:
        alpha = 1e-16
        result = one_sample_t_power(
            effect=0.0,
            difference_sd=1.0,
            n=20,
            alpha=alpha,
        )
        self.assertTrue(math.isclose(result, alpha, rel_tol=1e-10, abs_tol=0.0))

    def test_unrepresentable_critical_value_raises_arithmetic_error(self) -> None:
        smallest_positive_float = float.fromhex("0x0.0000000000001p-1022")
        with self.assertRaisesRegex(ArithmeticError, "critical"):
            one_sample_t_power(
                effect=0.0,
                difference_sd=1.0,
                n=20,
                alpha=smallest_positive_float,
            )

        with patch.object(stats.t, "isf", return_value=float("inf")):
            with self.assertRaisesRegex(ArithmeticError, "critical"):
                one_sample_t_power(
                    effect=0.0,
                    difference_sd=1.0,
                    n=20,
                    alpha=0.05,
                )

    def test_equal_extreme_scales_do_not_overflow_before_standardization(self) -> None:
        self.assertAlmostEqual(
            one_sample_t_power(
                effect=1e308,
                difference_sd=1e308,
                n=4,
                alpha=0.05,
            ),
            0.2887524164017149,
            delta=2e-14,
        )

    def test_unrepresentable_integer_argument_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            one_sample_t_power(
                effect=10**400,
                difference_sd=1.0,
                n=4,
                alpha=0.05,
            )

    def test_dependency_numeric_domain_errors_are_arithmetic_errors(self) -> None:
        with patch.object(stats.nct, "sf", side_effect=TypeError("domain")):
            with self.assertRaises(ArithmeticError):
                one_sample_t_power(
                    effect=0.5,
                    difference_sd=1.0,
                    n=20,
                    alpha=0.05,
                )

    def test_unrepresentable_required_n_search_raises_arithmetic_error(self) -> None:
        with self.assertRaises(ArithmeticError):
            required_sample_size(
                effect=float.fromhex("0x0.0000000000001p-1022"),
                difference_sd=1.0,
                alpha=0.05,
                target_power=0.8,
            )

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

    def test_large_noncentrality_keeps_power_finite(self) -> None:
        n = 5
        alpha = 0.0125
        difference_sd = 8.0
        effect = 32.0
        critical_t = stats.t.ppf(1.0 - alpha / 2.0, n - 1)
        noncentrality = effect * math.sqrt(n) / difference_sd

        result = one_sample_t_power(
            effect=effect,
            difference_sd=difference_sd,
            n=n,
            alpha=alpha,
        )
        self.assertTrue(math.isfinite(result))
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)
        self.assertAlmostEqual(
            result,
            stats.nct.sf(critical_t, n - 1, noncentrality)
            + stats.nct.sf(critical_t, n - 1, -noncentrality),
            places=12,
        )

    def test_nonfinite_primary_tails_use_symmetric_fallback(self) -> None:
        n = 20
        alpha = 0.05
        difference_sd = 1.0
        effect = 0.5
        critical_t = stats.t.ppf(1.0 - alpha / 2.0, n - 1)
        noncentrality = effect * math.sqrt(n) / difference_sd
        original_sf = stats.nct.sf
        original_cdf = stats.nct.cdf

        def sf_with_nonfinite_positive_tail(
            value: float, degrees_of_freedom: int, noncentrality_value: float
        ) -> float:
            if noncentrality_value > 0:
                return float("nan")
            return original_sf(value, degrees_of_freedom, noncentrality_value)

        with patch.object(stats.nct, "sf", side_effect=sf_with_nonfinite_positive_tail):
            result = one_sample_t_power(
                effect=effect,
                difference_sd=difference_sd,
                n=n,
                alpha=alpha,
            )
        self.assertTrue(math.isfinite(result))
        self.assertAlmostEqual(
            result,
            original_cdf(-critical_t, n - 1, -noncentrality)
            + original_cdf(-critical_t, n - 1, noncentrality),
            places=12,
        )

        def cdf_with_nonfinite_positive_tail(
            value: float, degrees_of_freedom: int, noncentrality_value: float
        ) -> float:
            if noncentrality_value > 0:
                return float("nan")
            return original_cdf(value, degrees_of_freedom, noncentrality_value)

        with patch.object(
            stats.nct, "cdf", side_effect=cdf_with_nonfinite_positive_tail
        ):
            result = one_sample_t_power(
                effect=effect,
                difference_sd=difference_sd,
                n=n,
                alpha=alpha,
            )
        self.assertTrue(math.isfinite(result))
        self.assertAlmostEqual(
            result,
            original_sf(critical_t, n - 1, noncentrality)
            + original_sf(critical_t, n - 1, -noncentrality),
            places=12,
        )

    def test_mde_recovers_target_when_bracket_uses_large_noncentrality(self) -> None:
        mde = minimum_detectable_effect(
            difference_sd=8.0,
            n=5,
            alpha=0.0125,
            target_power=0.8,
        )
        recovered = one_sample_t_power(
            effect=mde,
            difference_sd=8.0,
            n=5,
            alpha=0.0125,
        )
        self.assertAlmostEqual(recovered, 0.8, delta=1e-6)

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

    def test_invalid_non_numeric_and_bool_arguments_raise_value_error(self) -> None:
        calls = (
            lambda: one_sample_t_power(
                effect="bad", difference_sd=1.0, n=20, alpha=0.05
            ),
            lambda: one_sample_t_power(
                effect=True, difference_sd=1.0, n=20, alpha=0.05
            ),
            lambda: one_sample_t_power(
                effect=1.0, difference_sd=True, n=20, alpha=0.05
            ),
            lambda: one_sample_t_power(
                effect=1.0, difference_sd=1.0, n=True, alpha=0.05
            ),
            lambda: one_sample_t_power(
                effect=1.0, difference_sd=1.0, n=20, alpha=False
            ),
            lambda: minimum_detectable_effect(
                difference_sd="bad", n=20, alpha=0.05, target_power=0.8
            ),
            lambda: minimum_detectable_effect(
                difference_sd=True, n=20, alpha=0.05, target_power=0.8
            ),
            lambda: minimum_detectable_effect(
                difference_sd=1.0, n=20, alpha=False, target_power=0.8
            ),
            lambda: minimum_detectable_effect(
                difference_sd=1.0, n=20, alpha=0.05, target_power=True
            ),
            lambda: required_sample_size(
                effect="bad", difference_sd=1.0, alpha=0.05, target_power=0.8
            ),
            lambda: required_sample_size(
                effect=True, difference_sd=1.0, alpha=0.05, target_power=0.8
            ),
            lambda: required_sample_size(
                effect=0.0, difference_sd=1.0, alpha=0.05, target_power=0.8
            ),
            lambda: required_sample_size(
                effect=1.0, difference_sd=True, alpha=0.05, target_power=0.8
            ),
            lambda: required_sample_size(
                effect=1.0, difference_sd=1.0, alpha=False, target_power=0.8
            ),
            lambda: required_sample_size(
                effect=1.0, difference_sd=1.0, alpha=0.05, target_power=True
            ),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()

    def test_frozen_webr_r_strict_power_references(self) -> None:
        # Independently run 2026-08-21 with webR npm 0.6.0 using
        # R 4.6.0 / stats 4.6.0 in local Node R/Wasm (not native Rscript).
        # R: power.t.test(n=12, delta=0.3, sd=1, sig.level=0.10,
        #   type="one.sample", alternative="two.sided", strict=TRUE)$power
        # Observed: 0.256067159085451; frozen expected: 0.256067159085
        # R: power.t.test(n=25, delta=2, sd=5, sig.level=0.05,
        #   type="one.sample", alternative="two.sided", strict=TRUE)$power
        # Observed: 0.484018280695609; frozen expected: 0.484018280696
        # R: power.t.test(n=50, delta=1.5, sd=3, sig.level=0.01,
        #   type="one.sample", alternative="two.sided", strict=TRUE)$power
        # Observed: 0.799336911002067; frozen expected: 0.799336911002
        cases = (
            (0.3, 1.0, 12, 0.10, 0.256067159085),
            (2.0, 5.0, 25, 0.05, 0.484018280696),
            (1.5, 3.0, 50, 0.01, 0.799336911002),
        )
        for effect, difference_sd, n, alpha, expected in cases:
            with self.subTest(n=n, alpha=alpha, effect=effect):
                self.assertAlmostEqual(
                    one_sample_t_power(
                        effect=effect,
                        difference_sd=difference_sd,
                        n=n,
                        alpha=alpha,
                    ),
                    expected,
                    delta=2e-6,
                )


if __name__ == "__main__":
    unittest.main()
