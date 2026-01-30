"""Import tracking model - each CSV import is a discrete event."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agency import Agency
    from app.models.creator import Creator


class ImportType(str, Enum):
    """Types of data that can be imported."""

    SOCIAL_POSTS = "social_posts"
    FANS = "fans"
    REVENUE = "revenue"


class Import(Base):
    """Track each CSV import as a discrete snapshot event."""

    __tablename__ = "imports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id"), nullable=False
    )
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id")
    )
    import_type: Mapped[str] = mapped_column(String(20), nullable=False)

    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64))  # SHA256 for dedup
    rows_total: Mapped[int | None] = mapped_column(Integer)
    rows_imported: Mapped[int | None] = mapped_column(Integer)
    rows_skipped: Mapped[int | None] = mapped_column(Integer)

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )  # When this data represents
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    errors: Mapped[list | None] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("idx_imports_agency", "agency_id"),
        Index("idx_imports_creator", "creator_id"),
        Index("idx_imports_file_hash", "file_hash"),
    )
