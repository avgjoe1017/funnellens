"""Tracking link models for deterministic attribution."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class LinkPlatform(str, PyEnum):
    """Source platforms for tracking links."""

    tiktok = "tiktok"
    instagram = "instagram"
    twitter = "twitter"
    reddit = "reddit"
    youtube = "youtube"
    other = "other"


class TrackingLink(Base):
    """
    A trackable link that agencies use in their social media bios.

    Links are tagged with content type at creation for attribution.
    This is the KEY DIFFERENTIATOR - we know which content type
    the link promoted, enabling LTV analysis by content strategy.
    """

    __tablename__ = "tracking_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False
    )

    # The tracking code (e.g., "TT_STORY_JAN")
    code = Column(String(50), nullable=False)

    # Full URL: https://onlyfans.com/{username}?c={code}
    destination_url = Column(String(500), nullable=False)

    # Attribution metadata — THIS IS THE KEY DIFFERENTIATOR
    source_platform = Column(
        Enum(LinkPlatform, name="link_platform_enum", create_type=True),
        nullable=False,
    )
    content_type = Column(String(50), nullable=False)  # From taxonomy
    campaign = Column(String(100))  # Optional grouping (e.g., "JAN_WEEK1")

    # Aggregated metrics (updated nightly or on-demand)
    total_clicks = Column(Integer, default=0)  # Populated in v1.5 with redirect tracking
    total_subs = Column(Integer, default=0)
    total_revenue = Column(Float, default=0)
    conversion_rate = Column(Float)  # subs / clicks (when clicks available)
    avg_fan_ltv = Column(Float)

    # Lifecycle
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_sub_at = Column(DateTime)  # Most recent subscription via this link

    # Relationships
    creator = relationship("Creator", back_populates="tracking_links")
    fans = relationship("Fan", back_populates="tracking_link")
    clicks = relationship("LinkClick", back_populates="tracking_link")

    __table_args__ = (
        Index("idx_tracking_links_creator", "creator_id"),
        Index("idx_tracking_links_code", "code"),
        Index("idx_tracking_links_content_type", "content_type"),
        UniqueConstraint("creator_id", "code", name="uq_creator_link_code"),
    )

    def __repr__(self) -> str:
        return f"<TrackingLink {self.code} ({self.content_type})>"


class LinkClick(Base):
    """
    Individual click events. V1.5 feature — requires redirect tracking.

    For v1, this table exists but is unpopulated (subs matched by code only).
    """

    __tablename__ = "link_clicks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tracking_link_id = Column(
        UUID(as_uuid=True), ForeignKey("tracking_links.id"), nullable=False
    )

    # Click metadata
    clicked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Attribution (from redirect or JS pixel)
    referrer_url = Column(String(500))  # Where they came from
    user_agent = Column(String(500))
    device_type = Column(String(20))  # mobile, desktop, tablet
    country_code = Column(String(2))

    # Session tracking (for matching to subs)
    click_id = Column(String(64), unique=True)  # UUID for matching
    session_id = Column(String(64))  # Group multiple clicks from same session

    # Outcome (populated when matched to a subscription)
    converted_fan_id = Column(UUID(as_uuid=True), ForeignKey("fans.id"))
    converted_at = Column(DateTime)

    # Relationships
    tracking_link = relationship("TrackingLink", back_populates="clicks")

    __table_args__ = (
        Index("idx_link_clicks_link_time", "tracking_link_id", "clicked_at"),
        Index("idx_link_clicks_click_id", "click_id"),
    )

    def __repr__(self) -> str:
        return f"<LinkClick {self.click_id} at {self.clicked_at}>"
