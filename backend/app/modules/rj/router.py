"""
RJ Module — FastAPI Router
============================

Exposes the RJ script generation pipeline as REST endpoints.

Endpoints:
    POST /rj/generate   — Generate an RJ interlude script
    GET  /rj/health      — Health check for the RJ engine
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .engine import RJScriptEngine
from .models import RJScriptRequest, RJScriptResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rj", tags=["RJ Script Engine"])

# Module-level engine instance — created once, reused across requests
_engine = RJScriptEngine()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=RJScriptResponse,
    summary="Generate an RJ interlude script",
    description=(
        "Accepts a composable request with any combination of context blocks "
        "(persona, songs, weather, news, ad). Only populated blocks appear "
        "in the LLM prompt. Omitted blocks are silently skipped."
    ),
)
async def generate_script(request: RJScriptRequest) -> RJScriptResponse:
    """
    Generate a radio interlude script.

    Include any combination of context blocks — the engine assembles
    the prompt from only what you provide.

    **Minimal request** (just persona + songs)::

        {
            "persona": {"name": "Max", "tone": "energetic"},
            "songs": {"played": ["Blinding Lights"], "up_next": ["Levitating"]}
        }

    **Full request** (all 5 blocks)::

        {
            "persona": {"name": "Zara", "tone": "chill"},
            "songs": {"played": ["Song A", "Song B"], "up_next": ["Song C"]},
            "weather": {"city": "Mumbai", "temp": "29°C", "condition": "Humid"},
            "news": {"headlines": ["India wins!", "Tech layoffs"]},
            "ad": {"sponsor_script": "Brought to you by Notion..."}
        }

    **Empty request** (uses defaults)::

        {}
    """
    try:
        response = await _engine.generate(request)
        logger.info(
            "✅ Script generated — persona=%s, blocks=%s, mock=%s",
            response.persona_name,
            response.active_blocks,
            response.mock_mode,
        )
        return response
    except Exception as e:
        logger.exception("Failed to generate RJ script")
        raise HTTPException(
            status_code=500,
            detail=f"Script generation failed: {e}",
        )


@router.get(
    "/health",
    summary="RJ engine health check",
)
async def health_check():
    """Check if the RJ engine is operational."""
    return {
        "status": "ok",
        "engine": "RJScriptEngine",
        "mock_mode": _engine.is_mock,
        "message": (
            "Running in mock mode (no GEMINI_API_KEY set)"
            if _engine.is_mock
            else "Running in live mode (Gemini API connected)"
        ),
    }
