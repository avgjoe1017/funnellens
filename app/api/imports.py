"""CSV import API endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.import_log import ImportType
from app.services.csv_importer import CsvImportError, CsvImporter

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])


class ImportResponse(BaseModel):
    """Response from CSV import."""

    id: str
    import_type: str
    file_name: str | None
    rows_total: int | None
    rows_imported: int | None
    rows_skipped: int | None
    snapshot_at: datetime
    errors: list[dict] | None

    class Config:
        from_attributes = True


@router.post("/social-posts", response_model=ImportResponse)
async def import_social_posts(
    file: Annotated[UploadFile, File(description="CSV file with social post data")],
    agency_id: Annotated[str, Form(description="Agency UUID")],
    creator_id: Annotated[str, Form(description="Creator UUID")],
    snapshot_at: Annotated[str | None, Form(description="When this data represents (ISO format)")] = None,
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    Import social posts from CSV and create snapshots.

    Required CSV columns:
    - platform: "tiktok" or "instagram"
    - post_id/video_id/id: Platform's post identifier
    - posted_at/post_date/date: When the post was created
    - views/view_count/plays: View count

    Optional columns:
    - likes, comments, shares, saves
    - caption, url, duration
    """
    try:
        agency_uuid = uuid.UUID(agency_id)
        creator_uuid = uuid.UUID(creator_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {e}")

    snapshot_datetime = None
    if snapshot_at:
        try:
            snapshot_datetime = datetime.fromisoformat(snapshot_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid snapshot_at format")

    content = await file.read()

    importer = CsvImporter(db)

    try:
        import_record = await importer.import_csv(
            file_content=content,
            file_name=file.filename or "unknown.csv",
            agency_id=agency_uuid,
            creator_id=creator_uuid,
            import_type=ImportType.SOCIAL_POSTS,
            snapshot_at=snapshot_datetime,
        )
    except CsvImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportResponse(
        id=str(import_record.id),
        import_type=import_record.import_type,
        file_name=import_record.file_name,
        rows_total=import_record.rows_total,
        rows_imported=import_record.rows_imported,
        rows_skipped=import_record.rows_skipped,
        snapshot_at=import_record.snapshot_at,
        errors=import_record.errors,
    )


@router.post("/fans", response_model=ImportResponse)
async def import_fans(
    file: Annotated[UploadFile, File(description="CSV file with fan/subscriber data")],
    agency_id: Annotated[str, Form(description="Agency UUID")],
    creator_id: Annotated[str, Form(description="Creator UUID")],
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    Import fan/subscriber data from CSV.

    Required CSV columns:
    - acquired_at/subscribed_at/date: When the fan subscribed

    Optional columns:
    - external_id/user_id/fan_id: Platform's user identifier (will be hashed)
    - churned_at/unsubscribed_at: When the fan unsubscribed
    """
    try:
        agency_uuid = uuid.UUID(agency_id)
        creator_uuid = uuid.UUID(creator_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {e}")

    content = await file.read()

    importer = CsvImporter(db)

    try:
        import_record = await importer.import_csv(
            file_content=content,
            file_name=file.filename or "unknown.csv",
            agency_id=agency_uuid,
            creator_id=creator_uuid,
            import_type=ImportType.FANS,
        )
    except CsvImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportResponse(
        id=str(import_record.id),
        import_type=import_record.import_type,
        file_name=import_record.file_name,
        rows_total=import_record.rows_total,
        rows_imported=import_record.rows_imported,
        rows_skipped=import_record.rows_skipped,
        snapshot_at=import_record.snapshot_at,
        errors=import_record.errors,
    )


@router.post("/revenue", response_model=ImportResponse)
async def import_revenue(
    file: Annotated[UploadFile, File(description="CSV file with revenue events")],
    agency_id: Annotated[str, Form(description="Agency UUID")],
    creator_id: Annotated[str, Form(description="Creator UUID")],
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    Import revenue events from CSV.

    Required CSV columns:
    - fan_id/user_id/subscriber_id: Fan identifier
    - amount/value/price: Revenue amount
    - event_at/date: When the event occurred

    Optional columns:
    - event_type/type: subscription, renewal, tip, ppv, message
    - currency: USD, EUR, etc.
    """
    try:
        agency_uuid = uuid.UUID(agency_id)
        creator_uuid = uuid.UUID(creator_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {e}")

    content = await file.read()

    importer = CsvImporter(db)

    try:
        import_record = await importer.import_csv(
            file_content=content,
            file_name=file.filename or "unknown.csv",
            agency_id=agency_uuid,
            creator_id=creator_uuid,
            import_type=ImportType.REVENUE,
        )
    except CsvImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportResponse(
        id=str(import_record.id),
        import_type=import_record.import_type,
        file_name=import_record.file_name,
        rows_total=import_record.rows_total,
        rows_imported=import_record.rows_imported,
        rows_skipped=import_record.rows_skipped,
        snapshot_at=import_record.snapshot_at,
        errors=import_record.errors,
    )
