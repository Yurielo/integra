"""Stable imported identifiers and fail-closed identity collision policy."""

from __future__ import annotations

import enum
import re
import uuid


INTEGRA_ID_NAMESPACE = uuid.UUID("260f6182-1e1d-50da-8a9c-8f6cf214207d")
NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CollisionDecision(str, enum.Enum):
    SAME_IDENTITY = "SAME_IDENTITY"
    REGISTER_ALIAS = "REGISTER_ALIAS"
    HARD_CONFLICT = "HARD_CONFLICT"


def derive_imported_id(
    namespace: str,
    source_component: str,
    native_id: str,
    source_revision_sha256: str,
) -> str:
    """Derive a reproducible ID without using mutable paths or display names."""

    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise ValueError("invalid Integra ID namespace")
    if not source_component.strip() or not native_id.strip():
        raise ValueError("source component and native ID are required")
    if not HASH_PATTERN.fullmatch(source_revision_sha256):
        raise ValueError("source revision must be a lowercase SHA-256")
    seed = "\x1f".join(
        (namespace, source_component.strip(), native_id.strip(), source_revision_sha256)
    )
    return f"urn:integra:{namespace}:{uuid.uuid5(INTEGRA_ID_NAMESPACE, seed)}"


def resolve_collision(
    existing_id: str,
    incoming_id: str,
    existing_identity_sha256: str,
    incoming_identity_sha256: str,
) -> CollisionDecision:
    """Classify a collision; this function never silently selects a writer."""

    for digest in (existing_identity_sha256, incoming_identity_sha256):
        if not HASH_PATTERN.fullmatch(digest):
            raise ValueError("identity hashes must be lowercase SHA-256 values")
    if existing_id == incoming_id:
        if existing_identity_sha256 == incoming_identity_sha256:
            return CollisionDecision.SAME_IDENTITY
        return CollisionDecision.HARD_CONFLICT
    if existing_identity_sha256 == incoming_identity_sha256:
        return CollisionDecision.REGISTER_ALIAS
    return CollisionDecision.HARD_CONFLICT
