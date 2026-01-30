"""Attribution service - the core analytics engine.

Key fixes from v1.1:
- Baseline ends at window_start (not contaminated)
- Uses hours not days (no truncation)
- Weighted credit split across content types
- Confounder awareness
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConfounderEvent, Creator, Fan, RevenueEvent
from app.services.confidence import ConfidenceResult, ConfidenceScorer
from app.services.snapshot_manager import SnapshotManager


class AttributionService:
    """
    Cohort-based incrementality attribution with:
    - Delta-based view tracking (not cumulative)
    - Baseline computed BEFORE window (not contaminated)
    - Weighted credit split across content types
    - Confounder awareness
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.snapshot_mgr = SnapshotManager(db)
        self.confidence_scorer = ConfidenceScorer()

    async def calculate_baseline(
        self,
        creator_id: uuid.UUID,
        baseline_end: datetime,
        lookback_days: int = 14,
    ) -> dict[str, Any]:
        """
        Calculate rolling baseline metrics for a creator.

        CRITICAL FIX: Baseline window ends at baseline_end (typically window_start),
        not at "now minus exclude_days". This prevents baseline contamination.

        Args:
            creator_id: Creator to calculate baseline for
            baseline_end: End of baseline window (usually = attribution window start)
            lookback_days: Days to look back for baseline

        Returns:
            Dict with subs_per_day, rev_per_day, data_days, etc.
        """
        baseline_start = baseline_end - timedelta(days=lookback_days)

        # Count fans acquired in baseline period
        fans_result = await self.db.execute(
            select(func.count(Fan.id)).where(
                Fan.creator_id == creator_id,
                Fan.acquired_at >= baseline_start,
                Fan.acquired_at < baseline_end,
            )
        )
        total_fans = fans_result.scalar() or 0

        # Sum revenue in baseline period
        revenue_result = await self.db.execute(
            select(func.sum(RevenueEvent.amount))
            .join(Fan)
            .where(
                Fan.creator_id == creator_id,
                RevenueEvent.event_at >= baseline_start,
                RevenueEvent.event_at < baseline_end,
            )
        )
        total_revenue = revenue_result.scalar() or 0.0

        # Get view deltas for baseline period
        content_deltas = await self.snapshot_mgr.get_content_type_deltas(
            creator_id, baseline_start, baseline_end
        )
        total_delta_views = sum(ct["views_delta"] for ct in content_deltas.values())

        # Calculate days with data
        data_days = lookback_days  # Simplified; could check actual data presence

        if data_days < 3 or total_fans < 3:
            # Insufficient data - return conservative defaults
            return {
                "subs_per_day": 5.0,
                "rev_per_day": 100.0,
                "subs_per_1k_delta_views": 0.2,
                "data_days": data_days,
                "total_fans": total_fans,
                "total_revenue": total_revenue,
                "is_default": True,
            }

        views_k = total_delta_views / 1000 if total_delta_views > 0 else 1

        return {
            "subs_per_day": total_fans / data_days,
            "rev_per_day": total_revenue / data_days,
            "subs_per_1k_delta_views": total_fans / views_k if views_k > 0 else 0,
            "data_days": data_days,
            "total_fans": total_fans,
            "total_revenue": total_revenue,
            "total_delta_views": total_delta_views,
            "is_default": False,
        }

    async def attribute_window(
        self,
        creator_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
        content_type_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        Compute attribution for a time window using delta views.

        FIXES APPLIED:
        1. Baseline ends at window_start (not contaminated)
        2. Uses hours for window duration (not truncated days)
        3. Returns weighted credit split
        4. Checks for confounders

        Args:
            creator_id: Creator to analyze
            window_start: Start of attribution window
            window_end: End of attribution window
            content_type_filter: Optional filter to single content type

        Returns:
            Dict with attribution results, lift, confidence, etc.
        """
        # FIXED: Baseline computed relative to window_start
        baseline = await self.calculate_baseline(
            creator_id,
            baseline_end=window_start,
            lookback_days=14,
        )

        # FIXED: Use hours, not truncated days
        window_hours = (window_end - window_start).total_seconds() / 3600
        window_hours = max(window_hours, 1)  # Minimum 1 hour
        window_days = window_hours / 24

        # Get actual subs during window
        actual_subs_result = await self.db.execute(
            select(func.count(Fan.id)).where(
                Fan.creator_id == creator_id,
                Fan.acquired_at >= window_start,
                Fan.acquired_at < window_end,
            )
        )
        actual_subs = actual_subs_result.scalar() or 0

        # Get actual revenue during window
        actual_revenue_result = await self.db.execute(
            select(func.sum(RevenueEvent.amount))
            .join(Fan)
            .where(
                Fan.creator_id == creator_id,
                RevenueEvent.event_at >= window_start,
                RevenueEvent.event_at < window_end,
            )
        )
        actual_revenue = actual_revenue_result.scalar() or 0.0

        # Expected values based on baseline
        expected_subs = baseline["subs_per_day"] * window_days
        expected_revenue = baseline["rev_per_day"] * window_days

        # Get view deltas by content type
        content_type_deltas = await self.snapshot_mgr.get_content_type_deltas(
            creator_id, window_start, window_end
        )

        # Filter if requested
        if content_type_filter:
            content_type_deltas = {
                k: v
                for k, v in content_type_deltas.items()
                if k == content_type_filter
            }

        # Compute weighted credit split
        total_delta_views = sum(ct["views_delta"] for ct in content_type_deltas.values())
        credit_weights = {}

        if total_delta_views > 0:
            for ct, data in content_type_deltas.items():
                credit_weights[ct] = round(data["views_delta"] / total_delta_views, 3)

        # Check for confounders
        confounders = await self._check_confounders(creator_id, window_start, window_end)

        # Compute lifts
        subs_lift = (
            ((actual_subs / expected_subs) - 1) * 100 if expected_subs > 0 else 0
        )
        revenue_lift = (
            ((actual_revenue / expected_revenue) - 1) * 100 if expected_revenue > 0 else 0
        )

        # Compute confidence
        confidence = self.confidence_scorer.score(
            actual_events=actual_subs,
            expected_events=expected_subs,
            window_hours=window_hours,
            has_confounders=len(confounders) > 0,
            baseline_data_days=baseline["data_days"],
        )

        return {
            "creator_id": str(creator_id),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "window_hours": round(window_hours, 1),
            "baseline": {
                "subs_per_day": round(baseline["subs_per_day"], 2),
                "rev_per_day": round(baseline["rev_per_day"], 2),
                "data_days": baseline["data_days"],
                "is_default": baseline["is_default"],
            },
            "expected_subs": round(expected_subs, 1),
            "actual_subs": actual_subs,
            "subs_lift_pct": round(subs_lift, 1),
            "expected_revenue": round(expected_revenue, 2),
            "actual_revenue": round(actual_revenue, 2),
            "revenue_lift_pct": round(revenue_lift, 1),
            "content_type_deltas": {
                ct: {
                    "views_delta": data["views_delta"],
                    "posts_with_views": data["posts_with_views"],
                }
                for ct, data in content_type_deltas.items()
            },
            "credit_weights": credit_weights,
            "total_delta_views": total_delta_views,
            "confounders": confounders,
            "confidence": confidence.to_dict(),
            "recommendation_tier": "confident" if confidence.score >= 0.7 else "hypothesis",
        }

    async def _check_confounders(
        self,
        creator_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict]:
        """Check if any confounder events overlap with the window."""
        result = await self.db.execute(
            select(ConfounderEvent).where(
                ConfounderEvent.creator_id == creator_id,
                ConfounderEvent.event_start <= window_end,
                # Event end is null (point event) or extends into window
                (
                    (ConfounderEvent.event_end >= window_start)
                    | (ConfounderEvent.event_end.is_(None))
                ),
            )
        )
        events = result.scalars().all()

        return [
            {
                "type": e.event_type,
                "description": e.description,
                "impact": e.estimated_impact,
                "start": e.event_start.isoformat(),
            }
            for e in events
        ]

    async def get_content_type_performance(
        self,
        creator_id: uuid.UUID,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Get performance breakdown by content type.

        Returns lift and confidence for each content type.
        """
        window_end = datetime.utcnow()
        window_start = window_end - timedelta(days=days)

        # Get overall attribution
        overall = await self.attribute_window(creator_id, window_start, window_end)

        # Get fans by attributed content type
        fans_by_type_result = await self.db.execute(
            select(Fan.attributed_content_type, func.count(Fan.id))
            .where(
                Fan.creator_id == creator_id,
                Fan.acquired_at >= window_start,
                Fan.acquired_at < window_end,
                Fan.attributed_content_type.isnot(None),
            )
            .group_by(Fan.attributed_content_type)
        )
        fans_by_type = {row[0]: row[1] for row in fans_by_type_result.fetchall()}

        # Build performance by content type
        performance = {}
        baseline_subs_per_1k = overall["baseline"]["subs_per_day"] * days / (
            overall["total_delta_views"] / 1000 if overall["total_delta_views"] > 0 else 1
        )

        for ct, deltas in overall["content_type_deltas"].items():
            views_k = deltas["views_delta"] / 1000 if deltas["views_delta"] > 0 else 0
            attributed_subs = fans_by_type.get(ct, 0)

            # Calculate subs per 1K views for this content type
            subs_per_1k = attributed_subs / views_k if views_k > 0 else 0

            # Lift vs baseline
            lift_pct = (
                ((subs_per_1k / baseline_subs_per_1k) - 1) * 100
                if baseline_subs_per_1k > 0
                else 0
            )

            # Confidence for this content type
            expected_subs = baseline_subs_per_1k * views_k
            confidence = self.confidence_scorer.score(
                actual_events=attributed_subs,
                expected_events=expected_subs,
                window_hours=days * 24,
                has_confounders=len(overall["confounders"]) > 0,
                baseline_data_days=overall["baseline"]["data_days"],
            )

            performance[ct] = {
                "views_delta": deltas["views_delta"],
                "posts_with_views": deltas["posts_with_views"],
                "attributed_subs": attributed_subs,
                "subs_per_1k_views": round(subs_per_1k, 2),
                "lift_pct": round(lift_pct, 1),
                "credit_weight": overall["credit_weights"].get(ct, 0),
                "confidence": confidence.to_dict(),
                "tier": "confident" if confidence.score >= 0.7 else "hypothesis",
            }

        return {
            "creator_id": str(creator_id),
            "period_days": days,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "total_subs": overall["actual_subs"],
            "total_views": overall["total_delta_views"],
            "has_confounders": len(overall["confounders"]) > 0,
            "confounders": overall["confounders"],
            "content_types": performance,
        }

    async def attribute_fans(
        self,
        creator_id: uuid.UUID,
        attribution_window_hours: int = 48,
    ) -> dict[str, int]:
        """
        Attribute unattributed fans using weighted credit split.

        Instead of "winner takes all" (highest views), each content type
        gets proportional credit based on view share in the attribution window.

        Returns count of fans attributed by method.
        """
        # Get unattributed fans
        result = await self.db.execute(
            select(Fan).where(
                Fan.creator_id == creator_id,
                Fan.attributed_content_type.is_(None),
            )
        )
        fans = result.scalars().all()

        stats = {"referral_link": 0, "weighted_window": 0, "no_data": 0}

        for fan in fans:
            # Method 1: Referral link (deterministic, highest confidence)
            if fan.referral_link_id:
                # Would need to look up referral link's content_type_hint
                # For now, skip this path
                pass

            # Method 2: Weighted attribution by view delta share
            window_start = fan.acquired_at - timedelta(hours=attribution_window_hours)

            content_deltas = await self.snapshot_mgr.get_content_type_deltas(
                creator_id, window_start, fan.acquired_at
            )

            if not content_deltas:
                stats["no_data"] += 1
                continue

            total_views = sum(ct["views_delta"] for ct in content_deltas.values())

            if total_views == 0:
                stats["no_data"] += 1
                continue

            # Compute weights
            weights = {}
            for ct, data in content_deltas.items():
                if data["views_delta"] > 0:
                    weights[ct] = data["views_delta"] / total_views

            if not weights:
                stats["no_data"] += 1
                continue

            # Primary attribution goes to highest weight
            primary_type = max(weights, key=weights.get)

            fan.attributed_content_type = primary_type
            fan.attribution_method = "weighted_window"
            fan.attribution_weights = weights

            # Confidence based on concentration of weight
            max_weight = max(weights.values())
            fan.attribution_confidence = 0.3 + (max_weight * 0.5)  # 0.3 - 0.8 range

            stats["weighted_window"] += 1

        await self.db.commit()

        return stats
