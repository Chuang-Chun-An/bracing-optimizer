"""Extract the reusable jack symbol from the dedicated source DXF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import ezdxf
from ezdxf import bbox
from ezdxf.math import Matrix44


DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "千斤頂專用.dxf"
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "assets" / "dxf" / "jack_symbol.dxf"
)
SOURCE_BLOCK_NAME = "JACK"
ASSET_BLOCK_NAME = "SUPPORT_JACK"
SOURCE_TO_MM_SCALE = 100.0


def _point(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def extract_jack_symbol(source_path: Path, output_path: Path) -> dict:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    source_doc = ezdxf.readfile(source_path)
    source_block = source_doc.blocks.get(SOURCE_BLOCK_NAME)

    target_doc = ezdxf.new("R2018", setup=True)
    target_doc.header["$INSUNITS"] = 4  # millimetres
    target_block = target_doc.blocks.new(
        ASSET_BLOCK_NAME,
        base_point=(0.0, 0.0, 0.0),
    )
    transform = Matrix44.scale(
        SOURCE_TO_MM_SCALE,
        SOURCE_TO_MM_SCALE,
        SOURCE_TO_MM_SCALE,
    )
    for source_entity in source_block:
        entity = source_entity.copy()
        entity.transform(transform)
        # Layer 0 with BYLAYER properties makes the block inherit the layer
        # assigned to its INSERT when exported back to a project drawing.
        entity.dxf.layer = "0"
        entity.dxf.color = 256
        entity.dxf.linetype = "BYLAYER"
        target_block.add_entity(entity)

    # Keep one model-space reference so opening this asset directly displays
    # the symbol.  The application imports only the block definition.
    target_doc.modelspace().add_blockref(
        ASSET_BLOCK_NAME,
        (0.0, 0.0, 0.0),
        dxfattribs={"layer": "0"},
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_doc.saveas(output_path)

    native_extents = bbox.extents(source_block)
    physical_extents = bbox.extents(target_block)
    manifest = {
        "asset_version": 1,
        "source_file": source_path.name,
        "source_block": SOURCE_BLOCK_NAME,
        "block_name": ASSET_BLOCK_NAME,
        "units": "mm",
        "source_to_mm_scale": SOURCE_TO_MM_SCALE,
        "base_point": [0.0, 0.0, 0.0],
        "axis": {
            "start": [0.0, 0.0, 0.0],
            "end": [600.0, 0.0, 0.0],
            "insert_point_role": "start",
        },
        "nominal_length_mm": 600.0,
        "nominal_width_mm": 300.0,
        "entity_count": len(target_block),
        "native_extents": {
            "min": _point(native_extents.extmin),
            "max": _point(native_extents.extmax),
        },
        "physical_extents_mm": {
            "min": _point(physical_extents.extmin),
            "max": _point(physical_extents.extmax),
        },
        "insertion": {
            "scale": 1.0,
            "rotation_degrees": "member axis angle",
            "layer": "component source layer",
            "annotate": False,
        },
    }
    manifest_path = output_path.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = extract_jack_symbol(args.source, args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
