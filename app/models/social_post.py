"""Social media post and snapshot models."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.creator import Creator
    from app.models.import_log import Import


class Platform(str, Enum):
    """Social media platforms."""

    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class TagSource(str, Enum):
    """How content type was assigned."""

    ML_SUGGESTED = "ml_suggested"
    USER_CONFIRMED = "user_confirmed"
    USER_OVERRIDE = "user_override"


class SocialPost(Base):
    """
    A social media post.

    Metrics here are CUMULATIVE (latest known values).
    For period-specific metrics, use PostSnapshot deltas.
    """

    __tablename__ = "social_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_post_id: Mapped[str | None] = mapped_column(String(100))
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # CUMULATIVE metrics (latest snapshot)
    views_cumulative: Mapped[int] = mapped_column(Integer, default=0)
    likes_cumulative: Mapped[int] = mapped_column(Integer, default=0)
    comments_cumulative: Mapped[int] = mapped_column(Integer, default=0)
    shares_cumulative: Mapped[int] = mapped_column(Integer, default=0)
    saves_cumulative: Mapped[int] = mapped_column(Integer, default=0)

    # Content metadata
    caption: Mapped[str | None] = mapped_column(Text)
    caption_embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float))
    video_duration_seconds: Mapped[float | None] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(String(500))

    # Classification
    content_type: Mapped[str | None] = mapped_column(String(50))
    content_type_confidence: Mapped[float | None] = mapped_column(Float)
    content_type_source: Mapped[str | None] = mapped_column(String(20))
    campaign_tag: Mapped[str | None] = mapped_column(String(100))

    # Attribution (computed from deltas)
    attributed_subs: Mapped[int | None] = mapped_column(Integer)
    attributed_revenue: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    creator: Mapped["Creator"] = relationship("Creator", back_populates="posts")
    snapshots: Mapped[list["PostSnapshot"]] = relationship(
        "PostSnapshot", back_populates="post", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_posts_creator_posted", "creator_id", "posted_at"),
        Index("idx_posts_content_type", "content_type"),
        Index(
            "idx_posts_platform_id",
            "platform",
            "platform_post_id",
            unique=True,
            postgresql_where=(mapped_column("platform_post_id").isnot(None)),
        ),
    )


class PostSnapshot(Base):
    """
    Point-in-time snapshot of post metrics.

    CRITICAL: Deltas between snapshots give us views/engagement DURING a specific period.
    This fixes the cumulative-views attribution problem from v1.0.

    delta_views = snapshot_2.views - snapshot_1.views
    """

    __tablename__ = "post_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_posts.id"), nullable=False
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Cumulative values at this snapshot
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)

    # Import metadata
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("imports.id")
    )

    # Relationships
    post: Mapped["SocialPost"] = relationship("SocialPost", back_populates="snapshots")
    creator: Mapped["Creator"] = relationship("Creator", back_populates="snapshots")
    import_record: Mapped["Import | None"] = relationship("Import")

    __table_args__ = (
        Index("idx_snapshots_post_time", "post_id", "snapshot_at"),
        Index("idx_snapshots_creator_time", "creator_id", "snapshot_at"),
    )
