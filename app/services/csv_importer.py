"""CSV import service - handles parsing, validation, and snapshot creation."""

import hashlib
import io
import uuid
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Creator, Fan, Import, RevenueEvent, SocialPost
from app.models.import_log import ImportType
from app.models.social_post import Platform
from app.services.snapshot_manager import SnapshotManager


class CsvImportError(Exception):
    """Error during CSV import."""

    pass


class CsvImporter:
    """
    Handles CSV imports with snapshot creation.

    Every import creates PostSnapshots for all posts, which enables
    accurate delta calculations for attribution.
    """

    # Required columns for each import type
    REQUIRED_COLUMNS = {
        ImportType.SOCIAL_POSTS: {
            "platform": ["platform"],
            "post_id": ["post_id", "video_id", "id"],
            "posted_at": ["posted_at", "post_date", "date", "created_at"],
            "views": ["views", "view_count", "plays"],
        },
        ImportType.FANS: {
            "acquired_at": ["acquired_at", "subscribed_at", "date", "created_at"],
        },
        ImportType.REVENUE: {
            "fan_id": ["fan_id", "user_id", "subscriber_id"],
            "amount": ["amount", "value", "price"],
            "event_at": ["event_at", "date", "created_at"],
        },
    }

    # Optional columns that we'll try to extract
    OPTIONAL_COLUMNS = {
        ImportType.SOCIAL_POSTS: {
            "likes": ["likes", "like_count", "hearts"],
            "comments": ["comments", "comment_count"],
            "shares": ["shares", "share_count"],
            "saves": ["saves", "save_count", "bookmarks"],
            "caption": ["caption", "description", "text"],
            "url": ["url", "link", "video_url"],
            "duration": ["duration", "video_duration", "length"],
        },
        ImportType.FANS: {
            "external_id": ["external_id", "user_id", "fan_id", "subscriber_id"],
            "churned_at": ["churned_at", "unsubscribed_at", "cancelled_at"],
        },
        ImportType.REVENUE: {
            "event_type": ["event_type", "type", "category"],
            "currency": ["currency"],
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.snapshot_manager = SnapshotManager(db)

    async def import_csv(
        self,
        file_content: bytes,
        file_name: str,
        agency_id: uuid.UUID,
        creator_id: uuid.UUID,
        import_type: ImportType,
        snapshot_at: datetime | None = None,
    ) -> Import:
        """
        Import a CSV file and create appropriate records.

        Args:
            file_content: Raw CSV bytes
            file_name: Original filename
            agency_id: Agency performing the import
            creator_id: Creator the data belongs to
            import_type: Type of data (social_posts, fans, revenue)
            snapshot_at: When this data represents (defaults to now)

        Returns:
            Import record with stats
        """
        snapshot_at = snapshot_at or datetime.utcnow()

        # Compute file hash for dedup
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Check for duplicate import
        existing = await self.db.execute(
            select(Import).where(Import.file_hash == file_hash)
        )
        if existing.scalar_one_or_none():
            raise CsvImportError(f"This file has already been imported (hash: {file_hash[:12]})")

        # Parse CSV
        try:
            df = pd.read_csv(io.BytesIO(file_content))
        except Exception as e:
            raise CsvImportError(f"Failed to parse CSV: {e}")

        # Map columns to standard names
        column_mapping = self._map_columns(df.columns.tolist(), import_type)

        # Create import record
        import_record = Import(
            agency_id=agency_id,
            creator_id=creator_id,
            import_type=import_type.value,
            file_name=file_name,
            file_hash=file_hash,
            rows_total=len(df),
            rows_imported=0,
            rows_skipped=0,
            snapshot_at=snapshot_at,
            errors=[],
        )
        self.db.add(import_record)
        await self.db.flush()  # Get the import ID

        # Process rows based on import type
        if import_type == ImportType.SOCIAL_POSTS:
            await self._import_social_posts(
                df, column_mapping, creator_id, import_record, snapshot_at
            )
        elif import_type == ImportType.FANS:
            await self._import_fans(
                df, column_mapping, creator_id, import_record, agency_id
            )
        elif import_type == ImportType.REVENUE:
            await self._import_revenue(
                df, column_mapping, creator_id, import_record
            )

        return import_record

    def _map_columns(
        self, columns: list[str], import_type: ImportType
    ) -> dict[str, str]:
        """Map CSV columns to standard field names."""
        columns_lower = {c.lower().strip(): c for c in columns}
        mapping = {}

        # Required columns
        for field, variants in self.REQUIRED_COLUMNS.get(import_type, {}).items():
            for variant in variants:
                if variant.lower() in columns_lower:
                    mapping[field] = columns_lower[variant.lower()]
                    break
            else:
                raise CsvImportError(
                    f"Missing required column: {field} (tried: {variants})"
                )

        # Optional columns
        for field, variants in self.OPTIONAL_COLUMNS.get(import_type, {}).items():
            for variant in variants:
                if variant.lower() in columns_lower:
                    mapping[field] = columns_lower[variant.lower()]
                    break

        return mapping

    async def _import_social_posts(
        self,
        df: pd.DataFrame,
        mapping: dict[str, str],
        creator_id: uuid.UUID,
        import_record: Import,
        snapshot_at: datetime,
    ) -> None:
        """Import social posts and create snapshots."""
        errors = []

        for idx, row in df.iterrows():
            try:
                platform_raw = str(row[mapping["platform"]]).lower().strip()
                platform = Platform.TIKTOK.value if "tiktok" in platform_raw else Platform.INSTAGRAM.value

                platform_post_id = str(row[mapping["post_id"]])
                posted_at = pd.to_datetime(row[mapping["posted_at"]])
                views = int(row[mapping["views"]])

                # Check if post exists
                existing = await self.db.execute(
                    select(SocialPost).where(
                        SocialPost.platform == platform,
                        SocialPost.platform_post_id == platform_post_id,
                    )
                )
                post = existing.scalar_one_or_none()

                if post is None:
                    # Create new post
                    post = SocialPost(
                        creator_id=creator_id,
                        platform=platform,
                        platform_post_id=platform_post_id,
                        posted_at=posted_at,
                        views_cumulative=views,
                        likes_cumulative=int(row.get(mapping.get("likes", ""), 0) or 0),
                        comments_cumulative=int(row.get(mapping.get("comments", ""), 0) or 0),
                        shares_cumulative=int(row.get(mapping.get("shares", ""), 0) or 0),
                        saves_cumulative=int(row.get(mapping.get("saves", ""), 0) or 0),
                        caption=str(row.get(mapping.get("caption", ""), "")) or None,
                        url=str(row.get(mapping.get("url", ""), "")) or None,
                    )
                    self.db.add(post)
                    await self.db.flush()

                # Create snapshot for this post (critical for delta tracking)
                metrics = {
                    "views": views,
                    "likes": int(row.get(mapping.get("likes", ""), 0) or 0),
                    "comments": int(row.get(mapping.get("comments", ""), 0) or 0),
                    "shares": int(row.get(mapping.get("shares", ""), 0) or 0),
                    "saves": int(row.get(mapping.get("saves", ""), 0) or 0),
                }

                await self.snapshot_manager.create_snapshot(
                    post_id=post.id,
                    creator_id=creator_id,
                    metrics=metrics,
                    snapshot_at=snapshot_at,
                    import_id=import_record.id,
                )

                import_record.rows_imported = (import_record.rows_imported or 0) + 1

            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
                import_record.rows_skipped = (import_record.rows_skipped or 0) + 1

        import_record.errors = errors

    async def _import_fans(
        self,
        df: pd.DataFrame,
        mapping: dict[str, str],
        creator_id: uuid.UUID,
        import_record: Import,
        agency_id: uuid.UUID,
    ) -> None:
        """Import fan/subscriber data."""
        from app.models import Agency

        # Get agency salt for hashing
        agency_result = await self.db.execute(
            select(Agency).where(Agency.id == agency_id)
        )
        agency = agency_result.scalar_one()

        errors = []

        for idx, row in df.iterrows():
            try:
                acquired_at = pd.to_datetime(row[mapping["acquired_at"]])

                # Hash external ID if provided
                external_id_hash = None
                if "external_id" in mapping and pd.notna(row.get(mapping["external_id"])):
                    external_id = str(row[mapping["external_id"]])
                    external_id_hash = hashlib.sha256(
                        (external_id + agency.fan_id_salt).encode()
                    ).hexdigest()

                fan = Fan(
                    creator_id=creator_id,
                    external_id_hash=external_id_hash,
                    acquired_at=acquired_at,
                )

                if "churned_at" in mapping and pd.notna(row.get(mapping["churned_at"])):
                    fan.churned_at = pd.to_datetime(row[mapping["churned_at"]])

                self.db.add(fan)
                import_record.rows_imported = (import_record.rows_imported or 0) + 1

            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
                import_record.rows_skipped = (import_record.rows_skipped or 0) + 1

        import_record.errors = errors

    async def _import_revenue(
        self,
        df: pd.DataFrame,
        mapping: dict[str, str],
        creator_id: uuid.UUID,
        import_record: Import,
    ) -> None:
        """Import revenue events."""
        errors = []

        for idx, row in df.iterrows():
            try:
                # Find the fan by external ID hash
                fan_external_id = str(row[mapping["fan_id"]])

                # For now, skip if we can't find the fan
                # TODO: Better fan matching logic
                fan_result = await self.db.execute(
                    select(Fan).where(
                        Fan.creator_id == creator_id,
                    ).limit(1)
                )
                fan = fan_result.scalar_one_or_none()

                if fan is None:
                    errors.append({"row": idx, "error": f"Fan not found: {fan_external_id}"})
                    import_record.rows_skipped = (import_record.rows_skipped or 0) + 1
                    continue

                event = RevenueEvent(
                    fan_id=fan.id,
                    event_type=str(row.get(mapping.get("event_type", ""), "subscription")),
                    amount=float(row[mapping["amount"]]),
                    currency=str(row.get(mapping.get("currency", ""), "USD")),
                    event_at=pd.to_datetime(row[mapping["event_at"]]),
                )

                # Update fan's total spend
                fan.total_spend = (fan.total_spend or 0) + event.amount

                self.db.add(event)
                import_record.rows_imported = (import_record.rows_imported or 0) + 1

            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
                import_record.rows_skipped = (import_record.rows_skipped or 0) + 1

        import_record.errors = errors
