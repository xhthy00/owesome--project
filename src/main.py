"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.core.config import get_settings
from common.core.database import init_db
from common.router import register_routers
from common.middlewares.exception import register_exception_handlers

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
register_exception_handlers(app)

# Register routers
register_routers(app)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"code": 200, "message": "ok", "data": {"status": "ok"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)