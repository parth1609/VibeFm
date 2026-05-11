"""
RJ Module
=========
AI Radio Jockey script generation engine with composable context blocks.

Public surface
--------------
Context Blocks : PersonaContextBlock, SongContextBlock, WeatherContextBlock,
                 NewsContextBlock, AdContextBlock
Models         : RJScriptRequest, RJScriptResponse
Engine         : RJScriptEngine
Router         : router  (FastAPI APIRouter)
"""

from .context import (
    AdContextBlock,
    NewsContextBlock,
    PersonaContextBlock,
    SongContextBlock,
    WeatherContextBlock,
)
from .engine import RJScriptEngine
from .models import RJScriptRequest, RJScriptResponse
from .router import router

__all__ = [
    # Context Blocks
    "PersonaContextBlock",
    "SongContextBlock",
    "WeatherContextBlock",
    "NewsContextBlock",
    "AdContextBlock",
    # Models
    "RJScriptRequest",
    "RJScriptResponse",
    # Engine
    "RJScriptEngine",
    # Router
    "router",
]
