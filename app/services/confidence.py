"""Confidence scoring for attribution claims.

CRITICAL: Confidence is based on:
- Number of EVENTS (subs, revenue), NOT number of posts
- Statistical significance of lift vs baseline
- Data quality (baseline coverage, confounder presence)
"""

from dataclasses import dataclass
from math import factorial, exp


@dataclass
class ConfidenceResult:
    """Result of confidence scoring."""

    score: float  # 0.0 - 1.0
    level: str  # "low", "medium", "high"
    reasons: list[str]
    min_events_met: bool

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "level": self.level,
            "reasons": self.reasons,
            "min_events_met": self.min_events_met,
        }


class ConfidenceScorer:
    """
    Compute confidence scores for attribution claims.

    Thresholds from v1.1 spec:
    - MIN_SUBS_FOR_RECOMMENDATION = 10 (minimum to show any recommendation)
    - MIN_SUBS_FOR_CONFIDENT = 25 (minimum for "confident" tier)
    - MIN_BASELINE_DAYS = 7 (minimum baseline data)
    """

    MIN_SUBS_FOR_RECOMMENDATION = 10
    MIN_SUBS_FOR_CONFIDENT = 25
    MIN_BASELINE_DAYS = 7

    def score(
        self,
        actual_events: int,
        expected_events: float,
        window_hours: float,
        has_confounders: bool = False,
        baseline_data_days: int = 14,
    ) -> ConfidenceResult:
        """
        Score confidence in an attribution claim.

        Args:
            actual_events: Actual subscriber count in window
            expected_events: Expected subs based on baseline
            window_hours: Length of attribution window in hours
            has_confounders: Whether confounder events overlap
            baseline_data_days: Days of baseline data available

        Returns:
            ConfidenceResult with score, level, and reasoning
        """
        reasons = []
        score = 0.5  # Start at medium

        # 1. Event count thresholds (most important)
        if actual_events < self.MIN_SUBS_FOR_RECOMMENDATION:
            reasons.append(
                f"Low sample: only {actual_events} subs (need {self.MIN_SUBS_FOR_RECOMMENDATION}+)"
            )
            score -= 0.3
            min_events_met = False
        elif actual_events < self.MIN_SUBS_FOR_CONFIDENT:
            reasons.append(f"Moderate sample: {actual_events} subs")
            min_events_met = True
        else:
            reasons.append(f"Good sample: {actual_events} subs")
            score += 0.15
            min_events_met = True

        # 2. Statistical significance
        if expected_events > 0 and actual_events >= 5:
            p_value = self._poisson_test(actual_events, expected_events)

            if p_value < 0.05:
                reasons.append("Lift is statistically significant (p < 0.05)")
                score += 0.2
            elif p_value < 0.10:
                reasons.append("Lift is marginally significant (p < 0.10)")
                score += 0.1
            else:
                reasons.append(f"Lift not significant (p = {p_value:.2f})")
                score -= 0.1

        # 3. Baseline data quality
        if baseline_data_days < self.MIN_BASELINE_DAYS:
            reasons.append(
                f"Limited baseline: {baseline_data_days} days (prefer {self.MIN_BASELINE_DAYS}+)"
            )
            score -= 0.15
        elif baseline_data_days >= 14:
            score += 0.05

        # 4. Confounder penalty
        if has_confounders:
            reasons.append("Confounder event(s) overlap with window")
            score -= 0.2

        # 5. Window length sanity
        if window_hours < 24:
            reasons.append("Short window (<24h) increases noise")
            score -= 0.1

        # Clamp score
        score = max(0.1, min(0.95, score))

        # Determine level
        if score >= 0.7:
            level = "high"
        elif score >= 0.4:
            level = "medium"
        else:
            level = "low"

        return ConfidenceResult(
            score=score,
            level=level,
            reasons=reasons,
            min_events_met=min_events_met,
        )

    def _poisson_test(self, observed: int, expected: float) -> float:
        """
        Two-sided Poisson test.

        Returns p-value for H0: observed comes from Poisson(expected).
        Uses pure Python implementation to avoid scipy dependency.
        """
        if expected <= 0:
            return 1.0

        # Poisson PMF: P(X=k) = (lambda^k * e^-lambda) / k!
        def poisson_pmf(k: int, lam: float) -> float:
            if k < 0:
                return 0.0
            try:
                return (lam**k * exp(-lam)) / factorial(k)
            except (OverflowError, ValueError):
                # For large k, use Stirling's approximation or return small value
                return 1e-10

        # Poisson CDF: P(X <= k)
        def poisson_cdf(k: int, lam: float) -> float:
            total = 0.0
            for i in range(k + 1):
                total += poisson_pmf(i, lam)
            return min(total, 1.0)

        # Two-sided test
        if observed >= expected:
            # P(X >= observed)
            p_upper = 1 - poisson_cdf(observed - 1, expected)
            return 2 * min(p_upper, 0.5)
        else:
            # P(X <= observed)
            p_lower = poisson_cdf(observed, expected)
            return 2 * min(p_lower, 0.5)
