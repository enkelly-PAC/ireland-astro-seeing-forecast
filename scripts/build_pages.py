"""Build the static GitHub Pages frontend."""

from __future__ import annotations

import argparse
import html
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = ROOT / "src" / "meteoblue_seeing" / "assets"
SOURCE_HTML = SOURCE_DIRECTORY / "british_isles_ui.html"
DEFAULT_OUTPUT = ROOT / "docs"

API_META = '<meta name="astro-api-base" content="">'
HOSTING_META = '<meta name="astro-hosting-mode" content="local">'


def build_pages(output_directory: Path, api_base: str = "") -> Path:
    """Build a project-page-safe static frontend."""

    api_base = api_base.strip().rstrip("/")
    if api_base and not api_base.startswith("https://"):
        raise ValueError("The public API base URL must use HTTPS.")

    source_html = SOURCE_HTML.read_text(encoding="utf-8")
    escaped_api_base = html.escape(api_base, quote=True)
    pages_html = source_html.replace(
        API_META,
        f'<meta name="astro-api-base" content="{escaped_api_base}">',
        1,
    ).replace(
        HOSTING_META,
        '<meta name="astro-hosting-mode" content="pages">',
        1,
    )
    if pages_html == source_html:
        raise RuntimeError("The expected hosting metadata was not found.")

    output_directory.mkdir(parents=True, exist_ok=True)
    output_assets = output_directory / "assets"
    output_assets.mkdir(parents=True, exist_ok=True)
    asset_names = {path.name for path in SOURCE_DIRECTORY.glob("*.webp")}
    for stale_asset in output_assets.glob("*.webp"):
        if stale_asset.name not in asset_names:
            stale_asset.unlink()
    for source_asset in SOURCE_DIRECTORY.glob("*.webp"):
        shutil.copy2(source_asset, output_assets / source_asset.name)

    index_path = output_directory / "index.html"
    index_path.write_text(pages_html, encoding="utf-8")
    (output_directory / ".nojekyll").write_text("", encoding="ascii")
    return index_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the GitHub Pages frontend into the docs directory."
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("ASTRO_API_BASE", ""),
        help="HTTPS base URL of the hosted forecast API.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory. Defaults to ./docs.",
    )
    args = parser.parse_args()
    index_path = build_pages(args.output, args.api_base)
    print(f"Built GitHub Pages frontend at {index_path}")
    if not args.api_base:
        print("Live forecast calls remain disabled until --api-base is configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
