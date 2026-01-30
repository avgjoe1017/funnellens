# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d

# Install dependencies
pip install -e .

# Run migrations
alembic upgrade head

# Seed sample data
python scripts/seed_sample_data.py

# Start API server
uvicorn app.main:app --reload
```

## Project Structure

```
funnellens/
├── app/
│   ├── api/              # FastAPI routes
│   │   └── imports.py    # POST /api/v1/imports endpoints
│   ├── models/           # SQLAlchemy models
│   │   ├── agency.py     # Agency, TeamMember
│   │   ├── creator.py    # Creator
│   │   ├── social_post.py # SocialPost, PostSnapshot (critical for deltas)
│   │   ├── fan.py        # Fan, RevenueEvent
│   │   ├── confounder.py # ConfounderEvent
│   │   └── import_log.py # Import tracking
│   ├── services/
│   │   ├── csv_importer.py     # CSV parsing + snapshot creation
│   │   └── snapshot_manager.py # Delta calculations
│   ├── config.py         # Settings from env
│   ├── database.py       # DB connection
│   └── main.py           # FastAPI app
├── alembic/              # Database migrations
├── tests/sample_data/    # Test CSV files
└── scripts/
    └── seed_sample_data.py
```

## Key Concepts

### The Delta Problem (v1.1 Fix)
CSV exports give cumulative views. Never use cumulative values for attribution—always compute deltas between snapshots:
```python
views_during_window = snapshot_end.views - snapshot_start.views
```

### Snapshot System
Every CSV import creates `PostSnapshot` records. The `SnapshotManager` service computes deltas:
- `get_view_deltas()` - per-post deltas for a time period
- `get_content_type_deltas()` - aggregated by content type

### Import Flow
1. CSV uploaded via `/api/v1/imports/social-posts`
2. `CsvImporter` parses and validates columns
3. Creates/updates `SocialPost` records
4. Creates `PostSnapshot` for each post (critical!)
5. Returns import stats

## Spec Documents

- `funnellens-technical-spec-v1.1.md` — Full implementation spec
- `funnellens-changelog-v1.1.md` — v1.0 → v1.1 fixes
- `funnellens-pilot-readiness-checklist.md` — Launch validation tests

## Database

PostgreSQL via Docker on port 5432. Connection string in `.env`:
```
DATABASE_URL=postgresql+asyncpg://funnellens:funnellens_dev@localhost:5432/funnellens
```

## API Endpoints

- `GET /health` — Health check
- `POST /api/v1/imports/social-posts` — Import social post CSV
- `POST /api/v1/imports/fans` — Import fan/subscriber CSV
- `POST /api/v1/imports/revenue` — Import revenue events CSV

## Content Types

Default taxonomy: `storytime`, `grwm`, `thirst_trap`, `behind_scenes`, `money_talk`, `other`

## Next Steps (Not Yet Built)

- Attribution service (baseline calculation, weighted credit split)
- Confidence scorer (event-count based, Poisson tests)
- Recommendation engine (two-tier: Confident vs Hypothesis)
- Frontend dashboard
