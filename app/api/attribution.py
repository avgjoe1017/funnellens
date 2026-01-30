"""Attribution API endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.attribution import AttributionService

router = APIRouter(prefix="/api/v1/attribution", tags=["attribution"])


class BaselineResponse(BaseModel):
    """Baseline metrics response."""

    subs_per_day: float
    rev_per_day: float
    data_days: int
    is_default: bool


class ConfidenceResponse(BaseModel):
    """Confidence score response."""

    score: float
    level: str
    reasons: list[str]
    min_events_met: bool


class ContentTypeMetrics(BaseModel):
    """Metrics for a single content type."""

    views_delta: int
    posts_with_views: int
    attributed_subs: int | None = None
    subs_per_1k_views: float | None = None
    lift_pct: float | None = None
    credit_weight: float
    confidence: ConfidenceResponse | None = None
    tier: str | None = None


class AttributionWindowResponse(BaseModel):
    """Response from attribution window analysis."""

    creator_id: str
    window_start: str
    window_end: str
    window_hours: float
    baseline: BaselineResponse
    expected_subs: float
    actual_subs: int
    subs_lift_pct: float
    expected_revenue: float
    actual_revenue: float
    revenue_lift_pct: float
    content_type_deltas: dict[str, dict]
    credit_weights: dict[str, float]
    total_delta_views: int
    confounders: list[dict]
    confidence: ConfidenceResponse
    recommendation_tier: str


class ContentTypePerformanceResponse(BaseModel):
    """Response from content type performance analysis."""

    creator_id: str
    period_days: int
    window_start: str
    window_end: str
    total_subs: int
    total_views: int
    has_confounders: bool
    confounders: list[dict]
    content_types: dict[str, dict]


class AttributeFansResponse(BaseModel):
    """Response from fan attribution."""

    referral_link: int
    weighted_window: int
    no_data: int


@router.get("/window/{creator_id}", response_model=AttributionWindowResponse)
async def get_attribution_window(
    creator_id: str,
    days: Annotated[int, Query(ge=1, le=90, description="Days to analyze")] = 7,
    content_type: Annotated[str | None, Query(description="Filter to specific content type")] = None,
    db: AsyncSession = Depends(get_db),
) -> AttributionWindowResponse:
    """
    Analyze attribution for a time window.

    Returns:
    - Baseline metrics (pre-window)
    - Actual vs expected subs/revenue
    - Lift percentages
    - View deltas by content type
    - Weighted credit split
    - Confidence score and tier
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    service = AttributionService(db)

    window_end = datetime.utcnow()
    window_start = window_end - timedelta(days=days)

    result = await service.attribute_window(
        creator_uuid,
        window_start,
        window_end,
        content_type_filter=content_type,
    )

    return AttributionWindowResponse(**result)


@router.get("/performance/{creator_id}", response_model=ContentTypePerformanceResponse)
async def get_content_type_performance(
    creator_id: str,
    days: Annotated[int, Query(ge=1, le=90, description="Days to analyze")] = 30,
    db: AsyncSession = Depends(get_db),
) -> ContentTypePerformanceResponse:
    """
    Get performance breakdown by content type.

    Returns lift, confidence, and tier for each content type.
    Use this to determine which content types are converting best.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    service = AttributionService(db)

    result = await service.get_content_type_performance(creator_uuid, days)

    return ContentTypePerformanceResponse(**result)


@router.post("/attribute-fans/{creator_id}", response_model=AttributeFansResponse)
async def attribute_fans(
    creator_id: str,
    window_hours: Annotated[int, Query(ge=12, le=168, description="Attribution window in hours")] = 48,
    db: AsyncSession = Depends(get_db),
) -> AttributeFansResponse:
    """
    Attribute unattributed fans to content types.

    Uses weighted credit split based on view deltas in the attribution window
    before each fan's acquisition time.

    This is a write operation - it updates fan records with attribution data.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    service = AttributionService(db)

    stats = await service.attribute_fans(creator_uuid, window_hours)

    return AttributeFansResponse(**stats)


@router.get("/baseline/{creator_id}")
async def get_baseline(
    creator_id: str,
    lookback_days: Annotated[int, Query(ge=7, le=30, description="Days to look back")] = 14,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get baseline metrics for a creator.

    Baseline is computed from historical data and used to measure lift.
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    service = AttributionService(db)

    baseline = await service.calculate_baseline(
        creator_uuid,
        baseline_end=datetime.utcnow(),
        lookback_days=lookback_days,
    )

    return baseline
