"""FunnelLens API application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import attribution_router, imports_router, recommendations_router
from app.config import settings

app = FastAPI(
    title="FunnelLens",
    description="Analytics platform for creator agencies - measure which content types drive conversions",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(imports_router)
app.include_router(attribution_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "FunnelLens API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
