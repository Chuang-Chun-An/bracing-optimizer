"""Generate Windows app-icon assets from the approved A1 PNG master.

The source artwork is never redrawn.  This script only crops transparent
padding, scales the intact artwork onto a square canvas, applies restrained
small-size sharpening, and composites the dark-background variant.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "Glossy Blue Ribbon Monogram with Orange Orb.png"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "assets" / "app_icon"
APP_ICON_SIZES = (256, 64, 32, 16)
MASTER_SHA256 = "64115a324cea4107bba3b22084e025e5533e841b66f072b12e8e4489395b6695"
CONTENT_RATIO = 0.88
DARK_BACKGROUND = (15, 23, 42, 255)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_approved_master(source_path: Path) -> Image.Image:
    if _sha256(source_path) != MASTER_SHA256:
        raise ValueError(
            "The source PNG does not match the approved A1 visual master."
        )

    image = Image.open(source_path).convert("RGBA")
    content_bounds = image.getchannel("A").getbbox()
    if content_bounds is None:
        raise ValueError("The approved A1 visual master has no visible pixels.")
    return image.crop(content_bounds)


def _render_transparent_icon(master: Image.Image, size: int) -> Image.Image:
    target_extent = max(1, round(size * CONTENT_RATIO))
    scale = min(target_extent / master.width, target_extent / master.height)
    scaled_size = (
        max(1, round(master.width * scale)),
        max(1, round(master.height * scale)),
    )
    rendered = master.resize(
        scaled_size,
        Image.Resampling.LANCZOS,
        reducing_gap=3.0,
    )

    # At native 32 px and 16 px, restrained sharpening counters downsampling
    # softness without changing the CA curves, their proportions, or the orb.
    if size == 32:
        rendered = rendered.filter(
            ImageFilter.UnsharpMask(radius=0.45, percent=65, threshold=3)
        )
    elif size == 16:
        rendered = rendered.filter(
            ImageFilter.UnsharpMask(radius=0.35, percent=80, threshold=2)
        )

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    position = (
        (size - rendered.width) // 2,
        (size - rendered.height) // 2,
    )
    canvas.alpha_composite(rendered, position)
    return canvas


def _render_dark_icon(transparent_icon: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", transparent_icon.size, DARK_BACKGROUND)
    canvas.alpha_composite(transparent_icon)
    return canvas


def _save_multisize_ico(path: Path, frames: dict[int, Image.Image]) -> None:
    largest = frames[max(APP_ICON_SIZES)]
    appended = [frames[size] for size in APP_ICON_SIZES if size != largest.width]
    largest.save(
        path,
        format="ICO",
        sizes=[(size, size) for size in APP_ICON_SIZES],
        append_images=appended,
    )


def generate_icons(source_path: Path, output_dir: Path) -> None:
    master = _load_approved_master(source_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    transparent_frames: dict[int, Image.Image] = {}
    dark_frames: dict[int, Image.Image] = {}
    for size in APP_ICON_SIZES:
        transparent = _render_transparent_icon(master, size)
        dark = _render_dark_icon(transparent)
        transparent_frames[size] = transparent
        dark_frames[size] = dark
        transparent.save(
            output_dir / f"support_optimizer_transparent_{size}.png",
            format="PNG",
            optimize=True,
        )
        dark.save(
            output_dir / f"support_optimizer_dark_{size}.png",
            format="PNG",
            optimize=True,
        )

    _save_multisize_ico(
        output_dir / "support_optimizer_transparent.ico",
        transparent_frames,
    )
    _save_multisize_ico(
        output_dir / "support_optimizer_dark.ico",
        dark_frames,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    generate_icons(args.source.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
