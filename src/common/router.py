"""Central router aggregation."""

from system.api.system import router as system_router
from datasource.api.datasource import router as datasource_router
from chat.api.chat import router as chat_router


def get_all_routers() -> list:
    """Get all API routers."""
    return [
        system_router,
        datasource_router,
        chat_router,
    ]


def register_routers(app) -> None:
    """Register all routers to the FastAPI app."""
    for router in get_all_routers():
        app.include_router(router, prefix="/api/v1")
