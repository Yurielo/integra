"""Core dependency-free Integra contracts."""

from .adapter import AdapterPreconditionError, CapabilitySpec, LocalComponentAdapter
from .benchmark import BenchmarkValidationError, validate_benchmark_record
from .identity import CollisionDecision, derive_imported_id, resolve_collision
from .project_lease import (
    LeaseConflict,
    LeaseStore,
    RecoveryDecision,
    recovery_decision,
)
from .protocol import (
    CompatibilityError,
    IdempotencyDecision,
    IdempotencyLedger,
    ProgressTracker,
    ProtocolViolation,
    negotiate_protocol,
    resume_binding,
    validate_artifact_reference,
    validate_message,
    validate_resume_binding,
    validate_resume_token,
)

__all__ = [
    "AdapterPreconditionError",
    "BenchmarkValidationError",
    "CapabilitySpec",
    "CollisionDecision",
    "CompatibilityError",
    "IdempotencyDecision",
    "IdempotencyLedger",
    "LeaseConflict",
    "LeaseStore",
    "LocalComponentAdapter",
    "RecoveryDecision",
    "ProgressTracker",
    "ProtocolViolation",
    "derive_imported_id",
    "negotiate_protocol",
    "resume_binding",
    "recovery_decision",
    "resolve_collision",
    "validate_artifact_reference",
    "validate_benchmark_record",
    "validate_message",
    "validate_resume_binding",
    "validate_resume_token",
]
