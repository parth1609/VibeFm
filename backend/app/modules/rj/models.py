"""
RJ Module — Data Models
========================

Core request/response models for the RJ script generation pipeline.

The key abstraction is ``RJScriptRequest`` which holds **optional**
ContextBlock fields.  Only the blocks you populate will appear in the
final Gemini prompt — enabling mix-and-match usage:

    # Full context (all 5 blocks)
    req = RJScriptRequest(
        persona=PersonaContextBlock(name="Max", tone="energetic"),
        songs=SongContextBlock(played=["Song A"], up_next=["Song B"]),
        weather=WeatherContextBlock(city="Mumbai", temp="29°C", condition="Humid"),
        news=NewsContextBlock(headlines=["India wins!"]),
        ad=AdContextBlock(sponsor_script="Brought to you by Notion..."),
    )

    # Minimal (only 2 blocks)
    req = RJScriptRequest(
        persona=PersonaContextBlock(name="Zara", tone="chill"),
        songs=SongContextBlock(played=["Blinding Lights"], up_next=["Levitating"]),
    )
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .context import (
    AdContextBlock,
    NewsContextBlock,
    PersonaContextBlock,
    SongContextBlock,
    WeatherContextBlock,
)


# ---------------------------------------------------------------------------
# Default persona — used when none is provided
# ---------------------------------------------------------------------------

_DEFAULT_PERSONA = PersonaContextBlock(
    name="VibeFm Host",
    tone="friendly and upbeat",
)


# ---------------------------------------------------------------------------
# Script Request
# ---------------------------------------------------------------------------


class RJScriptRequest(BaseModel):
    """
    Composable request to generate an RJ interlude script.

    All context blocks are **optional** (except persona, which falls back
    to a default).  Only populated blocks are included in the prompt.

    This is the core design: include what you want, omit what you don't.
    """

    persona: Optional[PersonaContextBlock] = Field(
        default=None,
        description="RJ identity. Falls back to a friendly default if omitted.",
    )
    songs: Optional[SongContextBlock] = Field(
        default=None,
        description="Songs just played + up next",
    )
    weather: Optional[WeatherContextBlock] = Field(
        default=None,
        description="Current weather conditions",
    )
    news: Optional[NewsContextBlock] = Field(
        default=None,
        description="Top news headlines",
    )
    ad: Optional[AdContextBlock] = Field(
        default=None,
        description="Sponsor / ad copy to weave in",
    )

    # ------------------------------------------------------------------
    # Prompt assembly — the heart of the composability logic
    # ------------------------------------------------------------------

    def build_prompt(self) -> tuple[str, str]:
        """
        Assemble the Gemini prompt from only the populated context blocks.

        Returns:
            A tuple of ``(system_prompt, user_prompt)`` strings.

        The system prompt carries the persona instructions.
        The user prompt carries the context + generation instruction.
        """
        # --- System prompt (persona) ---
        active_persona = self.persona or _DEFAULT_PERSONA
        system_prompt = active_persona.render_system()

        # --- User prompt (context sections) ---
        context_lines: list[str] = []

        # Iterate over all context blocks in a defined order.
        # Each block is Optional — if None, we simply skip it.
        blocks = [
            self.songs,
            self.weather,
            self.news,
            self.ad,
        ]

        for block in blocks:
            if block is not None:
                context_lines.append(block.render())

        # Build the user-facing prompt
        if context_lines:
            context_section = "Context:\n" + "\n".join(f"  {line}" for line in context_lines)
        else:
            context_section = "Context: (No specific context provided — improvise!)"

        user_prompt = f"{context_section}\n\nGenerate a radio interlude script."

        return system_prompt, user_prompt

    def active_block_names(self) -> list[str]:
        """Return names of the context blocks that are populated."""
        names: list[str] = []
        if self.persona:
            names.append("persona")
        if self.songs:
            names.append("songs")
        if self.weather:
            names.append("weather")
        if self.news:
            names.append("news")
        if self.ad:
            names.append("ad")
        return names


# ---------------------------------------------------------------------------
# Script Response
# ---------------------------------------------------------------------------


class RJScriptResponse(BaseModel):
    """Response from the RJ script generation engine."""

    script: str = Field(..., description="Generated radio interlude script text")
    persona_name: str = Field(..., description="Name of the RJ persona used")
    active_blocks: list[str] = Field(
        default_factory=list,
        description="Which context blocks were included in the prompt",
    )
    tokens_used: int = Field(
        default=0,
        description="Total tokens consumed (prompt + completion)",
    )
    mock_mode: bool = Field(
        default=False,
        description="True if the script was generated without calling the LLM",
    )
