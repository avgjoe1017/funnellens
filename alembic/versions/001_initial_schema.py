"""Initial schema with all core tables.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agencies table
    op.create_table(
        "agencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("subscription_tier", sa.String(20), nullable=True),
        sa.Column("subscription_status", sa.String(20), nullable=True),
        sa.Column("max_creators", sa.Integer(), nullable=False, default=10),
        sa.Column("fan_id_salt", sa.String(64), nullable=False),
        sa.Column("settings", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("notification_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_agencies_slug", "agencies", ["slug"])

    # Team members table
    op.create_table(
        "team_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agency_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_team_members_agency", "team_members", ["agency_id"])
    op.create_index("idx_team_members_email", "team_members", ["email"])

    # Creators table
    op.create_table(
        "creators",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agency_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tiktok_handle", sa.String(100), nullable=True),
        sa.Column("instagram_handle", sa.String(100), nullable=True),
        sa.Column("of_account_id", sa.String(100), nullable=True),
        sa.Column("baseline_subs_per_day", sa.Float(), nullable=True),
        sa.Column("baseline_rev_per_day", sa.Float(), nullable=True),
        sa.Column("baseline_subs_per_1k_delta_views", sa.Float(), nullable=True),
        sa.Column("baseline_updated_at", sa.DateTime(), nullable=True),
        sa.Column("optimal_attribution_window_hours", sa.Integer(), default=48),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_creators_agency", "creators", ["agency_id"])
    op.create_index("idx_creators_status", "creators", ["status"])

    # Imports table (needed before social_posts for FK)
    op.create_table(
        "imports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agency_id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=True),
        sa.Column("import_type", sa.String(20), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=True),
        sa.Column("rows_imported", sa.Integer(), nullable=True),
        sa.Column("rows_skipped", sa.Integer(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("errors", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_imports_agency", "imports", ["agency_id"])
    op.create_index("idx_imports_creator", "imports", ["creator_id"])
    op.create_index("idx_imports_file_hash", "imports", ["file_hash"])

    # Social posts table
    op.create_table(
        "social_posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_post_id", sa.String(100), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
        sa.Column("views_cumulative", sa.Integer(), default=0),
        sa.Column("likes_cumulative", sa.Integer(), default=0),
        sa.Column("comments_cumulative", sa.Integer(), default=0),
        sa.Column("shares_cumulative", sa.Integer(), default=0),
        sa.Column("saves_cumulative", sa.Integer(), default=0),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("caption_embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("video_duration_seconds", sa.Float(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("content_type_confidence", sa.Float(), nullable=True),
        sa.Column("content_type_source", sa.String(20), nullable=True),
        sa.Column("campaign_tag", sa.String(100), nullable=True),
        sa.Column("attributed_subs", sa.Integer(), nullable=True),
        sa.Column("attributed_revenue", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_snapshot_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_posts_creator_posted", "social_posts", ["creator_id", "posted_at"])
    op.create_index("idx_posts_content_type", "social_posts", ["content_type"])
    op.create_index(
        "idx_posts_platform_id",
        "social_posts",
        ["platform", "platform_post_id"],
        unique=True,
        postgresql_where=sa.text("platform_post_id IS NOT NULL"),
    )

    # Post snapshots table
    op.create_table(
        "post_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("views", sa.Integer(), default=0),
        sa.Column("likes", sa.Integer(), default=0),
        sa.Column("comments", sa.Integer(), default=0),
        sa.Column("shares", sa.Integer(), default=0),
        sa.Column("saves", sa.Integer(), default=0),
        sa.Column("import_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_snapshots_post_time", "post_snapshots", ["post_id", "snapshot_at"])
    op.create_index("idx_snapshots_creator_time", "post_snapshots", ["creator_id", "snapshot_at"])

    # Fans table
    op.create_table(
        "fans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("external_id_hash", sa.String(64), nullable=True),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("referral_link_id", sa.UUID(), nullable=True),
        sa.Column("attributed_content_type", sa.String(50), nullable=True),
        sa.Column("attribution_method", sa.String(20), nullable=True),
        sa.Column("attribution_confidence", sa.Float(), nullable=True),
        sa.Column("attribution_weights", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("churned_at", sa.DateTime(), nullable=True),
        sa.Column("ltv_30d", sa.Float(), nullable=True),
        sa.Column("ltv_90d", sa.Float(), nullable=True),
        sa.Column("total_spend", sa.Float(), default=0),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fans_creator", "fans", ["creator_id"])
    op.create_index("idx_fans_acquired", "fans", ["acquired_at"])
    op.create_index("idx_fans_content_type", "fans", ["attributed_content_type"])

    # Revenue events table
    op.create_table(
        "revenue_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("fan_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["fan_id"], ["fans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_revenue_fan", "revenue_events", ["fan_id"])
    op.create_index("idx_revenue_event_at", "revenue_events", ["event_at"])

    # Confounder events table
    op.create_table(
        "confounder_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("event_start", sa.DateTime(), nullable=False),
        sa.Column("event_end", sa.DateTime(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("estimated_impact", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_confounders_creator_time", "confounder_events", ["creator_id", "event_start"])


def downgrade() -> None:
    op.drop_table("confounder_events")
    op.drop_table("revenue_events")
    op.drop_table("fans")
    op.drop_table("post_snapshots")
    op.drop_table("social_posts")
    op.drop_table("imports")
    op.drop_table("creators")
    op.drop_table("team_members")
    op.drop_table("agencies")
