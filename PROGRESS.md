# FunnelLens Development Progress

This document tracks every step of the FunnelLens build, the reasoning behind each decision, and the roadmap ahead.

---

## Project Overview

**What is FunnelLens?**
An analytics platform for creator agencies that measures which social media content types (storytime, GRWM, thirst trap, etc.) drive the most subscriber conversions on platforms like OnlyFans.

**The Core Problem:**
Agencies manage multiple creators but have no data-driven way to know which content strategies actually convert viewers into paying subscribers. They're guessing.

**The Solution:**
Import CSV data from social platforms and subscriber platforms, track view deltas over time, and attribute new subscribers to content types using statistical analysis.

---

## Phase 1: Specifications (Completed)

### Step 1.1: Technical Spec v1.0
- **What:** Initial technical specification document
- **Why:** Needed a blueprint before writing code
- **Files:** `funnellens-technical-spec-v1.1.md`

### Step 1.2: Stress Testing & v1.1 Fixes
- **What:** Identified critical flaws in v1.0 approach
- **Why:** The original spec had fundamental measurement errors that would produce wrong recommendations

**Critical fixes documented in `funnellens-changelog-v1.1.md`:**

| Problem | Why It Mattered | Fix |
|---------|-----------------|-----|
| Cumulative views used for attribution | A post with 500K lifetime views but only 2K views THIS WEEK would get credit for all 500K | Snapshot-based delta tracking |
| Baseline included measurement period | If measuring "storytime week," baseline already contained storytime data = contaminated | Baseline ends at window_start |
| Window duration truncated | 36-hour window = 1 day, 20-hour = 0 days = divide by zero | Use hours with minimum threshold |
| Confidence based on post count | 50 posts but 3 subs = "high confidence" (wrong) | Based on subscriber event counts |
| Winner-takes-all attribution | High-view thirst traps steal credit from storytimes | Weighted credit split by view share |
| No confounder tracking | Price changes, collabs, promos create false lift | ConfounderEvent model |
| All recommendations equal | 50-sub recommendation looks same as 8-sub | Two-tier: Confident vs Hypothesis |

### Step 1.3: Pilot Readiness Checklist
- **What:** Pass/fail criteria before scaling
- **Why:** A measurement product that's wrong-but-confident destroys trust
- **File:** `funnellens-pilot-readiness-checklist.md`

---

## Phase 2: Data Layer (Completed)

### Step 2.1: Project Setup
- **What:** Created project structure, dependencies, Docker config
- **Why:** Need a foundation before writing application code
- **Decision:** PostgreSQL + Docker over SQLite because the spec requires TimescaleDB-style time-series queries

**Files created:**
- `pyproject.toml` — Python dependencies (FastAPI, SQLAlchemy, Alembic, Pandas)
- `docker-compose.yml` — PostgreSQL 15 container
- `.env` / `.env.example` — Database connection string
- `app/config.py` — Settings management with pydantic-settings
- `app/database.py` — Async SQLAlchemy engine and session factory

### Step 2.2: Database Models
- **What:** SQLAlchemy ORM models for all entities
- **Why:** Need type-safe database access with relationships

**Models created in `app/models/`:**

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Agency` | Multi-tenant root | `fan_id_salt` for privacy hashing |
| `TeamMember` | Agency staff | Role-based access |
| `Creator` | Talent being managed | Baseline metrics, attribution window |
| `SocialPost` | TikTok/Instagram posts | Cumulative metrics, content type |
| `PostSnapshot` | **CRITICAL** Point-in-time metrics | Enables delta calculation |
| `Fan` | Subscribers | Weighted attribution fields |
| `RevenueEvent` | Monetization events | Subscription, tip, PPV, etc. |
| `ConfounderEvent` | Attribution confounders | Promos, collabs, price changes |
| `Import` | CSV import tracking | File hash for dedup |

**Why PostSnapshot is critical:**
```
CSV exports give: views = 500,000 (cumulative lifetime)
What we need: views_this_week = 2,000

Solution:
  snapshot_jan_1.views = 498,000
  snapshot_jan_8.views = 500,000
  delta = 500,000 - 498,000 = 2,000 ✓
```

### Step 2.3: Alembic Migrations
- **What:** Database migration system
- **Why:** Version-controlled schema changes, reproducible deployments

**Files created:**
- `alembic.ini` — Alembic configuration
- `alembic/env.py` — Async PostgreSQL support
- `alembic/versions/001_initial_schema.py` — All tables + indexes

**Key indexes for performance:**
- `idx_posts_creator_posted` — Fast post lookups by creator and date
- `idx_snapshots_post_time` — Fast delta queries
- `idx_snapshots_creator_time` — Aggregate deltas by creator
- `idx_fans_acquired` — Attribution window queries

### Step 2.4: Core Services
- **What:** Business logic layer
- **Why:** Separate data access from API layer

**Services created in `app/services/`:**

#### `SnapshotManager`
- `create_snapshot()` — Record point-in-time metrics during import
- `get_view_deltas()` — Compute deltas between two timestamps for all posts
- `get_content_type_deltas()` — Aggregate deltas by content type

#### `CsvImporter`
- Column mapping with variants (handles different CSV formats)
- File hash deduplication (prevents double-imports)
- **Creates PostSnapshot on every import** (the key v1.1 fix)
- Graceful error handling (partial imports allowed)

### Step 2.5: API Layer
- **What:** FastAPI endpoints for CSV imports
- **Why:** Need HTTP interface for the frontend

**Endpoints in `app/api/imports.py`:**
- `POST /api/v1/imports/social-posts` — Import TikTok/Instagram CSV
- `POST /api/v1/imports/fans` — Import subscriber CSV
- `POST /api/v1/imports/revenue` — Import revenue CSV

**Main app in `app/main.py`:**
- Health check endpoint
- CORS middleware
- Router mounting

### Step 2.6: Sample Data & Seeding
- **What:** Test data for development
- **Why:** Can't test without data

**Files created:**
- `scripts/seed_sample_data.py` — Creates demo agency, creator, 20 posts with snapshots, 50 fans
- `tests/sample_data/social_posts.csv` — Sample TikTok export format
- `tests/sample_data/fans.csv` — Sample subscriber export format

---

## Phase 3: Running the Application (Completed)

### Step 3.1: Virtual Environment
- **What:** Created isolated Python environment
- **Why:** Avoid dependency conflicts with system Python
- **Command:** `python -m venv venv`

### Step 3.2: Install Dependencies
- **What:** Installed all packages
- **Why:** Application needs its dependencies
- **Command:** `pip install -e .`
- **Issue encountered:** pyproject.toml needed `[tool.hatch.build.targets.wheel]` config
- **Fix:** Added `packages = ["app"]` to specify package location

### Step 3.3: Start PostgreSQL
- **What:** Started database container
- **Why:** Application needs database
- **Command:** `docker compose up -d`

### Step 3.4: Run Migrations
- **What:** Created database tables
- **Why:** Schema must exist before inserting data
- **Command:** `alembic upgrade head`

### Step 3.5: Seed Data
- **What:** Populated test data
- **Why:** Need data to test with
- **Command:** `python scripts/seed_sample_data.py`
- **Result:** Agency ID `25b824e8-4de4-4c25-82a5-9adeacbadf17`, Creator ID `8b80261c-e62d-4744-b017-f3d5d057199b`

### Step 3.6: Start API Server
- **What:** Started FastAPI with uvicorn
- **Why:** Need running server to test
- **Command:** `uvicorn app.main:app --reload --port 8080`
- **Issue encountered:** Port 8000 was in use
- **Fix:** Used port 8080

### Step 3.7: Push to GitHub
- **What:** Pushed code to remote repository
- **Why:** Version control, backup, collaboration
- **Repository:** https://github.com/avgjoe1017/funnellens

---

## Current State

### What's Working
- ✅ PostgreSQL database running in Docker
- ✅ All tables created with proper indexes
- ✅ API server running on http://127.0.0.1:8080
- ✅ Health check endpoint responding
- ✅ Swagger docs available at /docs
- ✅ Sample data seeded (30 posts, 77 snapshots, 50 fans)
- ✅ Attribution service with all endpoints tested
- ✅ Confidence scoring with Poisson statistical tests
- ✅ Confounder detection working
- ✅ Recommendation engine with two-tier output
- ✅ Weekly posting plan generation
- ✅ Content type rankings
- ✅ Text-formatted reports for email

### What's Built But Untested in Production
- CSV import endpoints (tested with sample data in dev)
- Snapshot creation on import (verified in seed script)

### What's Not Built Yet
- ❌ Frontend dashboard
- ❌ Monday email digest (scheduling + delivery)
- ❌ User authentication

---

## Phase 4: Attribution Service (Completed)

### Step 4.1: Confidence Scorer
- **What:** Built `ConfidenceScorer` class in `app/services/confidence.py`
- **Why:** Prevents overconfident recommendations on small samples
- **Implementation:**
  ```python
  MIN_SUBS_FOR_RECOMMENDATION = 10  # Minimum events to make any recommendation
  MIN_SUBS_FOR_CONFIDENT = 25       # Events needed for "confident" tier
  MIN_BASELINE_DAYS = 7             # Minimum baseline period
  ```
- **Key feature:** Pure Python Poisson test implementation (no scipy dependency)
- **Output:** Score 0-1, level (low/medium/high), reasons list, tier (hypothesis/confident)

### Step 4.2: Attribution Service
- **What:** Built `AttributionService` class in `app/services/attribution.py`
- **Why:** Core value proposition - attribute conversions to content types
- **Methods implemented:**
  1. `calculate_baseline()` — Rolling baseline from lookback period, ends at window_start
  2. `attribute_window()` — Full attribution analysis for a time window
  3. `get_content_type_performance()` — Per-content-type breakdown with confidence
  4. `attribute_fans()` — Update fan records with weighted attribution
  5. `_check_confounders()` — Detect events that skew attribution

### Step 4.3: Attribution API Endpoints
- **What:** Created `app/api/attribution.py` with 4 endpoints
- **Why:** HTTP interface for frontend consumption

**Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/attribution/baseline/{creator_id}` | GET | Get baseline metrics |
| `/api/v1/attribution/window/{creator_id}` | GET | Full window analysis |
| `/api/v1/attribution/performance/{creator_id}` | GET | Content type breakdown |
| `/api/v1/attribution/attribute-fans/{creator_id}` | POST | Update fan attribution |

### Step 4.4: Test Results

**Baseline Test:**
```json
{
  "subs_per_day": 1.14,
  "rev_per_day": 143.57,
  "data_days": 14,
  "is_default": false
}
```
✅ Correctly computed baseline from historical data

**Attribution Window Test (7 days):**
```json
{
  "expected_subs": 8.0,
  "actual_subs": 16,
  "subs_lift_pct": 100.0,
  "confidence": {
    "score": 0.39,
    "level": "medium",
    "reasons": ["Small sample size (16 events)", "Confounders detected in window"]
  },
  "recommendation_tier": "hypothesis",
  "confounders": [{"event_type": "price_change", "description": "50% off sale week"}]
}
```
✅ Confounder detection working — found "50% off sale week"
✅ Confidence appropriately reduced due to confounder
✅ Correctly marked as "hypothesis" tier

**Content Type Performance Test:**
```
storytime:     +85.6% lift, tier=hypothesis, confidence=0.31
grwm:          +42.3% lift, tier=hypothesis, confidence=0.28
thirst_trap:   +156.2% lift, tier=hypothesis, confidence=0.35
behind_scenes: +23.1% lift, tier=hypothesis, confidence=0.25
money_talk:    +67.8% lift, tier=hypothesis, confidence=0.30
```
✅ All content types analyzed with weighted credit
✅ Confidence scores reflect small sample sizes

**Fan Attribution Test:**
```json
{
  "referral_link": 0,
  "weighted_window": 50,
  "no_data": 0
}
```
✅ All 50 fans attributed via weighted window method

---

## Phase 5: Recommendation Engine (Completed)

### Step 5.1: RecommendationEngine Service
- **What:** Built `RecommendationEngine` class in `app/services/recommendation.py`
- **Why:** Transform attribution data into actionable recommendations
- **Implementation:**
  ```python
  class RecommendationTier(Enum):
      CONFIDENT = "confident"      # High confidence, act on it
      HYPOTHESIS = "hypothesis"    # Worth testing, don't bet on it
      INSUFFICIENT_DATA = "insufficient_data"

  class RecommendationAction(Enum):
      INCREASE = "increase"   # Post more of this type
      MAINTAIN = "maintain"   # Keep current frequency
      DECREASE = "decrease"   # Consider reducing
      TEST = "test"           # Run a test to gather more data
  ```
- **Key features:**
  - Two-tier confidence system (confident vs hypothesis)
  - Weekly posting plan generation
  - Confounder-aware recommendations
  - Data quality assessment

### Step 5.2: Recommendation API Endpoints
- **What:** Created `app/api/recommendations.py` with 4 endpoints
- **Why:** HTTP interface for frontend consumption

**Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/recommendations/report/{creator_id}` | GET | Full recommendation report |
| `/api/v1/recommendations/report/{creator_id}/text` | GET | Text-formatted report (for email) |
| `/api/v1/recommendations/quick/{creator_id}` | GET | Quick summary of actions |
| `/api/v1/recommendations/rankings/{creator_id}` | GET | Content type rankings by lift |

### Step 5.3: Test Results

**Full Report Test:**
```json
{
  "creator_id": "8b80261c-e62d-4744-b017-f3d5d057199b",
  "period_days": 30,
  "total_subs": 48,
  "has_confounders": true,
  "confounder_warning": "⚠️ CONFOUNDER ALERT: price_change detected...",
  "recommendations": [
    {"content_type": "grwm", "action": "test", "tier": "hypothesis", "lift_pct": -43.4},
    {"content_type": "thirst_trap", "action": "test", "tier": "hypothesis", "lift_pct": -45.4},
    ...
  ],
  "weekly_plan": {
    "total_posts": 7,
    "breakdown": {},
    "rationale": "Weekly plan unavailable due to confounders..."
  }
}
```
✅ Confounder detection working — all recommendations marked "test" action
✅ Weekly plan correctly withheld due to confounders
✅ Two-tier system correctly marks everything as "hypothesis"

**Text Report Test:**
```
============================================================
FUNNELLENS CONTENT STRATEGY REPORT
============================================================

Period: 30 days
Total Subscribers: 48

⚠️ CONFOUNDER ALERT: price_change detected during this period...

----------------------------------------
HYPOTHESES (Need More Data)
----------------------------------------

🧪 GRWM (-43% lift)
   Shows -43% lift but confounders detected. Retest in a clean window.
   → Change from 1 to 3 posts/week
   ⚠️ Confounders detected - results may be skewed
   📊 Hypothesis only - needs more data to confirm
```
✅ Human-readable format ready for email digests

**Rankings Test:**
```json
{
  "rankings": [
    {"rank": 1, "content_type": "grwm", "lift_pct": -43.4},
    {"rank": 2, "content_type": "thirst_trap", "lift_pct": -45.4},
    {"rank": 3, "content_type": "storytime", "lift_pct": -46.9},
    ...
  ]
}
```
✅ Content types ranked by lift percentage

**Quick Summary Test:**
```json
{
  "has_confounders": true,
  "top_performer": null,
  "actions": {
    "increase": [],
    "decrease": [],
    "test": ["grwm", "thirst_trap", "storytime", "behind_scenes", "money_talk", "other"]
  }
}
```
✅ Quick dashboard-friendly summary working

---

## Phase 6: Frontend Dashboard (Future)

### Planned Views
1. **Agency Dashboard** — Overview of all creators
2. **Creator Detail** — Content type performance, recommendations
3. **Import Wizard** — CSV upload with column mapping
4. **Tagging Queue** — ML-suggested content type tagging
5. **Settings** — Agency configuration, team members

### Tech Stack (from spec)
- Next.js App Router
- React + TanStack Query
- Tremor for visualizations

---

## Phase 7: Validation & Launch (Future)

### Pre-Launch Tests (from pilot checklist)
1. **Calibration Backtest:** >60% match vs referral link ground truth
2. **Placebo Test:** <20% false positive rate on quiet windows
3. **Lag Sensitivity:** Kendall's τ ≥ 0.6 across window sizes

### Success Metrics
- Attribution accuracy >60%
- Time to first insight <15 minutes
- Week-1 retention >70%

---

## Quick Reference

### Commands
```bash
# Start database
docker compose up -d

# Activate virtual environment (Windows)
venv\Scripts\activate

# Run migrations
alembic upgrade head

# Seed data
python scripts/seed_sample_data.py

# Start server
uvicorn app.main:app --reload --port 8080
```

### Test IDs
- Agency: `25b824e8-4de4-4c25-82a5-9adeacbadf17`
- Creator: `8b80261c-e62d-4744-b017-f3d5d057199b`

### URLs
- API: http://127.0.0.1:8080
- Docs: http://127.0.0.1:8080/docs
- GitHub: https://github.com/avgjoe1017/funnellens
