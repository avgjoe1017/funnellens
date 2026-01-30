"""Agency and team member models."""

import secrets
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.creator import Creator


class SubscriptionTier(str, Enum):
    """Agency subscription tiers."""

    STARTER = "starter"
    GROWTH = "growth"
    AGENCY = "agency"


class SubscriptionStatus(str, Enum):
    """Agency subscription status."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class TeamRole(str, Enum):
    """Team member roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


class Agency(Base):
    """Multi-tenant agency root entity."""

    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    subscription_tier: Mapped[str | None] = mapped_column(
        String(20), default=SubscriptionTier.STARTER.value
    )
    subscription_status: Mapped[str | None] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE.value
    )
    max_creators: Mapped[int] = mapped_column(default=10)

    # Privacy: per-agency salt for fan ID hashing
    fan_id_salt: Mapped[str] = mapped_column(
        String(64), default=lambda: secrets.token_hex(32)
    )

    settings: Mapped[dict | None] = mapped_column(JSON, default=dict)
    notification_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    creators: Mapped[list["Creator"]] = relationship(
        "Creator", back_populates="agency", cascade="all, delete-orphan"
    )
    team_members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="agency", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_agencies_slug", "slug"),)


class TeamMember(Base):
    """Team members within an agency."""

    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=TeamRole.VIEWER.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    agency: Mapped["Agency"] = relationship("Agency", back_populates="team_members")

    __table_args__ = (
        Index("idx_team_members_agency", "agency_id"),
        Index("idx_team_members_email", "email"),
    )
