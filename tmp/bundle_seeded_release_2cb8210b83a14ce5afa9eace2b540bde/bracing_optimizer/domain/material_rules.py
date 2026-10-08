"""Shared, solver-independent material length and ratio rules.

This module is the common policy boundary for Waler and support solvers. It
must not depend on either solver so both can use the same classification and
ratio calculations without depending on one another.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Literal, Mapping


MaterialCategory = Literal["short", "mid", "long", "out"]
MATERIAL_CATEGORIES = ("short", "mid", "long")


@dataclass(frozen=True)
class MaterialLengthRules:
    """Inclusive/exclusive length boundaries used by material classification."""

    short_min: int = 4000
    short_max: int = 6000
    mid_min: int = 6000
    mid_max: int = 8000
    long_min: int = 8000
    long_max: int = 10000


DEFAULT_MATERIAL_LENGTH_RULES = MaterialLengthRules()


@dataclass(frozen=True)
class MaterialRatioTargets:
    """Normalized targets for the short, mid, and long material categories."""

    short: float
    mid: float
    long: float

    @classmethod
    def normalized(
        cls,
        short: float,
        mid: float,
        long: float,
    ) -> "MaterialRatioTargets":
        values = (float(short), float(mid), float(long))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("材料比例必須是有效數字。")
        if any(value < 0 for value in values):
            raise ValueError("材料比例不可小於 0。")
        total = sum(values)
        if total <= 0:
            raise ValueError("材料比例總和必須大於 0。")
        return cls(*(value / total for value in values))

    @classmethod
    def from_mapping(cls, source: Mapping[str, float]) -> "MaterialRatioTargets":
        """Create targets from values that are already normalized by a caller."""

        return cls(
            short=float(source.get("short", 0.0)),
            mid=float(source.get("mid", 0.0)),
            long=float(source.get("long", 0.0)),
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "short": self.short,
            "mid": self.mid,
            "long": self.long,
        }


@dataclass(frozen=True)
class MaterialRatioAnalysis:
    counts: dict[str, int]
    ratios: dict[str, float]
    targets: dict[str, float]
    ratio_deviation: float
    penalty: float
    classified_total: int
    out_count: int
    weight: float


def classify_length(
    length: int,
    rules: MaterialLengthRules = DEFAULT_MATERIAL_LENGTH_RULES,
) -> MaterialCategory:
    """Classify a material length while preserving established boundaries."""

    if rules.short_min <= length < rules.short_max:
        return "short"
    if rules.mid_min <= length <= rules.mid_max:
        return "mid"
    if rules.long_min < length <= rules.long_max:
        return "long"
    return "out"


def analyze_material_ratios(
    lengths: Iterable[int],
    targets: MaterialRatioTargets,
    *,
    weight: float,
    rules: MaterialLengthRules = DEFAULT_MATERIAL_LENGTH_RULES,
) -> MaterialRatioAnalysis:
    """Return category counts, ratios, deviation, and weighted penalty."""

    counts = {category: 0 for category in MATERIAL_CATEGORIES}
    out_count = 0
    for length in lengths:
        category = classify_length(int(length), rules)
        if category in counts:
            counts[category] += 1
        else:
            out_count += 1

    classified_total = sum(counts.values())
    if classified_total:
        ratios = {
            category: counts[category] / classified_total
            for category in MATERIAL_CATEGORIES
        }
    else:
        ratios = {category: 0.0 for category in MATERIAL_CATEGORIES}

    target_values = targets.as_dict()
    ratio_deviation = sum(
        abs(ratios[category] - target_values[category])
        for category in MATERIAL_CATEGORIES
    )
    numeric_weight = float(weight)
    return MaterialRatioAnalysis(
        counts=counts,
        ratios=ratios,
        targets=target_values,
        ratio_deviation=ratio_deviation,
        penalty=ratio_deviation * numeric_weight,
        classified_total=classified_total,
        out_count=out_count,
        weight=numeric_weight,
    )


__all__ = [
    "DEFAULT_MATERIAL_LENGTH_RULES",
    "MATERIAL_CATEGORIES",
    "MaterialCategory",
    "MaterialLengthRules",
    "MaterialRatioAnalysis",
    "MaterialRatioTargets",
    "analyze_material_ratios",
    "classify_length",
]
