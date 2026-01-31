"""Recommendation engine for content strategy."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.models.taxonomy import ContentType


class RecommendationTier(str, Enum):
    """Recommendation confidence tiers."""

    CONFIDENT = "confident"  # High confidence, act on it
    HYPOTHESIS = "hypothesis"  # Worth testing, don't bet on it
    INSUFFICIENT_DATA = "insufficient_data"  # Not enough data to recommend


class RecommendationAction(str, Enum):
    """Types of recommended actions."""

    INCREASE = "increase"  # Post more of this content type
    MAINTAIN = "maintain"  # Keep current posting frequency
    DECREASE = "decrease"  # Consider reducing this content type
    TEST = "test"  # Run a test to gather more data


@dataclass
class ContentRecommendation:
    """A single content type recommendation."""

    content_type: str
    action: RecommendationAction
    tier: RecommendationTier
    lift_pct: float | None
    confidence_score: float
    current_posts_per_week: float
    suggested_posts_per_week: float | None
    reasoning: str
    caveats: list[str]


@dataclass
class WeeklyPlan:
    """Suggested weekly posting plan."""

    total_posts: int
    breakdown: dict[str, int]  # content_type -> suggested count
    rationale: str


@dataclass
class RecommendationReport:
    """Complete recommendation report for a creator."""

    creator_id: str
    period_days: int
    total_subs: int
    total_revenue: float
    has_confounders: bool
    confounder_warning: str | None
    recommendations: list[ContentRecommendation]
    weekly_plan: WeeklyPlan | None
    top_performer: str | None
    underperformer: str | None
    data_quality_notes: list[str]


class RecommendationEngine:
    """
    Generates actionable recommendations from attribution data.

    Key principles:
    1. Never recommend with false confidence
    2. Clearly separate "confident" from "hypothesis"
    3. Account for confounders in recommendations
    4. Provide specific, actionable suggestions
    """

    # Thresholds for recommendations
    MIN_LIFT_FOR_INCREASE = 20.0  # 20% lift minimum to suggest increase
    MIN_LIFT_FOR_CONFIDENT_INCREASE = 50.0  # 50% lift for confident increase
    DECREASE_THRESHOLD = -10.0  # Negative lift threshold for decrease suggestion
    MIN_POSTS_FOR_ANALYSIS = 3  # Need at least 3 posts to analyze a content type

    # Weekly posting targets
    DEFAULT_POSTS_PER_WEEK = 7  # Baseline assumption
    MAX_POSTS_PER_WEEK = 21  # 3 per day max
    MIN_POSTS_PER_WEEK = 3  # Minimum to maintain presence

    def generate_report(
        self,
        creator_id: str,
        performance_data: dict[str, Any],
        attribution_data: dict[str, Any] | None = None,
    ) -> RecommendationReport:
        """
        Generate a complete recommendation report.

        Args:
            creator_id: Creator UUID as string
            performance_data: Output from AttributionService.get_content_type_performance()
            attribution_data: Optional output from AttributionService.attribute_window()

        Returns:
            RecommendationReport with actionable recommendations
        """
        content_types = performance_data.get("content_types", {})
        confounders = performance_data.get("confounders", [])
        has_confounders = performance_data.get("has_confounders", False)

        # Build confounder warning
        confounder_warning = None
        if has_confounders:
            confounder_warning = self._build_confounder_warning(confounders)

        # Generate recommendations for each content type
        recommendations = []
        for ct_name, ct_data in content_types.items():
            rec = self._analyze_content_type(ct_name, ct_data, has_confounders)
            recommendations.append(rec)

        # Sort by lift (highest first), with confident tier prioritized
        recommendations.sort(
            key=lambda r: (
                r.tier == RecommendationTier.CONFIDENT,
                r.lift_pct or 0,
            ),
            reverse=True,
        )

        # Identify top performer and underperformer
        top_performer = None
        underperformer = None

        confident_recs = [r for r in recommendations if r.tier == RecommendationTier.CONFIDENT]
        if confident_recs:
            top_performer = confident_recs[0].content_type
            # Find underperformer among confident recommendations
            decrease_recs = [r for r in confident_recs if r.action == RecommendationAction.DECREASE]
            if decrease_recs:
                underperformer = decrease_recs[0].content_type

        # Generate weekly plan
        weekly_plan = self._generate_weekly_plan(recommendations, has_confounders)

        # Data quality notes
        data_quality_notes = self._assess_data_quality(
            performance_data, recommendations
        )

        return RecommendationReport(
            creator_id=creator_id,
            period_days=performance_data.get("period_days", 0),
            total_subs=performance_data.get("total_subs", 0),
            total_revenue=attribution_data.get("actual_revenue", 0) if attribution_data else 0,
            has_confounders=has_confounders,
            confounder_warning=confounder_warning,
            recommendations=recommendations,
            weekly_plan=weekly_plan,
            top_performer=top_performer,
            underperformer=underperformer,
            data_quality_notes=data_quality_notes,
        )

    def _analyze_content_type(
        self,
        content_type: str,
        data: dict[str, Any],
        has_confounders: bool,
    ) -> ContentRecommendation:
        """Analyze a single content type and generate recommendation."""
        lift_pct = data.get("lift_pct")
        confidence = data.get("confidence", {})
        confidence_score = confidence.get("score", 0) if confidence else 0
        tier_str = data.get("tier", "hypothesis")
        posts_count = data.get("posts_with_views", 0)

        # Determine tier
        if confidence_score >= 0.7 and not has_confounders:
            tier = RecommendationTier.CONFIDENT
        elif posts_count < self.MIN_POSTS_FOR_ANALYSIS:
            tier = RecommendationTier.INSUFFICIENT_DATA
        else:
            tier = RecommendationTier.HYPOTHESIS

        # Determine action
        action, reasoning = self._determine_action(
            lift_pct, confidence_score, tier, has_confounders
        )

        # Calculate suggested posts per week
        current_posts_per_week = posts_count / 4  # Rough estimate from 30-day data
        suggested_posts_per_week = self._calculate_suggested_posts(
            action, current_posts_per_week, lift_pct
        )

        # Build caveats
        caveats = self._build_caveats(data, has_confounders, tier)

        return ContentRecommendation(
            content_type=content_type,
            action=action,
            tier=tier,
            lift_pct=lift_pct,
            confidence_score=confidence_score,
            current_posts_per_week=round(current_posts_per_week, 1),
            suggested_posts_per_week=suggested_posts_per_week,
            reasoning=reasoning,
            caveats=caveats,
        )

    def _determine_action(
        self,
        lift_pct: float | None,
        confidence_score: float,
        tier: RecommendationTier,
        has_confounders: bool,
    ) -> tuple[RecommendationAction, str]:
        """Determine the recommended action and reasoning."""
        if tier == RecommendationTier.INSUFFICIENT_DATA:
            return (
                RecommendationAction.TEST,
                "Not enough posts to analyze. Run a test by posting more of this content type.",
            )

        if lift_pct is None:
            return (
                RecommendationAction.TEST,
                "Unable to calculate lift. Need more data.",
            )

        # Confident recommendations
        if tier == RecommendationTier.CONFIDENT:
            if lift_pct >= self.MIN_LIFT_FOR_CONFIDENT_INCREASE:
                return (
                    RecommendationAction.INCREASE,
                    f"Strong performer with {lift_pct:.0f}% lift. Confidently recommend increasing.",
                )
            elif lift_pct >= self.MIN_LIFT_FOR_INCREASE:
                return (
                    RecommendationAction.INCREASE,
                    f"Positive lift of {lift_pct:.0f}%. Recommend modest increase.",
                )
            elif lift_pct <= self.DECREASE_THRESHOLD:
                return (
                    RecommendationAction.DECREASE,
                    f"Negative lift of {lift_pct:.0f}%. Consider reallocating effort to better performers.",
                )
            else:
                return (
                    RecommendationAction.MAINTAIN,
                    f"Neutral performance ({lift_pct:.0f}% lift). Maintain current frequency.",
                )

        # Hypothesis recommendations (lower confidence)
        if has_confounders:
            return (
                RecommendationAction.TEST,
                f"Shows {lift_pct:.0f}% lift but confounders detected. Retest in a clean window.",
            )

        if lift_pct >= self.MIN_LIFT_FOR_INCREASE:
            return (
                RecommendationAction.TEST,
                f"Promising {lift_pct:.0f}% lift but needs more data. Worth testing further.",
            )
        elif lift_pct <= self.DECREASE_THRESHOLD:
            return (
                RecommendationAction.TEST,
                f"Showing {lift_pct:.0f}% lift. May underperform but needs more data to confirm.",
            )
        else:
            return (
                RecommendationAction.MAINTAIN,
                f"Inconclusive results ({lift_pct:.0f}% lift). Maintain while gathering more data.",
            )

    def _calculate_suggested_posts(
        self,
        action: RecommendationAction,
        current_posts_per_week: float,
        lift_pct: float | None,
    ) -> float | None:
        """Calculate suggested posts per week based on action."""
        if action == RecommendationAction.TEST:
            # Suggest minimum viable test
            return max(self.MIN_POSTS_FOR_ANALYSIS, current_posts_per_week)

        if action == RecommendationAction.INCREASE:
            # Increase proportional to lift, capped at max
            if lift_pct and lift_pct >= self.MIN_LIFT_FOR_CONFIDENT_INCREASE:
                multiplier = 1.5
            else:
                multiplier = 1.25
            suggested = current_posts_per_week * multiplier
            return min(round(suggested, 0), self.MAX_POSTS_PER_WEEK)

        if action == RecommendationAction.DECREASE:
            # Decrease by 25-50% depending on severity
            if lift_pct and lift_pct < -30:
                multiplier = 0.5
            else:
                multiplier = 0.75
            suggested = current_posts_per_week * multiplier
            return max(round(suggested, 0), 1)  # At least 1 to keep testing

        if action == RecommendationAction.MAINTAIN:
            return round(current_posts_per_week, 0) or 2

        return None

    def _build_caveats(
        self,
        data: dict[str, Any],
        has_confounders: bool,
        tier: RecommendationTier,
    ) -> list[str]:
        """Build list of caveats for this recommendation."""
        caveats = []

        confidence = data.get("confidence", {})
        reasons = confidence.get("reasons", []) if confidence else []

        if has_confounders:
            caveats.append("⚠️ Confounders detected - results may be skewed")

        if tier == RecommendationTier.HYPOTHESIS:
            caveats.append("📊 Hypothesis only - needs more data to confirm")

        if "Small sample size" in str(reasons):
            caveats.append("📉 Small sample size - confidence is limited")

        posts_count = data.get("posts_with_views", 0)
        if posts_count < 5:
            caveats.append(f"Only {posts_count} posts analyzed")

        return caveats

    def _build_confounder_warning(self, confounders: list[dict]) -> str:
        """Build a human-readable confounder warning."""
        if not confounders:
            return ""

        confounder_types = set()
        descriptions = []

        for c in confounders:
            event_type = c.get("event_type", "unknown")
            description = c.get("description", "")
            confounder_types.add(event_type)
            if description:
                descriptions.append(description)

        type_str = ", ".join(sorted(confounder_types))

        warning = f"⚠️ CONFOUNDER ALERT: {type_str} detected during this period"
        if descriptions:
            warning += f" ({'; '.join(descriptions[:3])})"
        warning += ". Recommendations are marked as hypotheses until a clean measurement window is available."

        return warning

    def _generate_weekly_plan(
        self,
        recommendations: list[ContentRecommendation],
        has_confounders: bool,
    ) -> WeeklyPlan | None:
        """Generate a suggested weekly posting plan."""
        if has_confounders:
            # Don't generate confident plan when confounders present
            return WeeklyPlan(
                total_posts=self.DEFAULT_POSTS_PER_WEEK,
                breakdown={},
                rationale="Weekly plan unavailable due to confounders. Maintain current mix while gathering clean data.",
            )

        # Check if we have any confident recommendations
        confident_recs = [
            r for r in recommendations
            if r.tier == RecommendationTier.CONFIDENT
        ]

        if not confident_recs:
            return WeeklyPlan(
                total_posts=self.DEFAULT_POSTS_PER_WEEK,
                breakdown={},
                rationale="Insufficient confident data for weekly plan. Continue testing all content types.",
            )

        # Build breakdown based on recommendations
        breakdown = {}
        total_suggested = 0

        for rec in recommendations:
            if rec.suggested_posts_per_week:
                posts = int(rec.suggested_posts_per_week)
                breakdown[rec.content_type] = posts
                total_suggested += posts

        # Normalize to reasonable total if needed
        if total_suggested > self.MAX_POSTS_PER_WEEK:
            scale = self.MAX_POSTS_PER_WEEK / total_suggested
            for ct in breakdown:
                breakdown[ct] = max(1, int(breakdown[ct] * scale))
            total_suggested = sum(breakdown.values())

        # Build rationale
        top_performers = [
            r.content_type for r in recommendations
            if r.action == RecommendationAction.INCREASE
        ][:2]

        if top_performers:
            rationale = f"Focus on {', '.join(top_performers)} based on lift data."
        else:
            rationale = "Balanced approach recommended based on current data."

        return WeeklyPlan(
            total_posts=total_suggested or self.DEFAULT_POSTS_PER_WEEK,
            breakdown=breakdown,
            rationale=rationale,
        )

    def _assess_data_quality(
        self,
        performance_data: dict[str, Any],
        recommendations: list[ContentRecommendation],
    ) -> list[str]:
        """Assess overall data quality and return notes."""
        notes = []

        total_subs = performance_data.get("total_subs", 0)
        period_days = performance_data.get("period_days", 0)

        if total_subs < 10:
            notes.append(f"⚠️ Only {total_subs} subscribers in period - minimum 10 recommended for attribution")

        if total_subs < 25:
            notes.append("📊 Sample size below 25 - all recommendations are hypotheses")

        if period_days < 14:
            notes.append(f"📅 Short analysis period ({period_days} days) - consider 30+ days for stability")

        insufficient_count = sum(
            1 for r in recommendations
            if r.tier == RecommendationTier.INSUFFICIENT_DATA
        )
        if insufficient_count > 0:
            notes.append(f"📉 {insufficient_count} content type(s) have insufficient data")

        # Check for content type coverage
        content_types = performance_data.get("content_types", {})
        if len(content_types) < 3:
            notes.append("💡 Consider testing more content types for comparison")

        return notes

    def format_report_text(self, report: RecommendationReport) -> str:
        """Format report as human-readable text for email/display."""
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("FUNNELLENS CONTENT STRATEGY REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        lines.append(f"Period: {report.period_days} days")
        lines.append(f"Total Subscribers: {report.total_subs}")
        if report.total_revenue:
            lines.append(f"Total Revenue: ${report.total_revenue:,.2f}")
        lines.append("")

        # Confounder warning
        if report.confounder_warning:
            lines.append(report.confounder_warning)
            lines.append("")

        # Top performer highlight
        if report.top_performer:
            lines.append(f"🏆 TOP PERFORMER: {report.top_performer}")
            lines.append("")

        # Recommendations by tier
        confident_recs = [r for r in report.recommendations if r.tier == RecommendationTier.CONFIDENT]
        hypothesis_recs = [r for r in report.recommendations if r.tier == RecommendationTier.HYPOTHESIS]
        insufficient_recs = [r for r in report.recommendations if r.tier == RecommendationTier.INSUFFICIENT_DATA]

        if confident_recs:
            lines.append("-" * 40)
            lines.append("CONFIDENT RECOMMENDATIONS")
            lines.append("-" * 40)
            for rec in confident_recs:
                lines.append(self._format_recommendation(rec))
            lines.append("")

        if hypothesis_recs:
            lines.append("-" * 40)
            lines.append("HYPOTHESES (Need More Data)")
            lines.append("-" * 40)
            for rec in hypothesis_recs:
                lines.append(self._format_recommendation(rec))
            lines.append("")

        if insufficient_recs:
            lines.append("-" * 40)
            lines.append("INSUFFICIENT DATA")
            lines.append("-" * 40)
            for rec in insufficient_recs:
                lines.append(f"  • {rec.content_type}: {rec.reasoning}")
            lines.append("")

        # Weekly plan
        if report.weekly_plan and report.weekly_plan.breakdown:
            lines.append("-" * 40)
            lines.append("SUGGESTED WEEKLY PLAN")
            lines.append("-" * 40)
            lines.append(f"Total posts: {report.weekly_plan.total_posts}")
            for ct, count in sorted(report.weekly_plan.breakdown.items(), key=lambda x: -x[1]):
                lines.append(f"  • {ct}: {count} posts")
            lines.append(f"\n{report.weekly_plan.rationale}")
            lines.append("")

        # Data quality notes
        if report.data_quality_notes:
            lines.append("-" * 40)
            lines.append("DATA QUALITY NOTES")
            lines.append("-" * 40)
            for note in report.data_quality_notes:
                lines.append(f"  {note}")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def _format_recommendation(self, rec: ContentRecommendation) -> str:
        """Format a single recommendation for text display."""
        lines = []

        # Content type and action
        action_emoji = {
            RecommendationAction.INCREASE: "⬆️",
            RecommendationAction.DECREASE: "⬇️",
            RecommendationAction.MAINTAIN: "➡️",
            RecommendationAction.TEST: "🧪",
        }
        emoji = action_emoji.get(rec.action, "•")

        lift_str = f"{rec.lift_pct:+.0f}% lift" if rec.lift_pct else "lift unknown"
        lines.append(f"\n{emoji} {rec.content_type.upper()} ({lift_str})")
        lines.append(f"   {rec.reasoning}")

        if rec.suggested_posts_per_week:
            current = rec.current_posts_per_week
            suggested = rec.suggested_posts_per_week
            if current != suggested:
                lines.append(f"   → Change from {current:.0f} to {suggested:.0f} posts/week")
            else:
                lines.append(f"   → Maintain {suggested:.0f} posts/week")

        for caveat in rec.caveats:
            lines.append(f"   {caveat}")

        return "\n".join(lines)
