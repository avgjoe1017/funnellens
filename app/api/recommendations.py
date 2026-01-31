"""Recommendations API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.attribution import AttributionService
from app.services.recommendation import (
    RecommendationAction,
    RecommendationEngine,
    RecommendationTier,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


class ContentRecommendationResponse(BaseModel):
    """Single content type recommendation."""

    content_type: str
    action: str
    tier: str
    lift_pct: float | None
    confidence_score: float
    current_posts_per_week: float
    suggested_posts_per_week: float | None
    reasoning: str
    caveats: list[str]


class WeeklyPlanResponse(BaseModel):
    """Weekly posting plan."""

    total_posts: int
    breakdown: dict[str, int]
    rationale: str


class RecommendationReportResponse(BaseModel):
    """Full recommendation report."""

    creator_id: str
    period_days: int
    total_subs: int
    total_revenue: float
    has_confounders: bool
    confounder_warning: str | None
    recommendations: list[ContentRecommendationResponse]
    weekly_plan: WeeklyPlanResponse | None
    top_performer: str | None
    underperformer: str | None
    data_quality_notes: list[str]


class TextReportResponse(BaseModel):
    """Text-formatted report for email/display."""

    report: str


@router.get("/report/{creator_id}", response_model=RecommendationReportResponse)
async def get_recommendation_report(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90, description="Days to analyze")] = 30,
    db: AsyncSession = Depends(get_db),
) -> RecommendationReportResponse:
    """
    Get full recommendation report for a creator.

    Analyzes content performance and generates actionable recommendations
    with confidence tiers (confident vs hypothesis).

    Includes:
    - Per-content-type recommendations with suggested actions
    - Weekly posting plan
    - Confounder warnings
    - Data quality assessment
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    # Get performance data
    attribution_service = AttributionService(db)
    performance_data = await attribution_service.get_content_type_performance(
        creator_uuid, days
    )

    # Get attribution window data for revenue
    from datetime import datetime, timedelta

    window_end = datetime.utcnow()
    window_start = window_end - timedelta(days=days)
    attribution_data = await attribution_service.attribute_window(
        creator_uuid, window_start, window_end
    )

    # Generate recommendations
    engine = RecommendationEngine()
    report = engine.generate_report(
        creator_id=creator_id,
        performance_data=performance_data,
        attribution_data=attribution_data,
    )

    # Convert to response model
    recommendations = [
        ContentRecommendationResponse(
            content_type=r.content_type,
            action=r.action.value,
            tier=r.tier.value,
            lift_pct=r.lift_pct,
            confidence_score=r.confidence_score,
            current_posts_per_week=r.current_posts_per_week,
            suggested_posts_per_week=r.suggested_posts_per_week,
            reasoning=r.reasoning,
            caveats=r.caveats,
        )
        for r in report.recommendations
    ]

    weekly_plan = None
    if report.weekly_plan:
        weekly_plan = WeeklyPlanResponse(
            total_posts=report.weekly_plan.total_posts,
            breakdown=report.weekly_plan.breakdown,
            rationale=report.weekly_plan.rationale,
        )

    return RecommendationReportResponse(
        creator_id=report.creator_id,
        period_days=report.period_days,
        total_subs=report.total_subs,
        total_revenue=report.total_revenue,
        has_confounders=report.has_confounders,
        confounder_warning=report.confounder_warning,
        recommendations=recommendations,
        weekly_plan=weekly_plan,
        top_performer=report.top_performer,
        underperformer=report.underperformer,
        data_quality_notes=report.data_quality_notes,
    )


@router.get("/report/{creator_id}/text", response_model=TextReportResponse)
async def get_recommendation_report_text(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90, description="Days to analyze")] = 30,
    db: AsyncSession = Depends(get_db),
) -> TextReportResponse:
    """
    Get recommendation report as formatted text.

    Suitable for email digests or plain text display.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    # Get performance data
    attribution_service = AttributionService(db)
    performance_data = await attribution_service.get_content_type_performance(
        creator_uuid, days
    )

    # Get attribution window data
    from datetime import datetime, timedelta

    window_end = datetime.utcnow()
    window_start = window_end - timedelta(days=days)
    attribution_data = await attribution_service.attribute_window(
        creator_uuid, window_start, window_end
    )

    # Generate recommendations
    engine = RecommendationEngine()
    report = engine.generate_report(
        creator_id=creator_id,
        performance_data=performance_data,
        attribution_data=attribution_data,
    )

    # Format as text
    text = engine.format_report_text(report)

    return TextReportResponse(report=text)


@router.get("/quick/{creator_id}")
async def get_quick_recommendations(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90, description="Days to analyze")] = 30,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get quick summary of top recommendations.

    Returns just the actionable items without full analysis.
    Useful for dashboards or quick checks.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    # Get performance data
    attribution_service = AttributionService(db)
    performance_data = await attribution_service.get_content_type_performance(
        creator_uuid, days
    )

    # Generate recommendations
    engine = RecommendationEngine()
    report = engine.generate_report(
        creator_id=creator_id,
        performance_data=performance_data,
    )

    # Extract quick summary
    increase = [
        r.content_type
        for r in report.recommendations
        if r.action == RecommendationAction.INCREASE
    ]
    decrease = [
        r.content_type
        for r in report.recommendations
        if r.action == RecommendationAction.DECREASE
    ]
    test = [
        r.content_type
        for r in report.recommendations
        if r.action == RecommendationAction.TEST
    ]

    return {
        "creator_id": creator_id,
        "period_days": days,
        "has_confounders": report.has_confounders,
        "top_performer": report.top_performer,
        "actions": {
            "increase": increase,
            "decrease": decrease,
            "test": test,
        },
        "data_quality_issues": len(report.data_quality_notes),
    }


@router.get("/rankings/{creator_id}")
async def get_content_rankings(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90, description="Days to analyze")] = 30,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get content types ranked by performance.

    Returns a simple ranking from best to worst performer
    based on lift percentage.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    # Get performance data
    attribution_service = AttributionService(db)
    performance_data = await attribution_service.get_content_type_performance(
        creator_uuid, days
    )

    content_types = performance_data.get("content_types", {})

    # Build rankings
    rankings = []
    for ct_name, ct_data in content_types.items():
        lift = ct_data.get("lift_pct")
        confidence = ct_data.get("confidence", {})
        tier = ct_data.get("tier", "hypothesis")

        rankings.append({
            "rank": 0,  # Will be set after sorting
            "content_type": ct_name,
            "lift_pct": lift,
            "tier": tier,
            "confidence_score": confidence.get("score", 0) if confidence else 0,
            "posts_analyzed": ct_data.get("posts_with_views", 0),
        })

    # Sort by lift (descending)
    rankings.sort(key=lambda x: x["lift_pct"] or float("-inf"), reverse=True)

    # Assign ranks
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return {
        "creator_id": creator_id,
        "period_days": days,
        "has_confounders": performance_data.get("has_confounders", False),
        "rankings": rankings,
    }
