# FunnelLens

Analytics platform for creator agencies - measure which content types drive subscriber conversions.

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e .

# Run migrations
alembic upgrade head

# Seed sample data
python scripts/seed_sample_data.py

# Start API server
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs for API documentation.

## Features

- CSV import for social posts, fans, and revenue data
- Snapshot-based delta tracking for accurate view attribution
- Multi-tenant agency support
- Content type taxonomy (storytime, GRWM, thirst trap, etc.)

## Tech Stack

- **Backend**: FastAPI + Pydantic
- **Database**: PostgreSQL + SQLAlchemy 2.0
- **Migrations**: Alembic
