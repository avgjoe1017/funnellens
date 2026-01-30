# FunnelLens Technical Specification v1.1
**Revised with stress-test fixes — Ready for implementation**

---

## Critical Changes from v1.0

| Issue | Problem | Fix |
|-------|---------|-----|
| View deltas | Cumulative views ≠ window views; breaks subs/1K metric | Snapshot-based delta tracking |
| Baseline contamination | Baseline included push period | Baseline ends at window_start |
| Window truncation | Integer days → 0 for <24h windows | Use hours with minimums |
| Confidence backwards | Based on post count, not sub count | Based on event counts + thresholds |
| Reach bias | High-view content steals attribution | Weighted credit split |
| Confounders | Promos/collabs create false lift | Confounder event log |
| Output certainty | All recommendations look equal | Two-tier: Confident vs Hypothesis |

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Data Models](#data-models)
3. [Snapshot & Delta System](#snapshot--delta-system)
4. [Attribution Service (Revised)](#attribution-service-revised)
5. [Confidence Framework](#confidence-framework)
6. [Recommendation Engine](#recommendation-engine)
7. [Backend Services](#backend-services)
8. [ML Pipeline](#ml-pipeline)
9. [Frontend Application](#frontend-application)
10. [Open Source Toolkit](#open-source-toolkit)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Next.js    │  │  React      │  │  TanStack   │  │  Tremor             │ │
│  │  App Router │  │  Components │  │  Query      │  │  Visualizations     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               API LAYER                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         FastAPI + Pydantic                              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Snapshot   │  │  Delta      │  │  Attribution│  │  Confidence         │ │
│  │  Manager    │  │  Calculator │  │  Engine     │  │  Scorer             │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  PostgreSQL │  │  TimescaleDB│  │  Redis      │  │  S3/R2              │ │
│  │  (Primary)  │  │  (Snapshots)│  │  (Cache)    │  │  (CSV Archive)      │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### Core Schema (PostgreSQL + SQLAlchemy)

```python
# models/core.py
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum, JSON, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import uuid
import hashlib
import secrets
from datetime import datetime

class Agency(Base):
    __tablename__ = "agencies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    subscription_tier = Column(Enum("starter", "growth", "agency", name="tier_enum"))
    subscription_status = Column(Enum("active", "past_due", "cancelled", name="status_enum"))
    max_creators = Column(Integer, default=10)
    
    # Privacy: per-agency salt for fan ID hashing
    fan_id_salt = Column(String(64), default=lambda: secrets.token_hex(32))
    
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    creators = relationship("Creator", back_populates="agency")
    team_members = relationship("TeamMember", back_populates="agency")


class Creator(Base):
    __tablename__ = "creators"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id = Column(UUID(as_uuid=True), ForeignKey("agencies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    tiktok_handle = Column(String(100))
    instagram_handle = Column(String(100))
    of_account_id = Column(String(100))
    
    # Baselines (computed from pre-window periods)
    baseline_subs_per_day = Column(Float)
    baseline_rev_per_day = Column(Float)
    baseline_subs_per_1k_delta_views = Column(Float)  # NEW: uses delta views
    baseline_updated_at = Column(DateTime)
    
    # Calibration metadata
    optimal_attribution_window_hours = Column(Integer, default=48)  # Learned per-creator
    
    status = Column(Enum("active", "paused", "archived", name="creator_status"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    agency = relationship("Agency", back_populates="creators")
    posts = relationship("SocialPost", back_populates="creator")
    fans = relationship("Fan", back_populates="creator")
    snapshots = relationship("PostSnapshot", back_populates="creator")
    confounder_events = relationship("ConfounderEvent", back_populates="creator")


class SocialPost(Base):
    """
    Represents a social media post. Metrics here are CUMULATIVE (latest known values).
    For period-specific metrics, use PostSnapshot deltas.
    """
    __tablename__ = "social_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    platform = Column(Enum("tiktok", "instagram", name="platform_enum"), nullable=False)
    platform_post_id = Column(String(100))
    posted_at = Column(DateTime, nullable=False)
    
    # CUMULATIVE metrics (latest snapshot)
    views_cumulative = Column(Integer, default=0)
    likes_cumulative = Column(Integer, default=0)
    comments_cumulative = Column(Integer, default=0)
    shares_cumulative = Column(Integer, default=0)
    saves_cumulative = Column(Integer, default=0)
    
    # Content metadata
    caption = Column(Text)
    caption_embedding = Column(ARRAY(Float))
    video_duration_seconds = Column(Float)
    url = Column(String(500))
    
    # Classification
    content_type = Column(String(50))
    content_type_confidence = Column(Float)
    content_type_source = Column(Enum("ml_suggested", "user_confirmed", "user_override", name="tag_source"))
    campaign_tag = Column(String(100))
    
    # Attribution (computed from deltas)
    attributed_subs = Column(Integer)
    attributed_revenue = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_snapshot_at = Column(DateTime)
    
    creator = relationship("Creator", back_populates="posts")
    snapshots = relationship("PostSnapshot", back_populates="post")

    __table_args__ = (
        Index("idx_posts_creator_posted", "creator_id", "posted_at"),
        Index("idx_posts_content_type", "content_type"),
        Index("idx_posts_platform_id", "platform", "platform_post_id", unique=True),
    )


class PostSnapshot(Base):
    """
    CRITICAL: Point-in-time snapshot of post metrics.
    Deltas between snapshots give us views/engagement DURING a specific period.
    This fixes the cumulative-views attribution problem.
    """
    __tablename__ = "post_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("social_posts.id"), nullable=False)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Cumulative values at this snapshot
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    
    # Import metadata
    import_id = Column(UUID(as_uuid=True), ForeignKey("imports.id"))
    
    post = relationship("SocialPost", back_populates="snapshots")
    creator = relationship("Creator", back_populates="snapshots")

    __table_args__ = (
        Index("idx_snapshots_post_time", "post_id", "snapshot_at"),
        Index("idx_snapshots_creator_time", "creator_id", "snapshot_at"),
    )


class ConfounderEvent(Base):
    """
    NEW: Track events that could confound attribution.
    When these overlap with content pushes, recommendations are flagged.
    """
    __tablename__ = "confounder_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    event_type = Column(Enum(
        "price_change",      # Sub price changed
        "promotion",         # Sale, discount, free trial
        "collab",           # Shoutout from another creator
        "external_traffic", # Reddit, Twitter, news coverage
        "mass_dm",          # DM campaign
        "of_promo",         # OnlyFans platform promotion
        "other",
        name="confounder_type"
    ), nullable=False)
    
    event_start = Column(DateTime, nullable=False)
    event_end = Column(DateTime)  # Nullable for point-in-time events
    description = Column(String(500))
    estimated_impact = Column(Enum("low", "medium", "high", name="impact_level"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    creator = relationship("Creator", back_populates="confounder_events")

    __table_args__ = (
        Index("idx_confounders_creator_time", "creator_id", "event_start"),
    )


class Fan(Base):
    __tablename__ = "fans"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    
    # FIXED: Salted hash for privacy (per-agency salt)
    external_id_hash = Column(String(64))
    
    acquired_at = Column(DateTime, nullable=False)
    referral_link_id = Column(UUID(as_uuid=True), ForeignKey("referral_links.id"))
    
    # Attribution
    attributed_content_type = Column(String(50))
    attribution_method = Column(Enum(
        "referral_link",    # Deterministic via link
        "weighted_window",  # Probabilistic with credit split
        "campaign",         # Via campaign tag
        name="attribution_method"
    ))
    attribution_confidence = Column(Float)
    
    # NEW: Weighted attribution (for multi-content-type credit)
    attribution_weights = Column(JSON)  # {"storytime": 0.6, "grwm": 0.4}
    
    # Lifecycle
    churned_at = Column(DateTime)
    ltv_30d = Column(Float)
    ltv_90d = Column(Float)
    total_spend = Column(Float, default=0)
    
    creator = relationship("Creator", back_populates="fans")


class RevenueEvent(Base):
    __tablename__ = "revenue_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fan_id = Column(UUID(as_uuid=True), ForeignKey("fans.id"), nullable=False)
    event_type = Column(Enum("subscription", "renewal", "tip", "ppv", "message", name="event_type"))
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    event_at = Column(DateTime, nullable=False)


class Import(Base):
    """Track each CSV import as a discrete snapshot event."""
    __tablename__ = "imports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id = Column(UUID(as_uuid=True), ForeignKey("agencies.id"), nullable=False)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    import_type = Column(Enum("social_posts", "fans", "revenue", name="import_type"))
    
    file_name = Column(String(255))
    file_hash = Column(String(64))  # SHA256 for dedup
    rows_total = Column(Integer)
    rows_imported = Column(Integer)
    rows_skipped = Column(Integer)
    
    snapshot_at = Column(DateTime, default=datetime.utcnow)  # When this data represents
    imported_at = Column(DateTime, default=datetime.utcnow)
    
    errors = Column(JSON, default=[])
```

### Content Type Taxonomy

```python
# models/taxonomy.py
from enum import Enum

class ContentType(str, Enum):
    STORYTIME = "storytime"
    GRWM = "grwm"
    THIRST_TRAP = "thirst_trap"
    BEHIND_SCENES = "behind_scenes"
    MONEY_TALK = "money_talk"
    OTHER = "other"

DEFAULT_TAXONOMY = {
    "storytime": {
        "label": "Storytime",
        "description": "Work stories, client stories, life narratives",
        "keywords": ["story", "happened", "client", "work", "crazy", "told", "said", "omg"],
        "hotkey": "1"
    },
    "grwm": {
        "label": "GRWM / Talk to Camera",
        "description": "Get ready with me, direct address, conversational",
        "keywords": ["grwm", "get ready", "chat", "talk", "honest", "real talk", "rant"],
        "hotkey": "2"
    },
    "thirst_trap": {
        "label": "Thirst Trap",
        "description": "Aesthetic-focused, minimal narrative, visual appeal",
        "keywords": ["outfit", "fit check", "look", "vibe", "💅", "🔥"],
        "hotkey": "3"
    },
    "behind_scenes": {
        "label": "Behind the Scenes",
        "description": "Day in life, club vlogs, BTS content",
        "keywords": ["vlog", "day in", "bts", "behind", "come with", "pov", "routine"],
        "hotkey": "4"
    },
    "money_talk": {
        "label": "Money / Income",
        "description": "Earnings breakdowns, income proof, money motivation",
        "keywords": ["made", "earned", "income", "money", "$$", "k this", "profit", "bag"],
        "hotkey": "5"
    },
    "other": {
        "label": "Other",
        "description": "Doesn't fit other categories",
        "keywords": [],
        "hotkey": "6"
    }
}
```

---

## Snapshot & Delta System

This is the critical fix for the cumulative-views problem.

```python
# app/services/snapshot_manager.py
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy import func

class SnapshotManager:
    """
    Manages point-in-time snapshots and computes deltas.
    
    KEY INSIGHT: CSV exports give cumulative metrics. To know how many views
    a post got DURING a specific period, we need:
    
        delta_views = snapshot_2.views - snapshot_1.views
    
    This is the foundation for accurate attribution.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_snapshot(
        self,
        post_id: UUID,
        metrics: Dict,
        snapshot_at: datetime,
        import_id: UUID
    ) -> PostSnapshot:
        """
        Record a point-in-time snapshot of post metrics.
        Called during CSV import.
        """
        snapshot = PostSnapshot(
            post_id=post_id,
            creator_id=metrics.get("creator_id"),
            snapshot_at=snapshot_at,
            views=metrics.get("views", 0),
            likes=metrics.get("likes", 0),
            comments=metrics.get("comments", 0),
            shares=metrics.get("shares", 0),
            saves=metrics.get("saves", 0),
            import_id=import_id
        )
        self.db.add(snapshot)
        
        # Update post's cumulative values
        post = self.db.query(SocialPost).get(post_id)
        if post:
            post.views_cumulative = metrics.get("views", post.views_cumulative)
            post.likes_cumulative = metrics.get("likes", post.likes_cumulative)
            post.last_snapshot_at = snapshot_at
        
        return snapshot
    
    def get_view_deltas(
        self,
        creator_id: UUID,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[UUID, Dict]:
        """
        Compute view deltas for all posts during a period.
        
        Returns: {post_id: {"views_delta": int, "likes_delta": int, ...}}
        """
        # Get snapshots at start and end of period
        # Use closest snapshot before period_start and closest before period_end
        
        posts = self.db.query(SocialPost).filter(
            SocialPost.creator_id == creator_id
        ).all()
        
        deltas = {}
        
        for post in posts:
            # Snapshot closest to (but before) period_start
            snap_start = self.db.query(PostSnapshot).filter(
                PostSnapshot.post_id == post.id,
                PostSnapshot.snapshot_at <= period_start
            ).order_by(PostSnapshot.snapshot_at.desc()).first()
            
            # Snapshot closest to (but before) period_end
            snap_end = self.db.query(PostSnapshot).filter(
                PostSnapshot.post_id == post.id,
                PostSnapshot.snapshot_at <= period_end
            ).order_by(PostSnapshot.snapshot_at.desc()).first()
            
            if snap_end:
                start_views = snap_start.views if snap_start else 0
                start_likes = snap_start.likes if snap_start else 0
                
                deltas[post.id] = {
                    "views_delta": max(0, snap_end.views - start_views),
                    "likes_delta": max(0, snap_end.likes - start_likes),
                    "comments_delta": max(0, snap_end.comments - (snap_start.comments if snap_start else 0)),
                    "shares_delta": max(0, snap_end.shares - (snap_start.shares if snap_start else 0)),
                    "content_type": post.content_type,
                    "posted_at": post.posted_at
                }
        
        return deltas
    
    def get_content_type_deltas(
        self,
        creator_id: UUID,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, Dict]:
        """
        Aggregate view deltas by content type for a period.
        
        Returns: {
            "storytime": {"views_delta": 45000, "posts_with_views": 8},
            "thirst_trap": {"views_delta": 120000, "posts_with_views": 12},
            ...
        }
        """
        post_deltas = self.get_view_deltas(creator_id, period_start, period_end)
        
        by_type = {}
        
        for post_id, delta in post_deltas.items():
            ct = delta.get("content_type") or "other"
            
            if ct not in by_type:
                by_type[ct] = {
                    "views_delta": 0,
                    "likes_delta": 0,
                    "posts_with_views": 0,
                    "post_ids": []
                }
            
            by_type[ct]["views_delta"] += delta["views_delta"]
            by_type[ct]["likes_delta"] += delta["likes_delta"]
            
            if delta["views_delta"] > 0:
                by_type[ct]["posts_with_views"] += 1
                by_type[ct]["post_ids"].append(post_id)
        
        return by_type
```

---

## Attribution Service (Revised)

Key fixes: baseline ends at window_start, uses hours not days, weighted credit split.

```python
# app/services/attribution.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import stats

class AttributionService:
    """
    Cohort-based incrementality attribution with:
    - Delta-based view tracking (not cumulative)
    - Baseline computed BEFORE window (not contaminated)
    - Weighted credit split across content types
    - Confounder awareness
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.snapshot_mgr = SnapshotManager(db)
        self.confidence_scorer = ConfidenceScorer()
    
    def calculate_baseline(
        self,
        creator_id: UUID,
        baseline_end: datetime,  # FIXED: explicit end point
        lookback_days: int = 14
    ) -> Dict[str, float]:
        """
        Calculate rolling baseline metrics for a creator.
        
        CRITICAL FIX: Baseline window ends at baseline_end (typically window_start),
        not at "now minus exclude_days". This prevents baseline contamination.
        """
        baseline_start = baseline_end - timedelta(days=lookback_days)
        
        # Get daily metrics from baseline period
        metrics = self.db.query(DailyCreatorMetrics).filter(
            DailyCreatorMetrics.creator_id == creator_id,
            DailyCreatorMetrics.date >= baseline_start,
            DailyCreatorMetrics.date < baseline_end  # Strictly before window
        ).all()
        
        if not metrics or len(metrics) < 3:
            # Insufficient data - return conservative defaults
            return {
                "subs_per_day": 5.0,
                "rev_per_day": 100.0,
                "subs_per_1k_delta_views": 0.2,
                "data_days": len(metrics) if metrics else 0,
                "is_default": True
            }
        
        total_subs = sum(m.new_subs or 0 for m in metrics)
        total_revenue = sum(m.revenue or 0 for m in metrics)
        total_delta_views = sum(m.total_views or 0 for m in metrics)  # These should be deltas
        
        days = len(metrics)
        views_k = total_delta_views / 1000 if total_delta_views > 0 else 1
        
        return {
            "subs_per_day": total_subs / days,
            "rev_per_day": total_revenue / days,
            "subs_per_1k_delta_views": total_subs / views_k,
            "data_days": days,
            "is_default": False,
            
            # For day-of-week adjustment
            "dow_factors": self._compute_dow_factors(metrics)
        }
    
    def _compute_dow_factors(self, metrics: List) -> Dict[int, float]:
        """Compute day-of-week adjustment factors."""
        by_dow = {}
        for m in metrics:
            dow = m.date.weekday()
            if dow not in by_dow:
                by_dow[dow] = []
            by_dow[dow].append(m.new_subs or 0)
        
        overall_avg = np.mean([m.new_subs or 0 for m in metrics])
        if overall_avg == 0:
            return {i: 1.0 for i in range(7)}
        
        factors = {}
        for dow in range(7):
            if dow in by_dow and by_dow[dow]:
                factors[dow] = np.mean(by_dow[dow]) / overall_avg
            else:
                factors[dow] = 1.0
        
        return factors
    
    def attribute_window(
        self,
        creator_id: UUID,
        window_start: datetime,
        window_end: datetime,
        content_type_filter: Optional[str] = None
    ) -> Dict:
        """
        Compute attribution for a time window using delta views.
        
        FIXES APPLIED:
        1. Baseline ends at window_start (not contaminated)
        2. Uses hours for window duration (not truncated days)
        3. Returns weighted credit split
        4. Checks for confounders
        """
        # FIXED: Baseline computed relative to window_start
        baseline = self.calculate_baseline(
            creator_id,
            baseline_end=window_start,
            lookback_days=14
        )
        
        # FIXED: Use hours, not truncated days
        window_hours = (window_end - window_start).total_seconds() / 3600
        window_hours = max(window_hours, 1)  # Minimum 1 hour
        window_days = window_hours / 24
        
        # Get actual subs during window
        actual_subs = self.db.query(func.count(Fan.id)).filter(
            Fan.creator_id == creator_id,
            Fan.acquired_at >= window_start,
            Fan.acquired_at < window_end
        ).scalar() or 0
        
        actual_revenue = self.db.query(func.sum(RevenueEvent.amount)).join(Fan).filter(
            Fan.creator_id == creator_id,
            RevenueEvent.event_at >= window_start,
            RevenueEvent.event_at < window_end
        ).scalar() or 0
        
        # Day-of-week adjusted expected values
        expected_subs = self._compute_dow_adjusted_expected(
            baseline, window_start, window_end
        )
        expected_revenue = baseline["rev_per_day"] * window_days
        
        # Get view deltas by content type
        content_type_deltas = self.snapshot_mgr.get_content_type_deltas(
            creator_id, window_start, window_end
        )
        
        # Filter if requested
        if content_type_filter:
            content_type_deltas = {
                k: v for k, v in content_type_deltas.items()
                if k == content_type_filter
            }
        
        # Compute weighted credit split
        total_delta_views = sum(ct["views_delta"] for ct in content_type_deltas.values())
        credit_weights = {}
        
        if total_delta_views > 0:
            for ct, data in content_type_deltas.items():
                credit_weights[ct] = data["views_delta"] / total_delta_views
        
        # Check for confounders
        confounders = self._check_confounders(creator_id, window_start, window_end)
        
        # Compute lifts
        subs_lift = ((actual_subs / expected_subs) - 1) * 100 if expected_subs > 0 else 0
        revenue_lift = ((actual_revenue / expected_revenue) - 1) * 100 if expected_revenue > 0 else 0
        
        # Compute confidence
        confidence = self.confidence_scorer.score(
            actual_events=actual_subs,
            expected_events=expected_subs,
            window_hours=window_hours,
            has_confounders=len(confounders) > 0,
            baseline_data_days=baseline["data_days"]
        )
        
        return {
            "window_start": window_start,
            "window_end": window_end,
            "window_hours": round(window_hours, 1),
            
            "baseline": baseline,
            "expected_subs": round(expected_subs, 1),
            "actual_subs": actual_subs,
            "subs_lift_pct": round(subs_lift, 1),
            
            "expected_revenue": round(expected_revenue, 2),
            "actual_revenue": round(actual_revenue, 2),
            "revenue_lift_pct": round(revenue_lift, 1),
            
            "content_type_deltas": content_type_deltas,
            "credit_weights": credit_weights,
            "total_delta_views": total_delta_views,
            
            "confounders": confounders,
            "confidence": confidence,
            "recommendation_tier": "confident" if confidence["score"] >= 0.7 else "hypothesis"
        }
    
    def _compute_dow_adjusted_expected(
        self,
        baseline: Dict,
        window_start: datetime,
        window_end: datetime
    ) -> float:
        """Compute expected subs with day-of-week adjustment."""
        if baseline.get("is_default") or "dow_factors" not in baseline:
            hours = (window_end - window_start).total_seconds() / 3600
            return baseline["subs_per_day"] * (hours / 24)
        
        expected = 0
        current = window_start
        
        while current < window_end:
            next_day = min(
                current.replace(hour=0, minute=0, second=0) + timedelta(days=1),
                window_end
            )
            hours_in_day = (next_day - current).total_seconds() / 3600
            
            dow = current.weekday()
            dow_factor = baseline["dow_factors"].get(dow, 1.0)
            
            expected += baseline["subs_per_day"] * (hours_in_day / 24) * dow_factor
            current = next_day
        
        return expected
    
    def _check_confounders(
        self,
        creator_id: UUID,
        window_start: datetime,
        window_end: datetime
    ) -> List[Dict]:
        """Check if any confounder events overlap with the window."""
        events = self.db.query(ConfounderEvent).filter(
            ConfounderEvent.creator_id == creator_id,
            ConfounderEvent.event_start <= window_end,
            # Event end is null (point event) or extends into window
            ((ConfounderEvent.event_end >= window_start) | 
             (ConfounderEvent.event_end.is_(None)))
        ).all()
        
        return [
            {
                "type": e.event_type.value,
                "description": e.description,
                "impact": e.estimated_impact.value if e.estimated_impact else "unknown",
                "start": e.event_start
            }
            for e in events
        ]
    
    def attribute_fans_weighted(
        self,
        creator_id: UUID,
        attribution_window_hours: int = 48
    ):
        """
        Attribute fans using weighted credit split across content types.
        
        Instead of "winner takes all" (highest views), each content type
        gets proportional credit based on view share in the attribution window.
        
        This fixes the "Reach Bias" problem where thirst traps steal credit
        from storytimes just because they have more views.
        """
        # Get unattributed fans
        fans = self.db.query(Fan).filter(
            Fan.creator_id == creator_id,
            Fan.attributed_content_type.is_(None)
        ).all()
        
        for fan in fans:
            # Method 1: Referral link (deterministic, highest confidence)
            if fan.referral_link_id:
                link = self.db.query(ReferralLink).get(fan.referral_link_id)
                if link and link.content_type_hint:
                    fan.attributed_content_type = link.content_type_hint
                    fan.attribution_method = "referral_link"
                    fan.attribution_confidence = 0.95
                    fan.attribution_weights = {link.content_type_hint: 1.0}
                    continue
            
            # Method 2: Weighted attribution by view delta share
            window_start = fan.acquired_at - timedelta(hours=attribution_window_hours)
            
            content_deltas = self.snapshot_mgr.get_content_type_deltas(
                creator_id, window_start, fan.acquired_at
            )
            
            if not content_deltas:
                continue
            
            total_views = sum(ct["views_delta"] for ct in content_deltas.values())
            
            if total_views == 0:
                continue
            
            # Compute weights
            weights = {}
            for ct, data in content_deltas.items():
                if data["views_delta"] > 0:
                    weights[ct] = data["views_delta"] / total_views
            
            if not weights:
                continue
            
            # Primary attribution goes to highest weight
            primary_type = max(weights, key=weights.get)
            
            fan.attributed_content_type = primary_type
            fan.attribution_method = "weighted_window"
            fan.attribution_weights = weights
            
            # Confidence based on concentration of weight
            # High concentration (one type dominates) = higher confidence
            max_weight = max(weights.values())
            fan.attribution_confidence = 0.3 + (max_weight * 0.5)  # 0.3 - 0.8 range
        
        self.db.commit()
```

---

## Confidence Framework

Fixed to use event counts, not post counts.

```python
# app/services/confidence.py
from dataclasses import dataclass
from typing import Optional
import numpy as np
from scipy import stats

@dataclass
class ConfidenceResult:
    score: float  # 0.0 - 1.0
    level: str    # "low", "medium", "high"
    reasons: list[str]
    min_events_met: bool
    
    def to_dict(self):
        return {
            "score": round(self.score, 2),
            "level": self.level,
            "reasons": self.reasons,
            "min_events_met": self.min_events_met
        }


class ConfidenceScorer:
    """
    Compute confidence scores for attribution claims.
    
    CRITICAL FIX: Confidence is based on:
    - Number of EVENTS (subs, revenue), NOT number of posts
    - Statistical significance of lift vs baseline
    - Data quality (baseline coverage, confounder presence)
    """
    
    # Minimum thresholds for any recommendation
    MIN_SUBS_FOR_RECOMMENDATION = 10
    MIN_SUBS_FOR_CONFIDENT = 25
    MIN_BASELINE_DAYS = 7
    
    def score(
        self,
        actual_events: int,
        expected_events: float,
        window_hours: float,
        has_confounders: bool = False,
        baseline_data_days: int = 14
    ) -> ConfidenceResult:
        """
        Score confidence in an attribution claim.
        
        Returns a ConfidenceResult with score, level, and reasoning.
        """
        reasons = []
        score = 0.5  # Start at medium
        
        # 1. Event count thresholds (most important)
        if actual_events < self.MIN_SUBS_FOR_RECOMMENDATION:
            reasons.append(f"Low sample: only {actual_events} subs (need {self.MIN_SUBS_FOR_RECOMMENDATION}+)")
            score -= 0.3
            min_events_met = False
        elif actual_events < self.MIN_SUBS_FOR_CONFIDENT:
            reasons.append(f"Moderate sample: {actual_events} subs")
            min_events_met = True
        else:
            reasons.append(f"Good sample: {actual_events} subs")
            score += 0.15
            min_events_met = True
        
        # 2. Statistical significance
        if expected_events > 0 and actual_events >= 5:
            # Poisson test for rate difference
            # H0: actual rate = expected rate
            p_value = self._poisson_test(actual_events, expected_events)
            
            if p_value < 0.05:
                reasons.append("Lift is statistically significant (p < 0.05)")
                score += 0.2
            elif p_value < 0.10:
                reasons.append("Lift is marginally significant (p < 0.10)")
                score += 0.1
            else:
                reasons.append(f"Lift not significant (p = {p_value:.2f})")
                score -= 0.1
        
        # 3. Baseline data quality
        if baseline_data_days < self.MIN_BASELINE_DAYS:
            reasons.append(f"Limited baseline: {baseline_data_days} days (prefer {self.MIN_BASELINE_DAYS}+)")
            score -= 0.15
        elif baseline_data_days >= 14:
            score += 0.05
        
        # 4. Confounder penalty
        if has_confounders:
            reasons.append("⚠️ Confounder event(s) overlap with window")
            score -= 0.2
        
        # 5. Window length sanity
        if window_hours < 24:
            reasons.append("Short window (<24h) increases noise")
            score -= 0.1
        
        # Clamp score
        score = max(0.1, min(0.95, score))
        
        # Determine level
        if score >= 0.7:
            level = "high"
        elif score >= 0.4:
            level = "medium"
        else:
            level = "low"
        
        return ConfidenceResult(
            score=score,
            level=level,
            reasons=reasons,
            min_events_met=min_events_met
        )
    
    def _poisson_test(self, observed: int, expected: float) -> float:
        """
        Two-sided Poisson test.
        Returns p-value for H0: observed comes from Poisson(expected).
        """
        if expected <= 0:
            return 1.0
        
        # Use exact Poisson test
        # P(X >= observed) if observed > expected, else P(X <= observed)
        if observed >= expected:
            p_upper = 1 - stats.poisson.cdf(observed - 1, expected)
            return 2 * min(p_upper, 0.5)  # Two-sided
        else:
            p_lower = stats.poisson.cdf(observed, expected)
            return 2 * min(p_lower, 0.5)
```

---

## Recommendation Engine

Two-tier output: Confident vs Hypothesis.

```python
# app/services/recommendations.py
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class RecommendationTier(str, Enum):
    CONFIDENT = "confident"    # High confidence, act on it
    HYPOTHESIS = "hypothesis"  # Test it, don't bet on it

@dataclass
class Recommendation:
    content_type: str
    action: str  # "post_more" or "post_less"
    tier: RecommendationTier
    lift_pct: float
    rationale: str
    confidence: float
    weekly_target: Optional[int] = None  # Suggested posts/week
    confounders: List[str] = None


class RecommendationEngine:
    """
    Generate actionable recommendations with explicit confidence tiers.
    
    CONFIDENT recommendations: High confidence, change behavior now
    HYPOTHESIS recommendations: Worth testing, but don't bet the farm
    """
    
    # Thresholds
    HIGH_LIFT_THRESHOLD = 50      # 1.5x baseline = +50%
    LOW_LIFT_THRESHOLD = -50      # 0.5x baseline = -50%
    MIN_VIEW_SHARE_FOR_POSTLESS = 0.10  # Only suggest "post less" if >10% of views
    MIN_SUBS_FOR_CONFIDENT = 25
    MIN_SUBS_FOR_HYPOTHESIS = 10
    
    def __init__(self, db: Session):
        self.db = db
        self.attribution_svc = AttributionService(db)
    
    def generate_recommendations(
        self,
        creator_id: UUID,
        days: int = 30
    ) -> dict:
        """
        Generate two-tier recommendations for a creator.
        
        Returns:
        {
            "confident": [Recommendation, ...],  # Act on these
            "hypothesis": [Recommendation, ...], # Test these
            "insufficient_data": [...]           # Can't say yet
        }
        """
        window_end = datetime.utcnow()
        window_start = window_end - timedelta(days=days)
        
        # Get attribution data
        attribution = self.attribution_svc.attribute_window(
            creator_id, window_start, window_end
        )
        
        # Get per-content-type performance
        content_types = self._get_content_type_performance(
            creator_id, window_start, window_end, attribution
        )
        
        confident = []
        hypothesis = []
        insufficient = []
        
        total_views = sum(ct["views_delta"] for ct in content_types.values())
        
        for ct_name, ct_data in content_types.items():
            if ct_name == "other":
                continue  # Skip catch-all
            
            view_share = ct_data["views_delta"] / total_views if total_views > 0 else 0
            attributed_subs = ct_data.get("attributed_subs", 0)
            lift = ct_data.get("lift_pct", 0)
            confidence = ct_data.get("confidence", {})
            
            # Determine tier
            if attributed_subs < self.MIN_SUBS_FOR_HYPOTHESIS:
                insufficient.append({
                    "content_type": ct_name,
                    "reason": f"Only {attributed_subs} subs attributed",
                    "views_delta": ct_data["views_delta"]
                })
                continue
            
            tier = (RecommendationTier.CONFIDENT 
                    if attributed_subs >= self.MIN_SUBS_FOR_CONFIDENT 
                       and confidence.get("score", 0) >= 0.7
                    else RecommendationTier.HYPOTHESIS)
            
            # Generate recommendation
            if lift >= self.HIGH_LIFT_THRESHOLD:
                rec = Recommendation(
                    content_type=ct_name,
                    action="post_more",
                    tier=tier,
                    lift_pct=lift,
                    rationale=self._generate_post_more_rationale(ct_name, lift, attributed_subs),
                    confidence=confidence.get("score", 0.5),
                    weekly_target=self._suggest_weekly_target(ct_data, "increase"),
                    confounders=ct_data.get("confounders", [])
                )
                (confident if tier == RecommendationTier.CONFIDENT else hypothesis).append(rec)
            
            elif lift <= self.LOW_LIFT_THRESHOLD and view_share >= self.MIN_VIEW_SHARE_FOR_POSTLESS:
                rec = Recommendation(
                    content_type=ct_name,
                    action="post_less",
                    tier=tier,
                    lift_pct=lift,
                    rationale=self._generate_post_less_rationale(ct_name, lift, view_share),
                    confidence=confidence.get("score", 0.5),
                    weekly_target=self._suggest_weekly_target(ct_data, "decrease"),
                    confounders=ct_data.get("confounders", [])
                )
                (confident if tier == RecommendationTier.CONFIDENT else hypothesis).append(rec)
        
        return {
            "confident": sorted(confident, key=lambda r: abs(r.lift_pct), reverse=True)[:3],
            "hypothesis": sorted(hypothesis, key=lambda r: abs(r.lift_pct), reverse=True)[:3],
            "insufficient_data": insufficient,
            "generated_at": datetime.utcnow(),
            "period_days": days,
            "total_subs": attribution["actual_subs"],
            "has_confounders": len(attribution["confounders"]) > 0
        }
    
    def _generate_post_more_rationale(
        self,
        content_type: str,
        lift: float,
        subs: int
    ) -> str:
        """Generate human-readable rationale for 'post more'."""
        ct_label = DEFAULT_TAXONOMY.get(content_type, {}).get("label", content_type)
        
        if lift >= 100:
            strength = "dramatically outperforms"
        elif lift >= 50:
            strength = "significantly outperforms"
        else:
            strength = "outperforms"
        
        return (
            f"{ct_label} content {strength} your baseline by {lift:.0f}%, "
            f"driving an estimated {subs} subs. Increase posting frequency."
        )
    
    def _generate_post_less_rationale(
        self,
        content_type: str,
        lift: float,
        view_share: float
    ) -> str:
        """Generate human-readable rationale for 'post less'."""
        ct_label = DEFAULT_TAXONOMY.get(content_type, {}).get("label", content_type)
        
        return (
            f"{ct_label} gets {view_share*100:.0f}% of your views but converts "
            f"{abs(lift):.0f}% below baseline. Reduce volume and reallocate to higher-converting types."
        )
    
    def _suggest_weekly_target(
        self,
        ct_data: Dict,
        direction: str
    ) -> int:
        """Suggest a weekly posting target."""
        current_weekly = ct_data.get("posts_per_week", 0)
        
        if direction == "increase":
            return max(current_weekly + 2, int(current_weekly * 1.5))
        else:
            return max(1, int(current_weekly * 0.5))
```

---

## Monday Email (Gated on Confidence)

```python
# app/tasks/email_tasks.py
from datetime import datetime, timedelta

@shared_task
def weekly_creator_digest():
    """
    Send Monday email with best performer and recommendations.
    
    CRITICAL: Only send strong claims when confidence is high.
    Low confidence gets softer language and "hypothesis" framing.
    """
    with get_db_session() as db:
        recommendation_engine = RecommendationEngine(db)
        
        agencies = db.query(Agency).filter(
            Agency.subscription_status == "active"
        ).all()
        
        for agency in agencies:
            for creator in agency.creators:
                if creator.status != "active":
                    continue
                
                # Get recommendations
                recs = recommendation_engine.generate_recommendations(creator.id)
                
                # Get best performer
                best_post = get_best_performer_last_week(db, creator.id)
                
                # Determine email tone based on confidence
                if recs["confident"]:
                    # High confidence: strong claims
                    email_type = "confident"
                    primary_recs = recs["confident"][:2]
                    headline = f"Clear wins for {creator.name} this week"
                elif recs["hypothesis"]:
                    # Low confidence: softer language
                    email_type = "hypothesis"
                    primary_recs = recs["hypothesis"][:2]
                    headline = f"Patterns worth testing for {creator.name}"
                else:
                    # Insufficient data
                    email_type = "diagnostic"
                    primary_recs = []
                    headline = f"Building baseline for {creator.name}"
                
                # Check for confounders
                confounder_warning = None
                if recs["has_confounders"]:
                    confounder_warning = (
                        "⚠️ External events (promo, collab, etc.) overlapped with this period. "
                        "Attribution may be less reliable."
                    )
                
                # Generate email
                email_html = render_weekly_email(
                    creator=creator,
                    email_type=email_type,
                    headline=headline,
                    best_post=best_post,
                    recommendations=primary_recs,
                    total_subs=recs["total_subs"],
                    confounder_warning=confounder_warning
                )
                
                send_email(
                    to=agency.notification_email,
                    subject=f"[FunnelLens] {headline}",
                    html=email_html
                )


def render_weekly_email(
    creator,
    email_type: str,
    headline: str,
    best_post,
    recommendations: List,
    total_subs: int,
    confounder_warning: Optional[str]
) -> str:
    """Render email with appropriate confidence framing."""
    
    if email_type == "confident":
        rec_header = "✅ Recommended Actions"
        rec_prefix = ""
    elif email_type == "hypothesis":
        rec_header = "🧪 Patterns to Test"
        rec_prefix = "Worth experimenting: "
    else:
        rec_header = "📊 What We're Tracking"
        rec_prefix = "Building data on: "
    
    # Build recommendations section
    rec_items = []
    for rec in recommendations:
        if rec.action == "post_more":
            action_text = f"Post more {rec.content_type} (target: {rec.weekly_target}/week)"
        else:
            action_text = f"Reduce {rec.content_type} (target: {rec.weekly_target}/week)"
        
        confidence_badge = ""
        if rec.tier == RecommendationTier.HYPOTHESIS:
            confidence_badge = " [hypothesis]"
        
        rec_items.append(f"{rec_prefix}{action_text}{confidence_badge}\n{rec.rationale}")
    
    # Assemble email
    template = f"""
    <h1>{headline}</h1>
    
    <p><strong>Last 7 days:</strong> {total_subs} new subs</p>
    
    {f'<p style="color: orange;">{confounder_warning}</p>' if confounder_warning else ''}
    
    {"<h2>🏆 Best Performer</h2>" + render_best_post(best_post) if best_post else ""}
    
    <h2>{rec_header}</h2>
    <ul>
    {"".join(f"<li>{item}</li>" for item in rec_items)}
    </ul>
    
    <p style="color: gray; font-size: 12px;">
    Attribution is probabilistic, not deterministic. These recommendations are based on 
    timing patterns and view deltas, not exact user tracking.
    </p>
    """
    
    return template
```

---

## Open Source Toolkit (Updated)

Added tools for snapshot/delta handling and statistical testing:

| Category | Package | License | Purpose |
|----------|---------|---------|---------|
| **Statistics** |
| scipy | BSD | [scipy/scipy](https://github.com/scipy/scipy) | Poisson tests, confidence intervals |
| statsmodels | BSD | [statsmodels/statsmodels](https://github.com/statsmodels/statsmodels) | Time series, regression |
| **Data Processing** |
| DuckDB | MIT | [duckdb/duckdb](https://github.com/duckdb/duckdb) | Fast delta queries on snapshots |
| Polars | MIT | [pola-rs/polars](https://github.com/pola-rs/polars) | Faster than Pandas for aggregations |
| **ML/NLP** |
| sentence-transformers | Apache 2.0 | [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Caption embeddings |
| **Data Quality** |
| Great Expectations | Apache 2.0 | [great-expectations/great_expectations](https://github.com/great-expectations/great_expectations) | Validate CSV imports |
| Pandera | MIT | [unionai-oss/pandera](https://github.com/unionai-oss/pandera) | DataFrame schemas |

---

## Stress Tests to Run Before Launch

Per the feedback, implement these validation checks:

### 1. Backtest with Referral Link Ground Truth

```python
def backtest_attribution_accuracy(creator_id: UUID) -> Dict:
    """
    Compare probabilistic attribution vs referral-link-attributed subs.
    Use referral link subs as ground truth.
    """
    # Get fans attributed via referral link (ground truth)
    link_fans = db.query(Fan).filter(
        Fan.creator_id == creator_id,
        Fan.attribution_method == "referral_link"
    ).all()
    
    # For each, compute what our weighted_window attribution would have said
    errors = []
    for fan in link_fans:
        actual_type = fan.attributed_content_type
        
        # Re-run weighted attribution
        window_start = fan.acquired_at - timedelta(hours=48)
        deltas = snapshot_mgr.get_content_type_deltas(
            creator_id, window_start, fan.acquired_at
        )
        
        if deltas:
            predicted_type = max(deltas, key=lambda ct: deltas[ct]["views_delta"])
            errors.append({
                "actual": actual_type,
                "predicted": predicted_type,
                "match": actual_type == predicted_type
            })
    
    accuracy = sum(1 for e in errors if e["match"]) / len(errors) if errors else 0
    
    return {
        "accuracy": accuracy,
        "sample_size": len(errors),
        "confusion_matrix": compute_confusion_matrix(errors)
    }
```

### 2. Negative Control (Placebo Windows)

```python
def placebo_test(creator_id: UUID, n_tests: int = 10) -> Dict:
    """
    Pick random windows with no major content posts.
    Verify we don't see systematic lift (would indicate broken baseline).
    """
    false_positives = 0
    
    for _ in range(n_tests):
        # Random window in last 60 days
        window_end = datetime.utcnow() - timedelta(days=random.randint(7, 60))
        window_start = window_end - timedelta(days=7)
        
        # Check if significant content was posted
        posts_in_window = db.query(SocialPost).filter(
            SocialPost.creator_id == creator_id,
            SocialPost.posted_at >= window_start,
            SocialPost.posted_at < window_end
        ).count()
        
        if posts_in_window > 5:  # Not a placebo window
            continue
        
        # Run attribution
        result = attribution_svc.attribute_window(creator_id, window_start, window_end)
        
        # Check if we'd make a recommendation (false positive)
        if abs(result["subs_lift_pct"]) > 50 and result["confidence"]["score"] > 0.5:
            false_positives += 1
    
    return {
        "tests_run": n_tests,
        "false_positives": false_positives,
        "false_positive_rate": false_positives / n_tests
    }
```

---

## Success Criteria (Revised)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Attribution accuracy | >60% match vs referral links | Backtest validation |
| False positive rate | <20% in placebo tests | Negative control tests |
| Confident recommendations | >1 per creator per week | Dashboard metrics |
| CSV import success | >95% | Import error rate |
| Time to first insight | <10 minutes | Onboarding funnel |
| Week-1 retention | >70% | Cohort analysis |

---

*Spec version 1.1 — Stress-test fixes incorporated*
