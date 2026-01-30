"""Seed script to populate dev database with sample data."""

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, engine, Base
from app.models import (
    Agency,
    Creator,
    SocialPost,
    PostSnapshot,
    Fan,
    ConfounderEvent,
)
from app.models.social_post import Platform
from app.models.confounder import ConfounderType, ImpactLevel


async def seed_database():
    """Seed the database with sample data for development."""

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        # Check if we already have data
        existing = await db.execute(select(Agency).limit(1))
        if existing.scalar_one_or_none():
            print("Database already has data. Skipping seed.")
            return

        print("Seeding database with sample data...")

        # Create sample agency
        agency = Agency(
            id=uuid.uuid4(),
            name="Demo Agency",
            slug="demo-agency",
            subscription_tier="growth",
            subscription_status="active",
            max_creators=10,
            fan_id_salt=secrets.token_hex(32),
            notification_email="demo@funnellens.com",
        )
        db.add(agency)
        await db.flush()
        print(f"Created agency: {agency.name} (ID: {agency.id})")

        # Create sample creator
        creator = Creator(
            id=uuid.uuid4(),
            agency_id=agency.id,
            name="Sarah Content",
            tiktok_handle="@sarahcontent",
            instagram_handle="@sarahcontent",
            of_account_id="sarahcontent",
            baseline_subs_per_day=15.0,
            baseline_rev_per_day=300.0,
            baseline_subs_per_1k_delta_views=0.5,
            status="active",
        )
        db.add(creator)
        await db.flush()
        print(f"Created creator: {creator.name} (ID: {creator.id})")

        # Create sample posts with multiple snapshots
        content_types = ["storytime", "grwm", "thirst_trap", "behind_scenes", "money_talk"]
        now = datetime.utcnow()

        for i in range(20):
            posted_at = now - timedelta(days=30 - i)
            content_type = content_types[i % len(content_types)]

            post = SocialPost(
                id=uuid.uuid4(),
                creator_id=creator.id,
                platform=Platform.TIKTOK.value,
                platform_post_id=f"tiktok_{i:04d}",
                posted_at=posted_at,
                views_cumulative=50000 + (i * 10000),
                likes_cumulative=2000 + (i * 500),
                comments_cumulative=100 + (i * 20),
                shares_cumulative=50 + (i * 10),
                saves_cumulative=200 + (i * 30),
                caption=f"Sample {content_type} post #{i+1}",
                content_type=content_type,
                content_type_source="user_confirmed",
            )
            db.add(post)
            await db.flush()

            # Create multiple snapshots for each post (simulating weekly imports)
            for week in range(4):
                snapshot_at = posted_at + timedelta(days=week * 7)
                if snapshot_at > now:
                    break

                # Views grow over time
                growth_factor = 1 + (week * 0.3)

                snapshot = PostSnapshot(
                    post_id=post.id,
                    creator_id=creator.id,
                    snapshot_at=snapshot_at,
                    views=int(post.views_cumulative * (0.3 + growth_factor * 0.2)),
                    likes=int(post.likes_cumulative * (0.3 + growth_factor * 0.2)),
                    comments=int(post.comments_cumulative * (0.3 + growth_factor * 0.2)),
                    shares=int(post.shares_cumulative * (0.3 + growth_factor * 0.2)),
                    saves=int(post.saves_cumulative * (0.3 + growth_factor * 0.2)),
                )
                db.add(snapshot)

        print(f"Created 20 sample posts with snapshots")

        # Create sample fans
        for i in range(50):
            acquired_at = now - timedelta(days=30 - (i % 30))
            content_type = content_types[i % len(content_types)]

            fan = Fan(
                creator_id=creator.id,
                external_id_hash=secrets.token_hex(32),
                acquired_at=acquired_at,
                attributed_content_type=content_type,
                attribution_method="weighted_window",
                attribution_confidence=0.6 + (i % 4) * 0.1,
                attribution_weights={content_type: 0.7, "other": 0.3},
                total_spend=10.0 + (i * 2),
            )
            db.add(fan)

        print(f"Created 50 sample fans")

        # Create sample confounder event
        confounder = ConfounderEvent(
            creator_id=creator.id,
            event_type=ConfounderType.PROMOTION.value,
            event_start=now - timedelta(days=7),
            event_end=now - timedelta(days=5),
            description="50% off sale week",
            estimated_impact=ImpactLevel.HIGH.value,
        )
        db.add(confounder)
        print(f"Created sample confounder event")

        await db.commit()
        print("\nDatabase seeded successfully!")
        print(f"\nUse these IDs for testing:")
        print(f"  Agency ID:  {agency.id}")
        print(f"  Creator ID: {creator.id}")


if __name__ == "__main__":
    asyncio.run(seed_database())
