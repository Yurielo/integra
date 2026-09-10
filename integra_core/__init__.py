"""Core dependency-free Integra contracts."""

from .adapter import AdapterPreconditionError, CapabilitySpec, LocalComponentAdapter
from .benchmark import BenchmarkValidationError, validate_benchmark_record
from .core_alpha import (
    CoreAlphaError,
    CoreAlphaPipeline,
    ReplayStageWorker,
    StageOutput,
    validate_core_alpha_manifest,
)
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
    "CoreAlphaError",
    "CoreAlphaPipeline",
    "CompatibilityError",
    "IdempotencyDecision",
    "IdempotencyLedger",
    "LeaseConflict",
    "LeaseStore",
    "LocalComponentAdapter",
    "RecoveryDecision",
    "ReplayStageWorker",
    "StageOutput",
    "ProgressTracker",
    "ProtocolViolation",
    "derive_imported_id",
    "negotiate_protocol",
    "resume_binding",
    "recovery_decision",
    "resolve_collision",
    "validate_artifact_reference",
    "validate_benchmark_record",
    "validate_core_alpha_manifest",
    "validate_message",
    "validate_resume_binding",
    "validate_resume_token",
]
