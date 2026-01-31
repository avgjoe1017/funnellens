"""Fan and revenue event models."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.creator import Creator
    from app.models.tracking import TrackingLink


class AttributionMethod(str, Enum):
    """How a fan was attributed to content."""

    REFERRAL_LINK = "referral_link"
    WEIGHTED_WINDOW = "weighted_window"
    CAMPAIGN = "campaign"


class RevenueEventType(str, Enum):
    """Types of revenue events."""

    SUBSCRIPTION = "subscription"
    RENEWAL = "renewal"
    TIP = "tip"
    PPV = "ppv"
    MESSAGE = "message"


class Fan(Base):
    """A subscriber/fan of a creator."""

    __tablename__ = "fans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False
    )

    # Salted hash for privacy (per-agency salt)
    external_id_hash: Mapped[str | None] = mapped_column(String(64))

    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    referral_link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Tracking link (deterministic attribution)
    tracking_link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracking_links.id")
    )
    tracking_link_code: Mapped[str | None] = mapped_column(String(50))

    # Attribution
    attributed_content_type: Mapped[str | None] = mapped_column(String(50))
    attribution_method: Mapped[str | None] = mapped_column(String(20))
    attribution_confidence: Mapped[float | None] = mapped_column(Float)

    # Weighted attribution (for multi-content-type credit)
    # Example: {"storytime": 0.6, "grwm": 0.4}
    attribution_weights: Mapped[dict | None] = mapped_column(JSON)

    # Lifecycle
    churned_at: Mapped[datetime | None] = mapped_column(DateTime)
    ltv_30d: Mapped[float | None] = mapped_column(Float)
    ltv_90d: Mapped[float | None] = mapped_column(Float)
    total_spend: Mapped[float] = mapped_column(Float, default=0)

    # Relationships
    creator: Mapped["Creator"] = relationship("Creator", back_populates="fans")
    revenue_events: Mapped[list["RevenueEvent"]] = relationship(
        "RevenueEvent", back_populates="fan", cascade="all, delete-orphan"
    )
    tracking_link: Mapped["TrackingLink | None"] = relationship(
        "TrackingLink", back_populates="fans"
    )

    __table_args__ = (
        Index("idx_fans_creator", "creator_id"),
        Index("idx_fans_acquired", "acquired_at"),
        Index("idx_fans_content_type", "attributed_content_type"),
        Index("idx_fans_tracking_link", "tracking_link_id"),
    )


class RevenueEvent(Base):
    """A monetization event from a fan."""

    __tablename__ = "revenue_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fans.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    fan: Mapped["Fan"] = relationship("Fan", back_populates="revenue_events")

    __table_args__ = (
        Index("idx_revenue_fan", "fan_id"),
        Index("idx_revenue_event_at", "event_at"),
    )
