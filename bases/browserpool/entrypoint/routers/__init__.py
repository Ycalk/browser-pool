from .browsers import router as browsers_router
from .internal import router as internal_router
from .node import router as node_router
from .proxy import router as proxy_router

__all__ = ["browsers_router", "internal_router", "node_router", "proxy_router"]
