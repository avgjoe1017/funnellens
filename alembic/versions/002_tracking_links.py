"""Add tracking links tables

Revision ID: 002_tracking_links
Revises: 001_initial_schema
Create Date: 2026-01-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_tracking_links"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create link platform enum
    link_platform_enum = postgresql.ENUM(
        "tiktok", "instagram", "twitter", "reddit", "youtube", "other",
        name="link_platform_enum",
        create_type=True
    )
    link_platform_enum.create(op.get_bind(), checkfirst=True)

    # Create tracking_links table
    op.create_table(
        "tracking_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("destination_url", sa.String(500), nullable=False),
        sa.Column(
            "source_platform",
            postgresql.ENUM(
                "tiktok", "instagram", "twitter", "reddit", "youtube", "other",
                name="link_platform_enum",
                create_type=False
            ),
            nullable=False
        ),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("campaign", sa.String(100), nullable=True),
        sa.Column("total_clicks", sa.Integer(), server_default="0"),
        sa.Column("total_subs", sa.Integer(), server_default="0"),
        sa.Column("total_revenue", sa.Float(), server_default="0"),
        sa.Column("conversion_rate", sa.Float(), nullable=True),
        sa.Column("avg_fan_ltv", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_sub_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "code", name="uq_creator_link_code"),
    )

    op.create_index("idx_tracking_links_creator", "tracking_links", ["creator_id"])
    op.create_index("idx_tracking_links_code", "tracking_links", ["code"])
    op.create_index("idx_tracking_links_content_type", "tracking_links", ["content_type"])

    # Create link_clicks table (for v1.5 - will be unpopulated initially)
    op.create_table(
        "link_clicks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tracking_link_id", sa.UUID(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("referrer_url", sa.String(500), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("click_id", sa.String(64), unique=True, nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("converted_fan_id", sa.UUID(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tracking_link_id"], ["tracking_links.id"]),
        sa.ForeignKeyConstraint(["converted_fan_id"], ["fans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_link_clicks_link_time", "link_clicks", ["tracking_link_id", "clicked_at"])
    op.create_index("idx_link_clicks_click_id", "link_clicks", ["click_id"])

    # Add tracking link columns to fans table
    op.add_column("fans", sa.Column("tracking_link_id", sa.UUID(), nullable=True))
    op.add_column("fans", sa.Column("tracking_link_code", sa.String(50), nullable=True))
    op.create_foreign_key(
        "fk_fans_tracking_link", "fans", "tracking_links",
        ["tracking_link_id"], ["id"]
    )
    op.create_index("idx_fans_tracking_link", "fans", ["tracking_link_id"])

    # Add of_username to creators for generating destination URLs
    op.add_column("creators", sa.Column("of_username", sa.String(100), nullable=True))


def downgrade() -> None:
    # Remove of_username from creators
    op.drop_column("creators", "of_username")

    # Remove tracking link columns from fans
    op.drop_index("idx_fans_tracking_link", "fans")
    op.drop_constraint("fk_fans_tracking_link", "fans", type_="foreignkey")
    op.drop_column("fans", "tracking_link_code")
    op.drop_column("fans", "tracking_link_id")

    # Drop link_clicks table
    op.drop_index("idx_link_clicks_click_id", "link_clicks")
    op.drop_index("idx_link_clicks_link_time", "link_clicks")
    op.drop_table("link_clicks")

    # Drop tracking_links table
    op.drop_index("idx_tracking_links_content_type", "tracking_links")
    op.drop_index("idx_tracking_links_code", "tracking_links")
    op.drop_index("idx_tracking_links_creator", "tracking_links")
    op.drop_table("tracking_links")

    # Drop enum
    op.execute("DROP TYPE IF EXISTS link_platform_enum")
