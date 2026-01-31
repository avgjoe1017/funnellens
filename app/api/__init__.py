"""FunnelLens API routes."""

from app.api.attribution import router as attribution_router
from app.api.imports import router as imports_router
from app.api.recommendations import router as recommendations_router
from app.api.tracking_links import router as tracking_links_router

__all__ = [
    "attribution_router",
    "imports_router",
    "recommendations_router",
    "tracking_links_router",
]
