"""
RJ Context Blocks — Composable Data Sources
============================================

Each ContextBlock represents a single, independent piece of context
that can be included (or excluded) from an RJ script prompt.

Usage:
    # Include all blocks:
    songs = SongContextBlock(played=["Song A"], up_next=["Song B"])
    weather = WeatherContextBlock(city="Mumbai", temp="29°C", condition="Humid")

    # Or just the ones you need — pass None / omit the rest.

Every block implements ``render() -> str`` which returns its portion
of the prompt context section.  If a block is ``None`` in the request,
its section is simply skipped.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Persona Block
# ---------------------------------------------------------------------------


class PersonaContextBlock(BaseModel):
    """
    Defines the RJ's on-air identity.

    Used in the *system* portion of the prompt:
        "You are {name} — a radio host with {tone} personality."
    """

    name: str = Field(..., description="RJ's on-air name, e.g. 'Max', 'Zara'")
    tone: str = Field(
        ...,
        description="Personality descriptor, e.g. 'energetic', 'chill', 'sarcastic'",
    )
    catchphrase: str | None = Field(
        default=None,
        description="Optional signature phrase the RJ uses",
    )

    def render_system(self) -> str:
        """Render the system-level persona instruction."""
        base = (
            f"You are {self.name} — a radio host with {self.tone} personality.\n"
            f"Keep scripts under 45 seconds. Be natural, not robotic."
        )
        if self.catchphrase:
            base += f"\nYour signature catchphrase is: \"{self.catchphrase}\""
        return base


# ---------------------------------------------------------------------------
# Song Context Block
# ---------------------------------------------------------------------------


class SongContextBlock(BaseModel):
    """
    Songs that just played and what's coming up next.

    Accepts plain strings (song titles) for simplicity.
    """

    played: list[str] = Field(
        default_factory=list,
        description="Titles of songs that just played",
    )
    up_next: list[str] = Field(
        default_factory=list,
        description="Titles of songs coming up next",
    )

    def render(self) -> str:
        lines: list[str] = []
        if self.played:
            formatted = ", ".join(self.played)
            lines.append(f"- Songs just played: [{formatted}]")
        if self.up_next:
            formatted = ", ".join(self.up_next)
            lines.append(f"- Up next: [{formatted}]")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Weather Context Block
# ---------------------------------------------------------------------------


class WeatherContextBlock(BaseModel):
    """Current weather conditions to weave into the RJ script."""

    city: str
    temp: str = Field(..., description="Temperature string, e.g. '29°C'")
    condition: str = Field(..., description="e.g. 'Partly Cloudy', 'Rainy'")

    def render(self) -> str:
        return f"- Current weather in {self.city}: {self.temp}, {self.condition}"


# ---------------------------------------------------------------------------
# News Context Block
# ---------------------------------------------------------------------------


class NewsContextBlock(BaseModel):
    """Top news headlines for the RJ to optionally reference."""

    headlines: list[str] = Field(
        ...,
        min_length=1,
        description="1–5 news headlines",
    )

    def render(self) -> str:
        formatted = "; ".join(self.headlines)
        return f"- Top news: {formatted}"


# ---------------------------------------------------------------------------
# Ad Context Block
# ---------------------------------------------------------------------------


class AdContextBlock(BaseModel):
    """
    Sponsor / ad script to be woven naturally into the RJ's monologue.

    The ad should be read by the RJ persona naturally — not as a hard break.
    """

    sponsor_script: str = Field(
        ...,
        description="Raw sponsor copy for the RJ to read naturally",
    )

    def render(self) -> str:
        return f"- Ad slot: {self.sponsor_script}"
