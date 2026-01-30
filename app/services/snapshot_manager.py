"""Snapshot manager - handles point-in-time snapshots and delta calculations.

This is the critical fix for the cumulative-views problem from v1.0.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PostSnapshot, SocialPost


class SnapshotManager:
    """
    Manages point-in-time snapshots and computes deltas.

    KEY INSIGHT: CSV exports give cumulative metrics. To know how many views
    a post got DURING a specific period, we need:

        delta_views = snapshot_2.views - snapshot_1.views

    This is the foundation for accurate attribution.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_snapshot(
        self,
        post_id: uuid.UUID,
        creator_id: uuid.UUID,
        metrics: dict[str, Any],
        snapshot_at: datetime,
        import_id: uuid.UUID | None = None,
    ) -> PostSnapshot:
        """
        Record a point-in-time snapshot of post metrics.
        Called during CSV import.
        """
        snapshot = PostSnapshot(
            post_id=post_id,
            creator_id=creator_id,
            snapshot_at=snapshot_at,
            views=metrics.get("views", 0),
            likes=metrics.get("likes", 0),
            comments=metrics.get("comments", 0),
            shares=metrics.get("shares", 0),
            saves=metrics.get("saves", 0),
            import_id=import_id,
        )
        self.db.add(snapshot)

        # Update post's cumulative values
        result = await self.db.execute(
            select(SocialPost).where(SocialPost.id == post_id)
        )
        post = result.scalar_one_or_none()

        if post:
            post.views_cumulative = metrics.get("views", post.views_cumulative)
            post.likes_cumulative = metrics.get("likes", post.likes_cumulative)
            post.comments_cumulative = metrics.get("comments", post.comments_cumulative)
            post.shares_cumulative = metrics.get("shares", post.shares_cumulative)
            post.saves_cumulative = metrics.get("saves", post.saves_cumulative)
            post.last_snapshot_at = snapshot_at

        return snapshot

    async def get_view_deltas(
        self,
        creator_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[uuid.UUID, dict[str, Any]]:
        """
        Compute view deltas for all posts during a period.

        Returns: {post_id: {"views_delta": int, "likes_delta": int, ...}}
        """
        # Get all posts for this creator
        posts_result = await self.db.execute(
            select(SocialPost).where(SocialPost.creator_id == creator_id)
        )
        posts = posts_result.scalars().all()

        deltas: dict[uuid.UUID, dict[str, Any]] = {}

        for post in posts:
            # Snapshot closest to (but before) period_start
            snap_start_result = await self.db.execute(
                select(PostSnapshot)
                .where(
                    PostSnapshot.post_id == post.id,
                    PostSnapshot.snapshot_at <= period_start,
                )
                .order_by(PostSnapshot.snapshot_at.desc())
                .limit(1)
            )
            snap_start = snap_start_result.scalar_one_or_none()

            # Snapshot closest to (but before) period_end
            snap_end_result = await self.db.execute(
                select(PostSnapshot)
                .where(
                    PostSnapshot.post_id == post.id,
                    PostSnapshot.snapshot_at <= period_end,
                )
                .order_by(PostSnapshot.snapshot_at.desc())
                .limit(1)
            )
            snap_end = snap_end_result.scalar_one_or_none()

            if snap_end:
                start_views = snap_start.views if snap_start else 0
                start_likes = snap_start.likes if snap_start else 0
                start_comments = snap_start.comments if snap_start else 0
                start_shares = snap_start.shares if snap_start else 0
                start_saves = snap_start.saves if snap_start else 0

                deltas[post.id] = {
                    "views_delta": max(0, snap_end.views - start_views),
                    "likes_delta": max(0, snap_end.likes - start_likes),
                    "comments_delta": max(0, snap_end.comments - start_comments),
                    "shares_delta": max(0, snap_end.shares - start_shares),
                    "saves_delta": max(0, snap_end.saves - start_saves),
                    "content_type": post.content_type,
                    "posted_at": post.posted_at,
                }

        return deltas

    async def get_content_type_deltas(
        self,
        creator_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, dict[str, Any]]:
        """
        Aggregate view deltas by content type for a period.

        Returns: {
            "storytime": {"views_delta": 45000, "posts_with_views": 8},
            "thirst_trap": {"views_delta": 120000, "posts_with_views": 12},
            ...
        }
        """
        post_deltas = await self.get_view_deltas(creator_id, period_start, period_end)

        by_type: dict[str, dict[str, Any]] = {}

        for post_id, delta in post_deltas.items():
            ct = delta.get("content_type") or "other"

            if ct not in by_type:
                by_type[ct] = {
                    "views_delta": 0,
                    "likes_delta": 0,
                    "comments_delta": 0,
                    "shares_delta": 0,
                    "saves_delta": 0,
                    "posts_with_views": 0,
                    "post_ids": [],
                }

            by_type[ct]["views_delta"] += delta["views_delta"]
            by_type[ct]["likes_delta"] += delta["likes_delta"]
            by_type[ct]["comments_delta"] += delta["comments_delta"]
            by_type[ct]["shares_delta"] += delta["shares_delta"]
            by_type[ct]["saves_delta"] += delta["saves_delta"]

            if delta["views_delta"] > 0:
                by_type[ct]["posts_with_views"] += 1
                by_type[ct]["post_ids"].append(post_id)

        return by_type

    async def get_latest_snapshot(
        self, post_id: uuid.UUID
    ) -> PostSnapshot | None:
        """Get the most recent snapshot for a post."""
        result = await self.db.execute(
            select(PostSnapshot)
            .where(PostSnapshot.post_id == post_id)
            .order_by(PostSnapshot.snapshot_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_snapshot_count(self, post_id: uuid.UUID) -> int:
        """Get the number of snapshots for a post."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(PostSnapshot.id)).where(PostSnapshot.post_id == post_id)
        )
        return result.scalar() or 0
