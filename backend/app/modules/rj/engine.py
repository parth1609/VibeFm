"""
RJ Script Engine — Gemini LLM Integration
==========================================

Calls Google Gemini (``google-generativeai``) to generate radio interlude
scripts from a composable prompt.

Supports two modes:
  - **Live mode**: Calls Gemini API (requires ``GEMINI_API_KEY`` env var)
  - **Mock mode**: Returns a plausible canned script without any API call
    (useful for development, testing, or when no API key is available)

Usage::

    engine = RJScriptEngine()  # auto-detects mock vs live from env

    request = RJScriptRequest(
        persona=PersonaContextBlock(name="Max", tone="energetic"),
        songs=SongContextBlock(played=["Song A"], up_next=["Song B"]),
    )

    response = await engine.generate(request)
    print(response.script)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .models import RJScriptRequest, RJScriptResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock responses for development / no-API-key mode
# ---------------------------------------------------------------------------

_MOCK_SCRIPTS: list[str] = [
    (
        "What's good, beautiful people! You just vibed with some absolute bangers — "
        "hope those tracks hit different today. We've got more heat coming your way, "
        "so don't you dare touch that dial. Stay locked in, this is your station, "
        "your vibe, your moment. Let's keep this energy rolling!"
    ),
    (
        "Hey hey hey, welcome back! If you've been riding with us, you already know "
        "we don't do boring over here. Those last few tracks were pure gold. "
        "But trust me, what's coming up next? Even better. Sit back, relax, "
        "and let the music do the talking. You're listening to VibeFm!"
    ),
    (
        "Alright alright, we're back in the mix! I hope you're feeling those "
        "frequencies because we are just getting started. Whether you're "
        "commuting, cooking, or just chilling — this one's for you. "
        "Let's ride into the next set together!"
    ),
]

_mock_index = 0


def _get_mock_script() -> str:
    """Cycle through mock scripts for variety."""
    global _mock_index
    script = _MOCK_SCRIPTS[_mock_index % len(_MOCK_SCRIPTS)]
    _mock_index += 1
    return script


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RJScriptEngine:
    """
    Generates RJ interlude scripts using Google Gemini or a mock fallback.

    Instantiation auto-detects whether to use mock mode:
      - If ``GEMINI_API_KEY`` is set in the environment → **live mode**
      - Otherwise → **mock mode** (no API calls)

    You can also force a mode with ``RJScriptEngine(mock_mode=True)``.
    """

    def __init__(self, *, mock_mode: Optional[bool] = None) -> None:
        self._api_key = os.getenv("GEMINI_API_KEY", "").strip()

        if mock_mode is not None:
            self._mock_mode = mock_mode
        else:
            # Auto-detect: if no API key, fall back to mock
            self._mock_mode = not bool(self._api_key)

        if self._mock_mode:
            logger.info(
                "🎙️ RJScriptEngine initialized in MOCK mode "
                "(set GEMINI_API_KEY to enable live generation)"
            )
        else:
            logger.info("🎙️ RJScriptEngine initialized in LIVE mode (Gemini API)")

    @property
    def is_mock(self) -> bool:
        return self._mock_mode

    # ------------------------------------------------------------------
    # Main generation method
    # ------------------------------------------------------------------

    async def generate(self, request: RJScriptRequest) -> RJScriptResponse:
        """
        Generate an RJ interlude script from the given request.

        Args:
            request: Composable script request with any combination of
                     context blocks populated.

        Returns:
            ``RJScriptResponse`` containing the generated script text
            and metadata.
        """
        system_prompt, user_prompt = request.build_prompt()
        active_blocks = request.active_block_names()
        persona_name = (request.persona.name if request.persona else "VibeFm Host")

        logger.info(
            "Generating RJ script — persona=%s, blocks=%s, mock=%s",
            persona_name,
            active_blocks,
            self._mock_mode,
        )
        logger.debug("System prompt:\n%s", system_prompt)
        logger.debug("User prompt:\n%s", user_prompt)

        if self._mock_mode:
            return self._generate_mock(request, active_blocks, persona_name)
        else:
            return await self._generate_live(
                system_prompt, user_prompt, active_blocks, persona_name
            )

    # ------------------------------------------------------------------
    # Mock generation
    # ------------------------------------------------------------------

    def _generate_mock(
        self,
        request: RJScriptRequest,
        active_blocks: list[str],
        persona_name: str,
    ) -> RJScriptResponse:
        """Return a canned script with contextual touches."""
        base_script = _get_mock_script()

        # Weave in some context if available
        extras: list[str] = []
        if request.weather:
            extras.append(
                f"It's {request.weather.temp} and {request.weather.condition} "
                f"out here in {request.weather.city}."
            )
        if request.news and request.news.headlines:
            extras.append(
                f"Oh, and in case you missed it — {request.news.headlines[0]}. "
                f"Wild, right?"
            )
        if request.ad:
            extras.append(
                f"Quick shoutout — {request.ad.sponsor_script}"
            )

        if extras:
            script = base_script + " " + " ".join(extras)
        else:
            script = base_script

        return RJScriptResponse(
            script=script,
            persona_name=persona_name,
            active_blocks=active_blocks,
            tokens_used=0,
            mock_mode=True,
        )

    # ------------------------------------------------------------------
    # Live Gemini generation
    # ------------------------------------------------------------------

    async def _generate_live(
        self,
        system_prompt: str,
        user_prompt: str,
        active_blocks: list[str],
        persona_name: str,
    ) -> RJScriptResponse:
        """Call the Gemini API to generate a script."""
        try:
            import google.generativeai as genai
        except ImportError:
            logger.error(
                "google-generativeai package not installed. "
                "Run: uv add google-generativeai"
            )
            raise RuntimeError(
                "google-generativeai is required for live mode. "
                "Install it with: uv add google-generativeai"
            )

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=system_prompt,
        )

        logger.info("Calling Gemini API (gemini-1.5-flash)…")
        response = await model.generate_content_async(user_prompt)

        # Extract token usage
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = (
                getattr(response.usage_metadata, "total_token_count", 0) or 0
            )

        script_text = response.text.strip()
        logger.info(
            "Gemini response received — %d chars, %d tokens",
            len(script_text),
            tokens_used,
        )

        return RJScriptResponse(
            script=script_text,
            persona_name=persona_name,
            active_blocks=active_blocks,
            tokens_used=tokens_used,
            mock_mode=False,
        )
