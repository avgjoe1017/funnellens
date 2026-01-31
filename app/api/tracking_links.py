"""Tracking Links API endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Creator, Fan, RevenueEvent, TrackingLink
from app.models.tracking import LinkPlatform
from app.models.taxonomy import ContentType

router = APIRouter(prefix="/api/v1/tracking-links", tags=["tracking-links"])


# ============ Schemas ============


class TrackingLinkCreate(BaseModel):
    """Request to create a tracking link."""

    creator_id: str
    source_platform: Literal["tiktok", "instagram", "twitter", "reddit", "youtube", "other"]
    content_type: str
    campaign: str | None = None
    custom_code: str | None = None


class TrackingLinkResponse(BaseModel):
    """Tracking link response."""

    id: str
    code: str
    full_url: str
    source_platform: str
    content_type: str
    campaign: str | None
    total_clicks: int
    total_subs: int
    total_revenue: float
    conversion_rate: float | None
    avg_fan_ltv: float | None
    created_at: str
    is_active: bool


class TrackingLinkStats(BaseModel):
    """Detailed statistics for a tracking link."""

    link_id: str
    code: str
    period_days: int
    clicks: int
    subs: int
    revenue: float
    conversion_rate: float | None
    avg_ltv: float
    ltv_vs_baseline_pct: float
    churn_rate: float
    churn_vs_baseline_pct: float


class FanSummary(BaseModel):
    """Summary of a fan for cohort display."""

    id: str
    acquired_at: str
    total_spend: float
    churned: bool
    last_active: str | None


class TrackingLinkFanCohort(BaseModel):
    """Fan cohort from a tracking link."""

    link_id: str
    fans: list[FanSummary]
    cohort_metrics: dict


class ContentTypeAnalytics(BaseModel):
    """Analytics aggregated by content type."""

    content_type: str
    total_links: int
    total_subs: int
    total_revenue: float
    avg_ltv: float
    churn_rate: float


# ============ Helper Functions ============


def _link_to_response(link: TrackingLink) -> TrackingLinkResponse:
    """Convert TrackingLink model to response."""
    return TrackingLinkResponse(
        id=str(link.id),
        code=link.code,
        full_url=link.destination_url,
        source_platform=link.source_platform.value,
        content_type=link.content_type,
        campaign=link.campaign,
        total_clicks=link.total_clicks or 0,
        total_subs=link.total_subs or 0,
        total_revenue=link.total_revenue or 0,
        conversion_rate=link.conversion_rate,
        avg_fan_ltv=link.avg_fan_ltv,
        created_at=link.created_at.isoformat() if link.created_at else "",
        is_active=link.is_active,
    )


def _compute_churn_rate(fans: list[Fan], days: int) -> float:
    """Compute churn rate for a list of fans within days."""
    if not fans:
        return 0
    churned = len([f for f in fans if f.churned_at])
    return churned / len(fans)


def _fan_to_summary(fan: Fan) -> FanSummary:
    """Convert Fan to summary."""
    return FanSummary(
        id=str(fan.id)[:8] + "...",
        acquired_at=fan.acquired_at.isoformat() if fan.acquired_at else "",
        total_spend=fan.total_spend or 0,
        churned=fan.churned_at is not None,
        last_active=None,  # Would need activity tracking
    )


# ============ Endpoints ============


@router.post("/", response_model=TrackingLinkResponse)
async def create_tracking_link(
    data: TrackingLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> TrackingLinkResponse:
    """
    Create a new tracking link for a creator.

    The link is tagged with content type at creation, enabling
    automatic attribution when fans subscribe via this link.
    """
    # Validate creator_id
    try:
        creator_uuid = uuid.UUID(data.creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    # Validate content type
    valid_content_types = [ct.value for ct in ContentType]
    if data.content_type not in valid_content_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type: {data.content_type}. Valid types: {valid_content_types}",
        )

    # Get creator
    result = await db.execute(select(Creator).where(Creator.id == creator_uuid))
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    # Generate code if not provided
    if data.custom_code:
        code = data.custom_code.upper().replace(" ", "_")
    else:
        # Auto-generate: {PLATFORM}_{CONTENT_TYPE}_{MONTH}
        platform_prefix = data.source_platform[:2].upper()
        content_prefix = data.content_type[:5].upper()
        month = datetime.utcnow().strftime("%b").upper()
        code = f"{platform_prefix}_{content_prefix}_{month}"

    # Check for duplicate
    result = await db.execute(
        select(TrackingLink).where(
            TrackingLink.creator_id == creator_uuid,
            TrackingLink.code == code,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Link code '{code}' already exists for this creator",
        )

    # Build destination URL
    username = creator.of_username or creator.name.lower().replace(" ", "")
    destination_url = f"https://onlyfans.com/{username}?c={code}"

    # Map platform string to enum
    platform_map = {
        "tiktok": LinkPlatform.tiktok,
        "instagram": LinkPlatform.instagram,
        "twitter": LinkPlatform.twitter,
        "reddit": LinkPlatform.reddit,
        "youtube": LinkPlatform.youtube,
        "other": LinkPlatform.other,
    }

    # Create link
    link = TrackingLink(
        creator_id=creator_uuid,
        code=code,
        destination_url=destination_url,
        source_platform=platform_map[data.source_platform],
        content_type=data.content_type,
        campaign=data.campaign,
        total_clicks=0,
        total_subs=0,
        total_revenue=0,
    )

    db.add(link)
    await db.commit()
    await db.refresh(link)

    return _link_to_response(link)


@router.get("/creator/{creator_id}", response_model=list[TrackingLinkResponse])
async def get_creator_tracking_links(
    creator_id: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[TrackingLinkResponse]:
    """Get all tracking links for a creator."""
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    query = select(TrackingLink).where(TrackingLink.creator_id == creator_uuid)

    if not include_inactive:
        query = query.where(TrackingLink.is_active == True)

    query = query.order_by(TrackingLink.created_at.desc())

    result = await db.execute(query)
    links = result.scalars().all()

    return [_link_to_response(link) for link in links]


@router.get("/{link_id}", response_model=TrackingLinkResponse)
async def get_tracking_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrackingLinkResponse:
    """Get a single tracking link by ID."""
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link_id format")

    result = await db.execute(select(TrackingLink).where(TrackingLink.id == link_uuid))
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    return _link_to_response(link)


@router.get("/{link_id}/stats", response_model=TrackingLinkStats)
async def get_tracking_link_stats(
    link_id: str,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
    db: AsyncSession = Depends(get_db),
) -> TrackingLinkStats:
    """
    Get detailed statistics for a tracking link.

    Includes comparison to creator baseline (fans from all sources).
    """
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link_id format")

    result = await db.execute(select(TrackingLink).where(TrackingLink.id == link_uuid))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Get fans from this link in period
    result = await db.execute(
        select(Fan).where(
            Fan.tracking_link_id == link_uuid,
            Fan.acquired_at >= start_date,
        )
    )
    link_fans = list(result.scalars().all())

    # Get all fans for baseline comparison
    result = await db.execute(
        select(Fan).where(
            Fan.creator_id == link.creator_id,
            Fan.acquired_at >= start_date,
        )
    )
    all_fans = list(result.scalars().all())

    # Compute metrics
    link_subs = len(link_fans)
    link_revenue = sum(f.total_spend or 0 for f in link_fans)
    link_ltv = link_revenue / link_subs if link_subs > 0 else 0

    all_ltv = sum(f.total_spend or 0 for f in all_fans) / len(all_fans) if all_fans else 0

    # Churn rates
    link_churned = len([f for f in link_fans if f.churned_at])
    link_churn_rate = link_churned / link_subs if link_subs > 0 else 0

    all_churned = len([f for f in all_fans if f.churned_at])
    all_churn_rate = all_churned / len(all_fans) if all_fans else 0

    return TrackingLinkStats(
        link_id=str(link.id),
        code=link.code,
        period_days=days,
        clicks=link.total_clicks or 0,
        subs=link_subs,
        revenue=link_revenue,
        conversion_rate=link_subs / link.total_clicks if link.total_clicks and link.total_clicks > 0 else None,
        avg_ltv=link_ltv,
        ltv_vs_baseline_pct=((link_ltv / all_ltv) - 1) * 100 if all_ltv > 0 else 0,
        churn_rate=link_churn_rate,
        churn_vs_baseline_pct=((link_churn_rate / all_churn_rate) - 1) * 100 if all_churn_rate > 0 else 0,
    )


@router.get("/{link_id}/fans", response_model=TrackingLinkFanCohort)
async def get_tracking_link_fans(
    link_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db),
) -> TrackingLinkFanCohort:
    """Get fans who subscribed via this tracking link."""
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link_id format")

    result = await db.execute(select(TrackingLink).where(TrackingLink.id == link_uuid))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Get paginated fans
    result = await db.execute(
        select(Fan)
        .where(Fan.tracking_link_id == link_uuid)
        .order_by(Fan.acquired_at.desc())
        .offset(offset)
        .limit(limit)
    )
    fans = list(result.scalars().all())

    # Get all fans for cohort metrics
    result = await db.execute(
        select(Fan).where(Fan.tracking_link_id == link_uuid)
    )
    all_link_fans = list(result.scalars().all())

    # Cohort metrics
    total_revenue = sum(f.total_spend or 0 for f in all_link_fans)
    total_fans = len(all_link_fans)

    cohort_metrics = {
        "total_fans": total_fans,
        "total_revenue": total_revenue,
        "avg_ltv": total_revenue / total_fans if total_fans > 0 else 0,
        "churn_rate": _compute_churn_rate(all_link_fans, 30),
        "active_fans": len([f for f in all_link_fans if not f.churned_at]),
    }

    return TrackingLinkFanCohort(
        link_id=str(link_uuid),
        fans=[_fan_to_summary(f) for f in fans],
        cohort_metrics=cohort_metrics,
    )


@router.delete("/{link_id}")
async def deactivate_tracking_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deactivate a tracking link (soft delete, preserves data)."""
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link_id format")

    result = await db.execute(select(TrackingLink).where(TrackingLink.id == link_uuid))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    link.is_active = False
    await db.commit()

    return {"status": "deactivated", "link_id": str(link_uuid)}


@router.post("/{link_id}/refresh-metrics")
async def refresh_link_metrics(
    link_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrackingLinkResponse:
    """Manually refresh aggregate metrics for a tracking link."""
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link_id format")

    result = await db.execute(select(TrackingLink).where(TrackingLink.id == link_uuid))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Get all fans from this link
    result = await db.execute(
        select(Fan).where(Fan.tracking_link_id == link_uuid)
    )
    fans = list(result.scalars().all())

    # Update aggregates
    link.total_subs = len(fans)
    link.total_revenue = sum(f.total_spend or 0 for f in fans)
    link.avg_fan_ltv = link.total_revenue / link.total_subs if link.total_subs > 0 else None

    if fans:
        link.last_sub_at = max(f.acquired_at for f in fans)

    await db.commit()
    await db.refresh(link)

    return _link_to_response(link)


# ============ Analytics Endpoints ============


@router.get("/analytics/by-content-type/{creator_id}")
async def get_link_analytics_by_content_type(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Aggregate tracking link performance by content type.

    This is the KEY INSIGHT: which content types drive the best fans?
    """
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Get all links for creator
    result = await db.execute(
        select(TrackingLink).where(TrackingLink.creator_id == creator_uuid)
    )
    links = list(result.scalars().all())

    # Group by content type
    by_content_type: dict[str, dict] = {}

    for link in links:
        ct = link.content_type

        # Get fans from this link in period
        result = await db.execute(
            select(Fan).where(
                Fan.tracking_link_id == link.id,
                Fan.acquired_at >= start_date,
            )
        )
        fans = list(result.scalars().all())

        if ct not in by_content_type:
            by_content_type[ct] = {
                "content_type": ct,
                "links": 0,
                "subs": 0,
                "revenue": 0,
                "fans": [],
            }

        by_content_type[ct]["links"] += 1
        by_content_type[ct]["subs"] += len(fans)
        by_content_type[ct]["revenue"] += sum(f.total_spend or 0 for f in fans)
        by_content_type[ct]["fans"].extend(fans)

    # Compute averages
    results = []
    for ct, data in by_content_type.items():
        avg_ltv = data["revenue"] / data["subs"] if data["subs"] > 0 else 0
        results.append(
            ContentTypeAnalytics(
                content_type=ct,
                total_links=data["links"],
                total_subs=data["subs"],
                total_revenue=data["revenue"],
                avg_ltv=avg_ltv,
                churn_rate=_compute_churn_rate(data["fans"], 30),
            )
        )

    # Sort by revenue
    results.sort(key=lambda x: x.total_revenue, reverse=True)

    return {
        "creator_id": creator_id,
        "period_days": days,
        "by_content_type": [r.model_dump() for r in results],
    }


@router.get("/analytics/by-platform/{creator_id}")
async def get_link_analytics_by_platform(
    creator_id: str,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate tracking link performance by source platform."""
    try:
        creator_uuid = uuid.UUID(creator_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid creator_id format")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Get all links for creator
    result = await db.execute(
        select(TrackingLink).where(TrackingLink.creator_id == creator_uuid)
    )
    links = list(result.scalars().all())

    # Group by platform
    by_platform: dict[str, dict] = {}

    for link in links:
        platform = link.source_platform.value

        # Get fans from this link in period
        result = await db.execute(
            select(Fan).where(
                Fan.tracking_link_id == link.id,
                Fan.acquired_at >= start_date,
            )
        )
        fans = list(result.scalars().all())

        if platform not in by_platform:
            by_platform[platform] = {
                "platform": platform,
                "links": 0,
                "subs": 0,
                "revenue": 0,
                "fans": [],
            }

        by_platform[platform]["links"] += 1
        by_platform[platform]["subs"] += len(fans)
        by_platform[platform]["revenue"] += sum(f.total_spend or 0 for f in fans)
        by_platform[platform]["fans"].extend(fans)

    # Compute results
    results = []
    for platform, data in by_platform.items():
        avg_ltv = data["revenue"] / data["subs"] if data["subs"] > 0 else 0
        results.append({
            "platform": platform,
            "total_links": data["links"],
            "total_subs": data["subs"],
            "total_revenue": data["revenue"],
            "avg_ltv": avg_ltv,
            "churn_rate": _compute_churn_rate(data["fans"], 30),
        })

    # Sort by revenue
    results.sort(key=lambda x: x["total_revenue"], reverse=True)

    return {
        "creator_id": creator_id,
        "period_days": days,
        "by_platform": results,
    }
