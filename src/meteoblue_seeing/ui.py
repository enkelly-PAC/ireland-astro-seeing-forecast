"""Loads the packaged Ireland forecast browser UI HTML asset."""

from __future__ import annotations

from importlib import resources

PLANET_ASSETS = {
    f"planet-{name}.webp"
    for name in (
        "moon",
        "mercury",
        "venus",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
    )
}
PLANET_ASSETS.add("seeing-moon-clavius.webp")


def load_index_html() -> str:
    """Return the self-contained browser UI HTML as text."""

    asset = resources.files("meteoblue_seeing").joinpath(
        "assets", "ireland_ui.html"
    )
    return asset.read_text(encoding="utf-8")


def load_planet_asset(filename: str) -> bytes:
    """Return a bundled, allowlisted astronomy image by its safe filename."""

    if filename not in PLANET_ASSETS:
        raise FileNotFoundError(filename)
    asset = resources.files("meteoblue_seeing").joinpath("assets", filename)
    return asset.read_bytes()
