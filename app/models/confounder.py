"""Confounder event model - tracks events that could skew attribution."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.creator import Creator


class ConfounderType(str, Enum):
    """Types of events that can confound attribution."""

    PRICE_CHANGE = "price_change"
    PROMOTION = "promotion"
    COLLAB = "collab"
    EXTERNAL_TRAFFIC = "external_traffic"
    MASS_DM = "mass_dm"
    OF_PROMO = "of_promo"
    OTHER = "other"


class ImpactLevel(str, Enum):
    """Estimated impact of confounder event."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfounderEvent(Base):
    """
    Events that could confound attribution analysis.

    When these overlap with content pushes, recommendations are flagged
    with reduced confidence.
    """

    __tablename__ = "confounder_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)

    event_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event_end: Mapped[datetime | None] = mapped_column(DateTime)
    description: Mapped[str | None] = mapped_column(String(500))
    estimated_impact: Mapped[str | None] = mapped_column(String(10))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    creator: Mapped["Creator"] = relationship(
        "Creator", back_populates="confounder_events"
    )

    __table_args__ = (
        Index("idx_confounders_creator_time", "creator_id", "event_start"),
    )
