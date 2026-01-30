"""Creator model - the talent managed by agencies."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agency import Agency
    from app.models.confounder import ConfounderEvent
    from app.models.fan import Fan
    from app.models.social_post import PostSnapshot, SocialPost


class CreatorStatus(str, Enum):
    """Creator account status."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Creator(Base):
    """A creator managed by an agency."""

    __tablename__ = "creators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tiktok_handle: Mapped[str | None] = mapped_column(String(100))
    instagram_handle: Mapped[str | None] = mapped_column(String(100))
    of_account_id: Mapped[str | None] = mapped_column(String(100))

    # Baselines (computed from pre-window periods)
    baseline_subs_per_day: Mapped[float | None] = mapped_column(Float)
    baseline_rev_per_day: Mapped[float | None] = mapped_column(Float)
    baseline_subs_per_1k_delta_views: Mapped[float | None] = mapped_column(Float)
    baseline_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Calibration metadata
    optimal_attribution_window_hours: Mapped[int] = mapped_column(
        Integer, default=48
    )

    status: Mapped[str] = mapped_column(
        String(20), default=CreatorStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    agency: Mapped["Agency"] = relationship("Agency", back_populates="creators")
    posts: Mapped[list["SocialPost"]] = relationship(
        "SocialPost", back_populates="creator", cascade="all, delete-orphan"
    )
    fans: Mapped[list["Fan"]] = relationship(
        "Fan", back_populates="creator", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["PostSnapshot"]] = relationship(
        "PostSnapshot", back_populates="creator", cascade="all, delete-orphan"
    )
    confounder_events: Mapped[list["ConfounderEvent"]] = relationship(
        "ConfounderEvent", back_populates="creator", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_creators_agency", "agency_id"),
        Index("idx_creators_status", "status"),
    )
