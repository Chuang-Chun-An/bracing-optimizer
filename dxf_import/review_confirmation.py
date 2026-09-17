"""Pure helpers for persistent, state-sensitive DXF review confirmations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from .models import DXFImportResult, ReviewItem
from .source_exclusion import canonical_source_identity


FORMAL_REVIEW_ROLES = frozenset(
    {"waler", "strut", "brace", "column", "beam", "corner_brace"}
)
_ROLE_COLLECTIONS = {
    "waler": "walers",
    "strut": "struts",
    "brace": "braces",
    "column": "columns",
    "beam": "beams",
    "corner_brace": "corner_braces",
}
_BLOCKING_SEVERITIES = frozenset({"error", "critical"})


def review_confirmations_from_state(
    state: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Read the optional v2 field without rejecting legacy review state."""

    if not isinstance(state, Mapping):
        return {}
    raw = state.get("review_confirmations", {})
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(identity).strip(): str(signature).strip().upper()
        for identity, signature in raw.items()
        if str(identity).strip() and str(signature).strip()
    }


def serialize_review_confirmations(
    confirmations: Mapping[str, str] | None,
) -> dict[str, str]:
    """Return deterministic, JSON-safe confirmation state."""

    if not isinstance(confirmations, Mapping):
        return {}
    return {
        identity: signature
        for identity, signature in sorted(
            (
                (str(identity).strip(), str(signature).strip().upper())
                for identity, signature in confirmations.items()
                if str(identity).strip() and str(signature).strip()
            ),
            key=lambda item: item[0],
        )
    }


def review_confirmation_identity(item: ReviewItem) -> str | None:
    """Return the stable source identity for one formal recognized member."""

    if item.status != "recognized" or item.role not in FORMAL_REVIEW_ROLES:
        return None
    identity = canonical_source_identity(item.role, item.source_handles)
    return identity if item.source_handles and identity else None


def review_item_can_be_confirmed(item: ReviewItem) -> bool:
    """Warning is reviewable; Error/Critical and non-formal rows are not."""

    return bool(
        review_confirmation_identity(item)
        and str(item.highest_severity).strip().lower()
        not in _BLOCKING_SEVERITIES
    )


def _member_for_item(result: DXFImportResult, item: ReviewItem) -> Any | None:
    collection_name = _ROLE_COLLECTIONS.get(item.role)
    if collection_name is None or not item.member_id:
        return None
    identity = review_confirmation_identity(item)
    matches = [
        member
        for member in getattr(result, collection_name)
        if member.id == item.member_id
        and canonical_source_identity(item.role, member.source_handles) == identity
    ]
    return matches[0] if len(matches) == 1 else None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def review_confirmation_signature(
    result: DXFImportResult,
    item: ReviewItem,
) -> str | None:
    """Hash all engineering/review state that one confirmation vouches for."""

    if not review_item_can_be_confirmed(item):
        return None
    member = _member_for_item(result, item)
    if member is None:
        return None
    contact_review = None
    if item.role == "waler":
        contact_review = next(
            (
                asdict(review)
                for review in result.waler_contact_reviews
                if review.waler_id == member.id
            ),
            None,
        )
    problem_data = sorted(
        (asdict(problem) for problem in item.problems),
        key=_canonical_json,
    )
    payload = {
        "role": item.role,
        "member": asdict(member),
        "coordinate_system": asdict(result.coordinate_system),
        "waler_contact_review": contact_review,
        "problems": problem_data,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest().upper()


def review_item_is_confirmed(
    result: DXFImportResult,
    item: ReviewItem,
    confirmations: Mapping[str, str] | None,
) -> bool:
    identity = review_confirmation_identity(item)
    if identity is None or not isinstance(confirmations, Mapping):
        return False
    current = review_confirmation_signature(result, item)
    saved = str(confirmations.get(identity, "") or "").strip().upper()
    return bool(current and saved == current)


def confirm_review_item(
    result: DXFImportResult,
    item: ReviewItem,
    confirmations: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a new map with the current eligible item confirmed."""

    identity = review_confirmation_identity(item)
    signature = review_confirmation_signature(result, item)
    if identity is None or signature is None:
        raise ValueError("此檢核項目目前不能確認。")
    updated = dict(confirmations or {})
    updated[identity] = signature
    return serialize_review_confirmations(updated)


def valid_review_confirmations(
    result: DXFImportResult,
    review_items: Sequence[ReviewItem],
    confirmations: Mapping[str, str] | None,
) -> dict[str, str]:
    """Discard stale, missing, excluded and otherwise ineligible entries."""

    if not isinstance(confirmations, Mapping):
        return {}
    valid: dict[str, str] = {}
    for item in review_items:
        identity = review_confirmation_identity(item)
        if identity is None:
            continue
        if review_item_is_confirmed(result, item, confirmations):
            valid[identity] = str(confirmations[identity]).strip().upper()
    return serialize_review_confirmations(valid)


def unconfirmed_formal_review_items(
    result: DXFImportResult,
    review_items: Sequence[ReviewItem],
    confirmations: Mapping[str, str] | None,
) -> tuple[ReviewItem, ...]:
    """Return only formal recognized components without a valid confirmation.

    Unknown, unresolved and excluded source rows are deliberately outside the
    import-completion reminder.  Blocking severities remain in this projection
    so callers can report them, but the import gate must reject them before any
    optional confirmation flow is entered.
    """

    return tuple(
        item
        for item in review_items
        if item.status == "recognized"
        and item.role in FORMAL_REVIEW_ROLES
        and not review_item_is_confirmed(result, item, confirmations)
    )


__all__ = [
    "FORMAL_REVIEW_ROLES",
    "confirm_review_item",
    "review_confirmation_identity",
    "review_confirmation_signature",
    "review_confirmations_from_state",
    "review_item_can_be_confirmed",
    "review_item_is_confirmed",
    "serialize_review_confirmations",
    "unconfirmed_formal_review_items",
    "valid_review_confirmations",
]
