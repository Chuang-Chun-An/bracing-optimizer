"""Canonical runtime identity for SupportOptimizer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductIdentity:
    """User-visible identity of one application release."""

    name: str
    version: str
    author: str


PRODUCT_IDENTITY = ProductIdentity(
    name="SupportOptimizer",
    version="3.0.0",
    author="莊竣安（Chuang Chun An）",
)


__all__ = ["PRODUCT_IDENTITY", "ProductIdentity"]
