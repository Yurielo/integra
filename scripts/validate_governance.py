#!/usr/bin/env python3
"""Validate Integra R0 repository truth without third-party dependencies."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.benchmark import (  # noqa: E402
    BenchmarkValidationError,
    sha256_file,
    validate_benchmark_record,
)
from integra_core.core_alpha import ReplayStageWorker  # noqa: E402
from integra_core.real_media import validate_actual_evidence  # noqa: E402
from integra_core.operations_fixtures import run_operations_fixtures  # noqa: E402
from integra_core.migration_fixtures import run_migration_fixtures  # noqa: E402
from integra_core.playlist import (  # noqa: E402
    build_playlist_plan,
    diff_playlist_refresh,
    discover_playlist,
    process_playlist,
)
from integra_core.documents import (  # noqa: E402
    extract_document,
    validate_document_against_source,
    validate_document_record,
)
from integra_core.projects_sources import (  # noqa: E402
    dumps_registry,
    loads_registry,
    new_registry,
    register_document,
    register_local_media,
    register_project,
    register_youtube_playlist,
    register_youtube_video,
    validate_registry,
)
from integra_core.transcript_topic_studio import (  # noqa: E402
    add_quality_finding,
    build_exception_package,
    dumps_studio,
    loads_studio,
    new_studio,
    register_artifact,
    register_topic_set,
    register_transcript,
    register_word_timeline,
    validate_studio,
)
from integra_core.multi_source_alignment import (  # noqa: E402
    add_link as add_alignment_link,
    add_node as add_alignment_node,
    dumps_alignment,
    loads_alignment,
    navigate as navigate_alignment,
    new_alignment,
    validate_alignment,
)
from integra_core.identity import derive_imported_id  # noqa: E402
from integra_core.protocol import content_sha256  # noqa: E402
from scripts.check_agents import load_registry, validate_agent_team  # noqa: E402


STATE_PATH = ROOT / "state" / "integra_state_v1.json"
SCHEMA_PATH = ROOT / "schemas" / "integra_state_v1.schema.json"
BASELINES_PATH = ROOT / "state" / "component_baselines_v1.json"
BASELINES_SCHEMA_PATH = ROOT / "schemas" / "component_baselines_v1.schema.json"
OWNERSHIP_PATH = ROOT / "state" / "data_ownership_v1.json"
OWNERSHIP_SCHEMA_PATH = ROOT / "schemas" / "data_ownership_v1.schema.json"
LEASE_SCHEMA_PATH = ROOT / "schemas" / "project_lease_v1.schema.json"
WORKER_PROTOCOL_PATH = ROOT / "state" / "worker_protocol_v1.json"
WORKER_PROTOCOL_SCHEMA_PATH = ROOT / "schemas" / "worker_protocol_v1.schema.json"
ARTIFACT_REFERENCE_SCHEMA_PATH = ROOT / "schemas" / "artifact_reference_v1.schema.json"
COMPONENT_IDENTITY_SCHEMA_PATH = ROOT / "schemas" / "component_identity_v1.schema.json"
ADAPTER_SPIKE_PATH = ROOT / "state" / "adapter_spike_v1.json"
ADAPTER_SPIKE_SCHEMA_PATH = ROOT / "schemas" / "adapter_spike_v1.schema.json"
ADAPTER_REPORT_SCHEMA_PATH = ROOT / "schemas" / "adapter_probe_report_v1.schema.json"
CAPABILITY_BENCHMARK_PATH = ROOT / "state" / "capability_benchmark_v1.json"
CAPABILITY_BENCHMARK_RAW_PATH = ROOT / "state" / "capability_benchmark_raw_v1.json"
CAPABILITY_BENCHMARK_SCHEMA_PATH = ROOT / "schemas" / "capability_benchmark_v1.schema.json"
AGENT_TEAM_PATH = ROOT / "state" / "agent_team_v1.json"
AGENT_TEAM_SCHEMA_PATH = ROOT / "schemas" / "agent_team_v1.schema.json"
CORE_ALPHA_PATH = ROOT / "state" / "core_alpha_v1.json"
CORE_ALPHA_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "core_alpha_evidence_v1.schema.json"
CORE_ALPHA_MANIFEST_SCHEMA_PATH = ROOT / "schemas" / "core_alpha_manifest_v1.schema.json"
CORE_ALPHA_REAL_PATH = ROOT / "state" / "core_alpha_real_v1.json"
CORE_ALPHA_REAL_SCHEMA_PATH = ROOT / "schemas" / "core_alpha_real_evidence_v1.schema.json"
OPERATIONS_PATH = ROOT / "state" / "operations_and_diagnostics_v1.json"
OPERATIONS_SCHEMA_PATH = ROOT / "schemas" / "operations_evidence_v1.schema.json"
MIGRATION_PATH = ROOT / "state" / "migration_v1.json"
MIGRATION_SCHEMA_PATH = ROOT / "schemas" / "migration_evidence_v1.schema.json"
PLAYLIST_PATH = ROOT / "state" / "playlist_v1.json"
PLAYLIST_SCHEMA_PATH = ROOT / "schemas" / "playlist_evidence_v1.schema.json"
DOCUMENT_PIPELINE_PATH = ROOT / "state" / "document_pipeline_v1.json"
DOCUMENT_PIPELINE_SCHEMA_PATH = ROOT / "schemas" / "document_pipeline_evidence_v1.schema.json"
PROJECTS_SOURCES_PATH = ROOT / "state" / "projects_sources_v1.json"
PROJECTS_SOURCES_SCHEMA_PATH = ROOT / "schemas" / "projects_sources_evidence_v1.schema.json"
PROJECT_SOURCE_REGISTRY_SCHEMA_PATH = ROOT / "schemas" / "project_source_registry_v1.schema.json"
TRANSCRIPT_TOPIC_STUDIO_PATH = ROOT / "state" / "transcript_topic_studio_v1.json"
TRANSCRIPT_TOPIC_STUDIO_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "transcript_topic_studio_evidence_v1.schema.json"
TRANSCRIPT_TOPIC_STUDIO_SCHEMA_PATH = ROOT / "schemas" / "transcript_topic_studio_v1.schema.json"
MULTI_SOURCE_ALIGNMENT_PATH = ROOT / "state" / "multi_source_alignment_v1.json"
MULTI_SOURCE_ALIGNMENT_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "multi_source_alignment_evidence_v1.schema.json"
MULTI_SOURCE_ALIGNMENT_SCHEMA_PATH = ROOT / "schemas" / "multi_source_alignment_v1.schema.json"
KNOWLEDGE_INTEGRATION_PATH = ROOT / "state" / "knowledge_integration_v1.json"
KNOWLEDGE_INTEGRATION_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "knowledge_integration_evidence_v1.schema.json"
KNOWLEDGE_VIEW_SCHEMA_PATH = ROOT / "schemas" / "knowledge_view_v1.schema.json"
MEDIA_INTEGRATION_PATH = ROOT / "state" / "media_integration_v1.json"
MEDIA_INTEGRATION_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "media_integration_evidence_v1.schema.json"
MEDIA_RECIPE_SCHEMA_PATH = ROOT / "schemas" / "media_recipe_v1.schema.json"
MEDIA_DERIVATIVE_SCHEMA_PATH = ROOT / "schemas" / "media_derivative_v1.schema.json"
CROSS_NAVIGATION_PATH = ROOT / "state" / "cross_navigation_v1.json"
CROSS_NAVIGATION_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "cross_navigation_evidence_v1.schema.json"
CROSS_NAVIGATION_SCHEMA_PATH = ROOT / "schemas" / "cross_navigation_v1.schema.json"
OBSIDIAN_EXPORT_PATH = ROOT / "state" / "obsidian_export_v1.json"
OBSIDIAN_EXPORT_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "obsidian_export_evidence_v1.schema.json"
OBSIDIAN_PACKAGE_SCHEMA_PATH = ROOT / "schemas" / "obsidian_package_v1.schema.json"
OBSIDIAN_RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "obsidian_export_receipt_v1.schema.json"
ONEDRIVE_PUBLICATION_PATH = ROOT / "state" / "onedrive_publication_v1.json"
ONEDRIVE_EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "onedrive_publication_evidence_v1.schema.json"
ONEDRIVE_PACKAGE_SCHEMA_PATH = ROOT / "schemas" / "onedrive_package_v1.schema.json"
ONEDRIVE_RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "onedrive_publication_receipt_v1.schema.json"
NATIVE_MACOS_APP_PATH = ROOT / "state" / "native_macos_app_v1.json"
NATIVE_MACOS_APP_SCHEMA_PATH = ROOT / "schemas" / "native_macos_app_evidence_v1.schema.json"
READY_APP_PATH = ROOT / "state" / "ready_app_v1.json"
READY_APP_SCHEMA_PATH = ROOT / "schemas" / "ready_app_v1_evidence.schema.json"
EXPECTED_READY_APP_IMPLEMENTATION = {
    "docs/architecture/READY_APP_V1_PACKAGING.md", "macos/Info.plist",
    "macos/Integra.entitlements", "docs/THIRD_PARTY_NOTICES.md",
    "macos/Resources/bridge.py", "scripts/integra_backup.py",
    "scripts/package_ready_app.sh", "tests/test_ready_app.py",
}
EXPECTED_OBSIDIAN_IMPLEMENTATION = {
    "docs/architecture/OBSIDIAN_EXPORT_V1.md",
    "integra_core/publishing.py",
    "schemas/obsidian_package_v1.schema.json",
    "schemas/obsidian_export_receipt_v1.schema.json",
    "schemas/obsidian_export_evidence_v1.schema.json",
    "tests/test_publishing.py",
}
EXPECTED_ONEDRIVE_IMPLEMENTATION = {
    "docs/architecture/ONEDRIVE_PUBLICATION_V1.md",
    "integra_core/onedrive.py",
    "schemas/onedrive_package_v1.schema.json",
    "schemas/onedrive_publication_receipt_v1.schema.json",
    "schemas/onedrive_publication_evidence_v1.schema.json",
    "tests/test_onedrive.py",
}
EXPECTED_NATIVE_MACOS_APP_IMPLEMENTATION = {
    "docs/architecture/NATIVE_MACOS_APPLICATION_V1.md", "docs/architecture/MACOS_APP_ICON.md",
    "macos/IntegraApp.swift", "macos/Info.plist", "macos/Resources/bridge.py",
    "macos/Resources/Integra.icns",
    "macos/Assets.xcassets/AppIcon.appiconset/Contents.json",
    "macos/Assets.xcassets/AppIcon.appiconset/Integra_app_icon.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_16x16.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_16x16@2x.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_32x32.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_32x32@2x.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_128x128.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_128x128@2x.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_256x256.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_256x256@2x.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_512x512.png",
    "macos/Assets.xcassets/AppIcon.appiconset/icon_512x512@2x.png",
    "macos/Resources/source_first_workflow.json", "macos/Resources/deferred_features.json",
    "scripts/build_macos_app.sh", "scripts/generate_macos_app_icon.sh", "scripts/test_macos_app.sh",
    "schemas/native_macos_app_evidence_v1.schema.json", "tests/macos_icon_probe.swift", "tests/test_macos_app.py",
}
EXPECTED_OPERATIONS_IMPLEMENTATION = {
    "integra_core/operations.py",
    "integra_core/operations_fixtures.py",
    "schemas/operations_job_v1.schema.json",
    "schemas/capability_report_v1.schema.json",
    "schemas/resource_snapshot_v1.schema.json",
    "schemas/resource_reservation_v1.schema.json",
    "schemas/operations_log_event_v1.schema.json",
    "schemas/integrity_report_v1.schema.json",
    "schemas/operations_evidence_v1.schema.json",
    "schemas/model_residency_v1.schema.json",
    "schemas/resource_request_v1.schema.json",
}
EXPECTED_OPERATIONS_FIXTURES = {
    "success",
    "interruption",
    "resume",
    "unsafe_resource",
    "capability_drift",
    "integrity_failure",
    "process_cleanup",
}
EXPECTED_MIGRATION_IMPLEMENTATION = {
    "integra_core/migration.py",
    "integra_core/migration_fixtures.py",
    "schemas/migration_discovery_v1.schema.json",
    "schemas/migration_plan_v1.schema.json",
    "schemas/migration_report_v1.schema.json",
    "schemas/migration_rollback_v1.schema.json",
    "schemas/migration_evidence_v1.schema.json",
}
EXPECTED_MIGRATION_FIXTURES = {
    "tests/fixtures/migration_v1/seminartext_project/seminar.yaml",
    "tests/fixtures/migration_v1/seminartext_project/sources.json",
    "tests/fixtures/migration_v1/seminartext_project/source/video/video_001.mp4",
    "tests/fixtures/migration_v1/seminartext_project/transcript_video_001.txt",
    "tests/fixtures/migration_v1/videotext_project/Support files/manifest.json",
    "tests/fixtures/migration_v1/videotext_project/source.mp4",
    "tests/fixtures/migration_v1/videotext_project/Texts/transcript.txt",
    "tests/fixtures/migration_v1/videotext_project/Video/output.mp4",
}
EXPECTED_PLAYLIST_IMPLEMENTATION = {
    "integra_core/playlist.py",
    "schemas/youtube_playlist_snapshot_v1.schema.json",
    "schemas/youtube_playlist_plan_v1.schema.json",
    "schemas/youtube_playlist_checkpoint_v1.schema.json",
    "schemas/youtube_playlist_refresh_v1.schema.json",
    "schemas/playlist_evidence_v1.schema.json",
}
EXPECTED_PLAYLIST_FIXTURES = {
    "tests/fixtures/playlist_v1/snapshot_initial.json",
    "tests/fixtures/playlist_v1/snapshot_refreshed.json",
}
EXPECTED_DOCUMENT_IMPLEMENTATION = {
    "integra_core/documents.py",
    "schemas/document_extraction_v1.schema.json",
    "schemas/document_pipeline_evidence_v1.schema.json",
}
EXPECTED_DOCUMENT_FIXTURES = {
    "tests/fixtures/document_v1/cases.json",
}
EXPECTED_PROJECTS_SOURCES_IMPLEMENTATION = {
    "docs/architecture/PROJECTS_AND_SOURCES_V1.md",
    "integra_core/projects_sources.py",
    "schemas/project_source_registry_v1.schema.json",
    "schemas/projects_sources_evidence_v1.schema.json",
    "tests/test_projects_sources.py",
}
EXPECTED_TRANSCRIPT_TOPIC_STUDIO_IMPLEMENTATION = {
    "docs/architecture/TRANSCRIPT_AND_TOPIC_STUDIO_V1.md",
    "integra_core/transcript_topic_studio.py",
    "schemas/transcript_topic_studio_v1.schema.json",
    "schemas/transcript_topic_studio_evidence_v1.schema.json",
    "tests/test_transcript_topic_studio.py",
}
EXPECTED_MULTI_SOURCE_ALIGNMENT_IMPLEMENTATION = {
    "docs/architecture/MULTI_SOURCE_ALIGNMENT_V1.md",
    "integra_core/multi_source_alignment.py",
    "schemas/multi_source_alignment_v1.schema.json",
    "schemas/multi_source_alignment_evidence_v1.schema.json",
    "tests/test_multi_source_alignment.py",
}
EXPECTED_KNOWLEDGE_IMPLEMENTATION = {
    "docs/architecture/KNOWLEDGE_INTEGRATION_V1.md",
    "integra_core/_vendor/__init__.py",
    "integra_core/_vendor/seminartext_a94936c/__init__.py",
    "integra_core/_vendor/seminartext_a94936c/canonical_evidence_v1.schema.json",
    "integra_core/_vendor/seminartext_a94936c/canonical_knowledge_lifecycle_v1.json",
    "integra_core/_vendor/seminartext_a94936c/canonical_knowledge_v1.schema.json",
    "integra_core/_vendor/seminartext_a94936c/validate_canonical_evidence_v1.py",
    "integra_core/_vendor/seminartext_a94936c/validate_canonical_knowledge_v1.py",
    "integra_core/knowledge.py",
    "schemas/knowledge_view_v1.schema.json",
    "tests/test_knowledge.py",
}
EXPECTED_MEDIA_IMPLEMENTATION = {
    "docs/architecture/MEDIA_INTEGRATION_V1.md",
    "integra_core/media.py",
    "schemas/media_derivative_v1.schema.json",
    "schemas/media_capability_report_v1.schema.json",
    "schemas/media_qa_report_v1.schema.json",
    "schemas/media_integration_evidence_v1.schema.json",
    "schemas/media_recipe_v1.schema.json",
    "tests/fixtures/media_v1/ffprobe_fixture.py",
    "tests/test_media.py",
}
EXPECTED_CROSS_NAVIGATION_IMPLEMENTATION = {
    "docs/architecture/CROSS_NAVIGATION_V1.md",
    "integra_core/cross_navigation.py",
    "schemas/cross_navigation_v1.schema.json",
    "schemas/cross_navigation_evidence_v1.schema.json",
    "tests/fixtures/cross_navigation_v1/ffprobe_fixture.py",
    "tests/test_cross_navigation.py",
}
EXPECTED_CORE_ALPHA_REAL_SHA256 = "7233cd2985d65d8616e217385b53935c671dbda69a686849a9864cba4565d47c"
EXPECTED_CORE_ALPHA_REAL_IMPLEMENTATION = {
    "integra_core/core_alpha.py",
    "integra_core/real_contracts.py",
    "integra_core/real_media.py",
    "scripts/run_core_alpha_real.py",
    "workers/core_alpha_real_worker.py",
    "workers/seminartext_topics_worker.py",
    "workers/videotext_transcript_worker.swift",
    "workers/videotext_clip_worker.swift",
    "scripts/certify_core_alpha_real.py",
    "schemas/core_alpha_real_evidence_v1.schema.json",
    "schemas/videotext_transcript_v1.schema.json",
    "schemas/seminartext_topic_drafts_v1.schema.json",
    "schemas/seminartext_exception_review_v1.schema.json",
    "schemas/seminartext_knowledge_candidate_v1.schema.json",
    "schemas/videotext_media_clip_v1.contract.json",
}

REQUIRED_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    ".codex/agents/README.md",
    "DEVELOPMENT_WORKFLOW.md",
    "docs/AUTONOMOUS_EXECUTION_POLICY.md",
    "docs/architecture/AGENT_TEAM_OPERATING_MODEL.md",
    "docs/INTEGRA_PLAN.md",
    "docs/PRODUCT_DEFINITION.md",
    "docs/ROADMAP.md",
    "docs/RISK_REGISTER.md",
    "docs/ACCEPTANCE_CRITERIA.md",
    "docs/architecture/INTEGRA_ARCHITECTURE.md",
    "docs/baselines/R1_BASELINE_CERTIFICATION.md",
    "schemas/component_baselines_v1.schema.json",
    "state/component_baselines_v1.json",
    "docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md",
    "schemas/data_ownership_v1.schema.json",
    "schemas/project_lease_v1.schema.json",
    "state/data_ownership_v1.json",
    "docs/architecture/WORKER_PROTOCOL_V1.md",
    "schemas/worker_protocol_v1.schema.json",
    "schemas/artifact_reference_v1.schema.json",
    "schemas/component_identity_v1.schema.json",
    "state/worker_protocol_v1.json",
    "docs/baselines/R4_ADAPTER_SPIKE_CERTIFICATION.md",
    "schemas/adapter_spike_v1.schema.json",
    "schemas/adapter_probe_report_v1.schema.json",
    "state/adapter_spike_v1.json",
    "integra_core/adapter.py",
    "scripts/run_adapter_spike.py",
    "docs/baselines/R5_CAPABILITY_BENCHMARK_CERTIFICATION.md",
    "schemas/capability_benchmark_v1.schema.json",
    "state/capability_benchmark_v1.json",
    "state/capability_benchmark_raw_v1.json",
    "integra_core/benchmark.py",
    "scripts/run_capability_benchmark.py",
    "scripts/compile_capability_benchmark.py",
    "schemas/agent_team_v1.schema.json",
    "state/agent_team_v1.json",
    "scripts/check_agents.py",
    "docs/baselines/R6_CORE_ALPHA_CERTIFICATION.md",
    "schemas/core_alpha_evidence_v1.schema.json",
    "schemas/core_alpha_manifest_v1.schema.json",
    "state/core_alpha_v1.json",
    "integra_core/core_alpha.py",
    "scripts/run_core_alpha.py",
    "tests/fixtures/core_alpha_v1/worker_outputs.json",
    "schemas/core_alpha_real_evidence_v1.schema.json",
    "schemas/videotext_transcript_v1.schema.json",
    "schemas/seminartext_topic_drafts_v1.schema.json",
    "schemas/seminartext_exception_review_v1.schema.json",
    "schemas/seminartext_knowledge_candidate_v1.schema.json",
    "schemas/videotext_media_clip_v1.contract.json",
    "state/core_alpha_real_v1.json",
    "integra_core/real_contracts.py",
    "integra_core/real_media.py",
    "scripts/run_core_alpha_real.py",
    "workers/core_alpha_real_worker.py",
    "workers/seminartext_topics_worker.py",
    "workers/videotext_transcript_worker.swift",
    "workers/videotext_clip_worker.swift",
    "docs/architecture/OPERATIONS_AND_DIAGNOSTICS_V1.md",
    "schemas/operations_evidence_v1.schema.json",
    "schemas/operations_job_v1.schema.json",
    "schemas/capability_report_v1.schema.json",
    "schemas/resource_snapshot_v1.schema.json",
    "schemas/resource_reservation_v1.schema.json",
    "schemas/operations_log_event_v1.schema.json",
    "schemas/integrity_report_v1.schema.json",
    "schemas/model_residency_v1.schema.json",
    "schemas/resource_request_v1.schema.json",
    "state/operations_and_diagnostics_v1.json",
    "integra_core/operations.py",
    "integra_core/operations_fixtures.py",
    "docs/architecture/COPY_ON_WRITE_MIGRATION_V1.md",
    "schemas/migration_discovery_v1.schema.json",
    "schemas/migration_plan_v1.schema.json",
    "schemas/migration_report_v1.schema.json",
    "schemas/migration_rollback_v1.schema.json",
    "schemas/migration_evidence_v1.schema.json",
    "state/migration_v1.json",
    "integra_core/migration.py",
    "integra_core/migration_fixtures.py",
    "docs/architecture/YOUTUBE_PLAYLIST_PIPELINE_V1.md",
    "schemas/youtube_playlist_snapshot_v1.schema.json",
    "schemas/youtube_playlist_plan_v1.schema.json",
    "schemas/youtube_playlist_checkpoint_v1.schema.json",
    "schemas/youtube_playlist_refresh_v1.schema.json",
    "schemas/playlist_evidence_v1.schema.json",
    "state/playlist_v1.json",
    "integra_core/playlist.py",
    "docs/architecture/DOCUMENT_AND_OCR_PIPELINE_V1.md",
    "schemas/document_extraction_v1.schema.json",
    "schemas/document_pipeline_evidence_v1.schema.json",
    "state/document_pipeline_v1.json",
    "integra_core/documents.py",
    "tests/fixtures/document_v1/cases.json",
    "docs/architecture/PROJECTS_AND_SOURCES_V1.md",
    "schemas/project_source_registry_v1.schema.json",
    "schemas/projects_sources_evidence_v1.schema.json",
    "state/projects_sources_v1.json",
    "integra_core/projects_sources.py",
    "docs/architecture/TRANSCRIPT_AND_TOPIC_STUDIO_V1.md",
    "schemas/transcript_topic_studio_v1.schema.json",
    "schemas/transcript_topic_studio_evidence_v1.schema.json",
    "state/transcript_topic_studio_v1.json",
    "integra_core/transcript_topic_studio.py",
    "docs/architecture/MULTI_SOURCE_ALIGNMENT_V1.md",
    "schemas/multi_source_alignment_v1.schema.json",
    "schemas/multi_source_alignment_evidence_v1.schema.json",
    "state/multi_source_alignment_v1.json",
    "integra_core/multi_source_alignment.py",
    "tests/test_multi_source_alignment.py",
    "docs/architecture/KNOWLEDGE_INTEGRATION_V1.md",
    "schemas/knowledge_view_v1.schema.json",
    "schemas/knowledge_integration_evidence_v1.schema.json",
    "state/knowledge_integration_v1.json",
    "integra_core/knowledge.py",
    "tests/test_knowledge.py",
    "docs/architecture/MEDIA_INTEGRATION_V1.md",
    "schemas/media_recipe_v1.schema.json",
    "schemas/media_derivative_v1.schema.json",
    "schemas/media_capability_report_v1.schema.json",
    "schemas/media_qa_report_v1.schema.json",
    "schemas/media_integration_evidence_v1.schema.json",
    "state/media_integration_v1.json",
    "integra_core/media.py",
    "tests/test_media.py",
    "docs/architecture/CROSS_NAVIGATION_V1.md",
    "schemas/cross_navigation_v1.schema.json",
    "schemas/cross_navigation_evidence_v1.schema.json",
    "state/cross_navigation_v1.json",
    "integra_core/cross_navigation.py",
    "tests/fixtures/cross_navigation_v1/ffprobe_fixture.py",
    "tests/test_cross_navigation.py",
)

READY_APP_REQUIRED_MODULES = {
    "projects_and_sources",
    "transcript_and_topic_studio",
    "knowledge_studio",
    "media_studio",
    "cross_navigation",
    "operations_and_diagnostics",
    "compatibility_and_migration",
    "obsidian_export",
    "onedrive_publication",
    "native_macos_application",
}

DEFERRED_MODULES = {
    "publishing_hub_additional_formats",
    "marketing_studio_v1",
    "learning_studio_v1",
    "knowledge_assistant_v1",
}

DEFERRED_SOCIAL_PLATFORMS = {
    "facebook_pages",
    "instagram",
    "threads",
    "youtube",
    "telegram",
    "whatsapp_business",
    "tiktok",
}

REQUIRED_DEFERRED_CAPABILITIES = {
    "general_docx_pdf_srt_audio_video_export",
    "live_youtube_api_and_media_download",
    "local_ocr_engine_and_model_execution",
    "automatic_multi_source_matching",
    "representative_full_media_studio_execution",
    "bidirectional_obsidian_sync",
    "microsoft_graph_onedrive",
    "unattended_external_publication",
    "public_distribution_signing_notarization_and_update_publication",
    "source_repository_consolidation",
    "source_application_retirement",
    "mobile_web_windows_editions",
    "multi_user_server_edition",
    "personalized_adaptive_learning",
    "unrestricted_rag",
    "full_autonomous_semantic_authoring",
}

GATED_NOT_AUTHORIZED = {
    "protected_or_private_data",
    "credentials_or_accounts",
    "live_external_writes",
    "authoritative_semantic_acceptance",
    "concept_identity_merging",
    "destructive_migration",
    "signing_identity",
    "release_authority",
}

READY_APP_PRIORITY_ORDER = [
    "R9C",
    "R10",
    "ONEDRIVE_PUBLICATION_V1",
    "R12",
    "R13",
    "USER_MEDIA_WORKFLOW_V1",
    "SOURCE_FIRST_UI_V1",
    "R14",
]

DEFERRED_ROADMAP_IDS = {
    "DEFERRED_CAPABILITIES_V1",
    "R11",
    "LEARNING_V1",
    "ASSISTANT_V1",
    "SOCIAL_FOUNDATION",
    "SOCIAL_FACEBOOK",
    "SOCIAL_INSTAGRAM",
    "SOCIAL_THREADS",
    "SOCIAL_YOUTUBE",
    "SOCIAL_TELEGRAM",
    "SOCIAL_WHATSAPP",
    "SOCIAL_TIKTOK",
    "R15",
}

ACTIVE_CHAIN_ROADMAP_IDS = {
    "R10",
    "ONEDRIVE_PUBLICATION_V1",
    "R12",
    "R13",
    "USER_MEDIA_WORKFLOW_V1",
    "SOURCE_FIRST_UI_V1",
    "R14",
}

EXPECTED_ROADMAP_ISSUES = {
    "R0": 2,
    "R1": 3,
    "R2": 4,
    "R3": 5,
    "R4": 6,
    "R5": 7,
    "R6": 8,
    "OPERATIONS_AND_DIAGNOSTICS_V1": 46,
    "R7": 9,
    "R8A": 10,
    "R8B": 11,
    "PROJECTS_AND_SOURCES_V1": 47,
    "TRANSCRIPT_AND_TOPIC_STUDIO_V1": 48,
    "R8C": 12,
    "R9A": 13,
    "R9B": 14,
    "R9C": 15,
    "R10": 16,
    "ONEDRIVE_PUBLICATION_V1": 63,
    "R12": 28,
    "R13": 29,
    "USER_MEDIA_WORKFLOW_V1": 72,
    "SOURCE_FIRST_UI_V1": 76,
    "R14": 30,
    "DEFERRED_CAPABILITIES_V1": 64,
    "R11": 17,
    "LEARNING_V1": 18,
    "ASSISTANT_V1": 19,
    "SOCIAL_FOUNDATION": 20,
    "SOCIAL_FACEBOOK": 21,
    "SOCIAL_INSTAGRAM": 22,
    "SOCIAL_THREADS": 23,
    "SOCIAL_YOUTUBE": 24,
    "SOCIAL_TELEGRAM": 25,
    "SOCIAL_WHATSAPP": 26,
    "SOCIAL_TIKTOK": 27,
    "R15": 31,
}

REQUIRED_MODULE_ROADMAP_IDS = {
    "projects_and_sources": {"PROJECTS_AND_SOURCES_V1"},
    "transcript_and_topic_studio": {"TRANSCRIPT_AND_TOPIC_STUDIO_V1"},
    "knowledge_studio": {"R9A"},
    "media_studio": {"R9B"},
    "cross_navigation": {"R9C"},
    "operations_and_diagnostics": {"OPERATIONS_AND_DIAGNOSTICS_V1"},
    "compatibility_and_migration": {"R7"},
    "obsidian_export": {"R10"},
    "onedrive_publication": {"ONEDRIVE_PUBLICATION_V1"},
    "native_macos_application": {"R12"},
}

REQUIRED_ROADMAP_DEPENDENCIES = {
    "OPERATIONS_AND_DIAGNOSTICS_V1": {"R6"},
    "R7": {"R6", "OPERATIONS_AND_DIAGNOSTICS_V1"},
    "R8A": {"R3", "R6", "OPERATIONS_AND_DIAGNOSTICS_V1"},
    "R8B": {"R3", "R6", "OPERATIONS_AND_DIAGNOSTICS_V1"},
    "PROJECTS_AND_SOURCES_V1": {"R6", "R7", "R8A", "R8B"},
    "TRANSCRIPT_AND_TOPIC_STUDIO_V1": {"R6", "PROJECTS_AND_SOURCES_V1"},
    "R8C": {
        "R8A",
        "R8B",
        "PROJECTS_AND_SOURCES_V1",
        "TRANSCRIPT_AND_TOPIC_STUDIO_V1",
    },
    "R9A": {"R6", "R8C", "TRANSCRIPT_AND_TOPIC_STUDIO_V1"},
    "R9B": {"R5", "R6", "OPERATIONS_AND_DIAGNOSTICS_V1"},
    "R9C": {"R8C", "R9A", "R9B"},
    "R10": {"R9C"},
    "ONEDRIVE_PUBLICATION_V1": {"R10"},
    "R12": {"ONEDRIVE_PUBLICATION_V1"},
    "R13": {"R12"},
    "USER_MEDIA_WORKFLOW_V1": {"R13"},
    "SOURCE_FIRST_UI_V1": {"USER_MEDIA_WORKFLOW_V1"},
    "R14": {"SOURCE_FIRST_UI_V1"},
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_state(state: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_DOCUMENTS:
        if not (root / relative).is_file():
            errors.append(f"missing required document: {relative}")

    if state.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if state.get("product") != "Integra":
        errors.append("product must be Integra")
    if state.get("standalone_products_preserved") is not True:
        errors.append("standalone_products_preserved must be true")
    if state.get("component_baseline_manifest") != "state/component_baselines_v1.json":
        errors.append("component_baseline_manifest must pin the R1 manifest")
    if state.get("data_ownership_contract") != "state/data_ownership_v1.json":
        errors.append("data_ownership_contract must pin the R2 ownership matrix")
    if state.get("project_lease_schema") != "schemas/project_lease_v1.schema.json":
        errors.append("project_lease_schema must pin the R2 lease contract")
    if state.get("worker_protocol_contract") != "state/worker_protocol_v1.json":
        errors.append("worker_protocol_contract must pin the R3 protocol registry")
    if state.get("adapter_spike_evidence") != "state/adapter_spike_v1.json":
        errors.append("adapter_spike_evidence must pin the R4 acceptance record")
    if state.get("capability_benchmark_evidence") != "state/capability_benchmark_v1.json":
        errors.append("capability_benchmark_evidence must pin the R5 acceptance record")
    if state.get("agent_team_contract") != "state/agent_team_v1.json":
        errors.append("agent_team_contract must pin the governed agent registry")
    if state.get("core_alpha_evidence") != "state/core_alpha_v1.json":
        errors.append("core_alpha_evidence must pin the R6 checkpoint record")
    if state.get("core_alpha_real_evidence") != "state/core_alpha_real_v1.json":
        errors.append("core_alpha_real_evidence must pin the R6 actual execution record")
    if state.get("operations_and_diagnostics_evidence") != "state/operations_and_diagnostics_v1.json":
        errors.append("operations_and_diagnostics_evidence must pin Issue #46 acceptance")
    if state.get("migration_evidence") != "state/migration_v1.json":
        errors.append("migration_evidence must pin R7 acceptance")
    if state.get("playlist_evidence") != "state/playlist_v1.json":
        errors.append("playlist_evidence must pin R8A acceptance")
    if state.get("document_pipeline_evidence") != "state/document_pipeline_v1.json":
        errors.append("document_pipeline_evidence must pin R8B acceptance")
    if state.get("projects_sources_evidence") != "state/projects_sources_v1.json":
        errors.append("projects_sources_evidence must pin Issue #47 acceptance")
    if state.get("transcript_topic_studio_evidence") != "state/transcript_topic_studio_v1.json":
        errors.append("transcript_topic_studio_evidence must pin Issue #48 acceptance")
    if state.get("multi_source_alignment_evidence") != "state/multi_source_alignment_v1.json":
        errors.append("multi_source_alignment_evidence must pin R8C acceptance")
    if state.get("knowledge_integration_evidence") != "state/knowledge_integration_v1.json":
        errors.append("knowledge_integration_evidence must pin R9A acceptance")
    if state.get("media_integration_evidence") != "state/media_integration_v1.json":
        errors.append("media_integration_evidence must pin R9B acceptance")
    if state.get("cross_navigation_evidence") != "state/cross_navigation_v1.json":
        errors.append("cross_navigation_evidence must pin R9C acceptance")
    if state.get("obsidian_export_evidence") != "state/obsidian_export_v1.json":
        errors.append("obsidian_export_evidence must pin R10 acceptance")
    if state.get("onedrive_publication_evidence") != "state/onedrive_publication_v1.json":
        errors.append("onedrive_publication_evidence must pin Issue #63 acceptance")
    if state.get("native_macos_app_evidence") != "state/native_macos_app_v1.json":
        errors.append("native_macos_app_evidence must pin R12 acceptance")
    if state.get("ready_app_evidence") != "state/ready_app_v1.json":
        errors.append("ready_app_evidence must pin R13 acceptance")

    execution_policy = state.get("execution_policy", {})
    expected_policy = {
        "safe_roadmap_implementation": "STANDING_AUTHORITY_AFTER_DEPENDENCIES",
        "merge": "AUTO_AFTER_FAIL_CLOSED_GATES",
        "runtime_reconciliation": "AUTO_GOVERNED_AFTER_FAIL_CLOSED_GATES",
        "release": "EXPLICIT_AUTHORITY_REQUIRED",
        "live_external_actions": "EXPLICIT_AUTHORITY_REQUIRED",
        "protected_data": "EXPLICIT_AUTHORITY_REQUIRED",
        "semantic_acceptance": "EXPLICIT_HUMAN_DECISION_REQUIRED",
        "destructive_migration": "EXPLICIT_AUTHORITY_REQUIRED",
        "source_repository_changes": "EXPLICIT_SCOPE_REQUIRED",
    }
    if execution_policy != expected_policy:
        errors.append("execution_policy does not match the authorized boundary")

    delivery_target = state.get("delivery_target", {})
    if delivery_target != {
        "id": "READY_APP_V1",
        "authorization_issue": 62,
        "priority_order": READY_APP_PRIORITY_ORDER,
        "deferred_status": "DEFERRED_TO_LATER_WORK",
        "acceptance_gate": "R14",
    }:
        errors.append("delivery_target does not match the authorized READY_APP_V1 chain")

    scope = state.get("release_scope", {})
    if scope.get("target") != "READY_APP_V1":
        errors.append("release_scope target must be READY_APP_V1")
    modules = set(scope.get("required_modules", []))
    if modules != READY_APP_REQUIRED_MODULES:
        errors.append("required modules differ from READY_APP_V1")
    deferred_modules = set(scope.get("deferred_modules", []))
    if deferred_modules != DEFERRED_MODULES:
        errors.append("deferred modules differ from the Product Owner registry")
    deferred_platforms = set(scope.get("deferred_social_platforms", []))
    if deferred_platforms != DEFERRED_SOCIAL_PLATFORMS:
        errors.append("deferred social platforms differ from the Product Owner registry")
    deferred_capabilities = set(scope.get("deferred", []))
    if deferred_capabilities != REQUIRED_DEFERRED_CAPABILITIES:
        errors.append("deferred capabilities differ from the Product Owner registry")
    gated_not_authorized = set(scope.get("gated_not_authorized", []))
    if gated_not_authorized != GATED_NOT_AUTHORIZED:
        errors.append("retained authorization gates differ from READY_APP_V1")

    roadmap = state.get("roadmap")
    if not isinstance(roadmap, list):
        return errors + ["roadmap must be a list"]

    ids = [entry.get("id") for entry in roadmap]
    issues = [entry.get("issue") for entry in roadmap]
    if len(ids) != len(set(ids)):
        errors.append("roadmap IDs must be unique")
    if len(issues) != len(set(issues)):
        errors.append("roadmap issue numbers must be unique")
    if set(issues) != set(EXPECTED_ROADMAP_ISSUES.values()):
        errors.append("roadmap issue inventory differs from the governed mapping")

    expected_ids = set(EXPECTED_ROADMAP_ISSUES)
    missing_ids = expected_ids - set(ids)
    extra_ids = set(ids) - expected_ids
    if missing_ids:
        errors.append(f"missing roadmap IDs: {sorted(missing_ids)}")
    if extra_ids:
        errors.append(f"unexpected roadmap IDs: {sorted(extra_ids)}")

    entries_by_id = {entry.get("id"): entry for entry in roadmap}
    for entry_id, expected_issue in EXPECTED_ROADMAP_ISSUES.items():
        actual_issue = entries_by_id.get(entry_id, {}).get("issue")
        if actual_issue != expected_issue:
            errors.append(
                f"{entry_id} must map to GitHub Issue #{expected_issue}"
            )

    for module, required_ids in REQUIRED_MODULE_ROADMAP_IDS.items():
        if module in modules and not required_ids.issubset(set(ids)):
            errors.append(
                f"required module {module} lacks executable roadmap coverage"
            )

    positions = {entry.get("id"): index for index, entry in enumerate(roadmap)}
    statuses = {entry.get("id"): entry.get("status") for entry in roadmap}
    for accepted_id in ("R0", "R1", "R2", "R3", "R4", "R5"):
        if statuses.get(accepted_id) != "ACCEPTED":
            errors.append(f"{accepted_id} must remain ACCEPTED")
    if statuses.get("R6") != "ACCEPTED":
        errors.append("R6 must be ACCEPTED after replay and pinned real-media evidence pass")
    if statuses.get("OPERATIONS_AND_DIAGNOSTICS_V1") != "ACCEPTED":
        errors.append("OPERATIONS_AND_DIAGNOSTICS_V1 must be ACCEPTED with pinned evidence")
    if statuses.get("R7") != "ACCEPTED":
        errors.append("R7 must be ACCEPTED with copy-on-write migration evidence")
    if statuses.get("R8A") != "ACCEPTED":
        errors.append("R8A must be ACCEPTED with YouTube playlist evidence")
    if statuses.get("R8B") != "ACCEPTED":
        errors.append("R8B must be ACCEPTED with document pipeline evidence")
    if statuses.get("PROJECTS_AND_SOURCES_V1") != "ACCEPTED":
        errors.append("PROJECTS_AND_SOURCES_V1 must be ACCEPTED with registry evidence")
    if statuses.get("TRANSCRIPT_AND_TOPIC_STUDIO_V1") != "ACCEPTED":
        errors.append("TRANSCRIPT_AND_TOPIC_STUDIO_V1 must be ACCEPTED with studio evidence")
    if statuses.get("R8C") != "ACCEPTED":
        errors.append("R8C must be ACCEPTED with multi-source alignment evidence")
    if statuses.get("R9A") != "ACCEPTED":
        errors.append("R9A must be ACCEPTED with knowledge integration evidence")
    if statuses.get("R9B") != "ACCEPTED":
        errors.append("R9B must be ACCEPTED with media integration evidence")
    if statuses.get("R9C") != "ACCEPTED":
        errors.append("R9C must be ACCEPTED with cross-navigation evidence")
    if statuses.get("R10") != "ACCEPTED":
        errors.append("R10 must be ACCEPTED with managed Obsidian export evidence")
    if statuses.get("ONEDRIVE_PUBLICATION_V1") != "ACCEPTED":
        errors.append("ONEDRIVE_PUBLICATION_V1 must be ACCEPTED with filesystem publication evidence")
    if statuses.get("R12") != "ACCEPTED":
        errors.append("R12 must be ACCEPTED with native macOS application evidence")
    if statuses.get("R13") != "ACCEPTED":
        errors.append("R13 must be ACCEPTED with READY_APP_V1 package evidence")
    if statuses.get("USER_MEDIA_WORKFLOW_V1") != "ACCEPTED":
        errors.append("USER_MEDIA_WORKFLOW_V1 must be ACCEPTED before R14")
    if statuses.get("SOURCE_FIRST_UI_V1") != "ACCEPTED":
        errors.append("SOURCE_FIRST_UI_V1 must be ACCEPTED before R14")
    if statuses.get("R14") != "ACCEPTED":
        errors.append("R14 must be ACCEPTED after the Product Owner decision")
    for deferred_id in DEFERRED_ROADMAP_IDS:
        if statuses.get(deferred_id) != "DEFERRED_TO_LATER_WORK":
            errors.append(f"{deferred_id} must remain DEFERRED_TO_LATER_WORK")
    for entry in roadmap:
        entry_id = entry.get("id")
        for dependency in entry.get("depends_on", []):
            if dependency not in positions:
                errors.append(f"{entry_id} has unknown dependency {dependency}")
            elif positions[dependency] >= positions.get(entry_id, -1):
                errors.append(f"{entry_id} dependency {dependency} must appear earlier")

    for entry_id, required_dependencies in REQUIRED_ROADMAP_DEPENDENCIES.items():
        actual_dependencies = set(entries_by_id.get(entry_id, {}).get("depends_on", []))
        if entry_id in ACTIVE_CHAIN_ROADMAP_IDS:
            if actual_dependencies != required_dependencies:
                errors.append(
                    f"{entry_id} dependencies differ from the exact READY_APP_V1 chain: "
                    f"expected {sorted(required_dependencies)}, "
                    f"got {sorted(actual_dependencies)}"
                )
            continue
        missing_dependencies = required_dependencies - actual_dependencies
        if missing_dependencies:
            errors.append(
                f"{entry_id} lacks required dependencies: "
                f"{sorted(missing_dependencies)}"
            )

    for entry_id in ACTIVE_CHAIN_ROADMAP_IDS:
        deferred_dependencies = set(
            entries_by_id.get(entry_id, {}).get("depends_on", [])
        ) & DEFERRED_ROADMAP_IDS
        if deferred_dependencies:
            errors.append(
                f"{entry_id} must not depend on deferred roadmap items: "
                f"{sorted(deferred_dependencies)}"
            )

    def depends_on_r14(entry_id: str, seen: set[str] | None = None) -> bool:
        if entry_id == "R14":
            return True
        seen = set() if seen is None else seen
        if entry_id in seen:
            return False
        seen.add(entry_id)
        return any(
            depends_on_r14(dependency, seen.copy())
            for dependency in entries_by_id.get(entry_id, {}).get("depends_on", [])
        )

    r14_position = positions.get("R14", len(roadmap))
    for deferred_id in DEFERRED_ROADMAP_IDS:
        if positions.get(deferred_id, -1) <= r14_position:
            errors.append(f"{deferred_id} must appear after R14")
        if not depends_on_r14(deferred_id):
            errors.append(f"{deferred_id} must be dependency-blocked until after R14")

    if not state.get("stop_conditions") or len(state["stop_conditions"]) < 8:
        errors.append("at least eight fail-closed stop conditions are required")

    return errors


def validate_component_baselines(manifest: dict) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0":
        errors.append("component baseline schema_version must be 1.0")
    policy = manifest.get("integration_policy", {})
    if policy != {
        "source_repositories": "READ_ONLY",
        "dependency_mode": "PINNED_COMMIT_AND_VERSIONED_CONTRACT",
        "unmerged_work_allowed": False,
    }:
        errors.append("component integration policy must remain read-only and pinned")
    components = manifest.get("components", [])
    if {component.get("id") for component in components} != {"seminartext", "videotext"}:
        errors.append("component baselines must contain SeminarText and VideoText exactly")
    for component in components:
        component_id = component.get("id", "unknown")
        if component.get("default_branch") != "main":
            errors.append(f"{component_id} baseline must use main")
        for field in ("commit_sha", "tree_sha"):
            value = component.get(field, "")
            if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
                errors.append(f"{component_id} has invalid {field}")
        if component.get("source_tree_clean") is not True:
            errors.append(f"{component_id} source tree must be clean")
        if not component.get("supported_contracts"):
            errors.append(f"{component_id} must pin at least one supported contract")
        for contract in component.get("supported_contracts", []):
            digest = contract.get("sha256", "")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                errors.append(f"{component_id} contract {contract.get('id')} has invalid sha256")
    acceptance = manifest.get("r1_acceptance", {})
    if acceptance.get("manifest_reproducible") is not True:
        errors.append("R1 manifest must be reproducible")
    if acceptance.get("unmerged_work_is_dependency") is not False:
        errors.append("unmerged work must not be an R1 dependency")
    if acceptance.get("status") == "PASS" and not acceptance.get("supported_standalone_gates_pass"):
        errors.append("R1 cannot PASS unless supported standalone gates pass")
    if acceptance.get("release_promotion_performed") is not False:
        errors.append("R1 must not promote a source application release")
    return errors


def validate_data_ownership(contract: dict) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != "1.0":
        errors.append("data ownership schema_version must be 1.0")
    id_policy = contract.get("id_policy", {})
    if id_policy.get("derivation") != "UUIDV5_COMPONENT_NATIVE_ID_SOURCE_REVISION_SHA256":
        errors.append("imported stable IDs must use immutable UUIDv5 inputs")
    forbidden = set(id_policy.get("mutable_inputs_forbidden", []))
    if not {"display_name", "filesystem_path", "sort_order"}.issubset(forbidden):
        errors.append("mutable names, paths, and ordering must not define stable IDs")
    namespaces = set(id_policy.get("namespaces", []))
    if not {"message", "session", "reservation"}.issubset(namespaces):
        errors.append("R3 protocol trace namespaces must be registered by R2 identity policy")
    ownership = contract.get("ownership", [])
    patterns = [entry.get("field_pattern") for entry in ownership]
    if len(patterns) != len(set(patterns)):
        errors.append("every field pattern must have exactly one ownership entry")
    for entry in ownership:
        if not entry.get("authoritative_owner"):
            errors.append(f"missing authoritative owner for {entry.get('field_pattern')}")
        if entry.get("writer_resolution") not in {"STATIC", "PINNED_ORIGIN_OWNER"}:
            errors.append(f"invalid writer resolution for {entry.get('field_pattern')}")
    entries_by_pattern = {entry.get("field_pattern"): entry for entry in ownership}
    expected_operations_ownership = {
        "/operations/jobs/*": ("OperationsJob", "integra.operations"),
        "/operations/reservations/*": (
            "HostResourceReservation",
            "integra.resource_scheduler",
        ),
        "/operations/model_residencies/*": (
            "ModelResidency",
            "integra.resource_scheduler",
        ),
    }
    for pattern, (entity, owner) in expected_operations_ownership.items():
        entry = entries_by_pattern.get(pattern)
        if entry != {
            "entity": entity,
            "field_pattern": pattern,
            "authoritative_owner": owner,
            "writer_resolution": "STATIC",
            "integra_access": "AUTHORITATIVE_WRITE",
        }:
            errors.append(f"operations ownership differs for {pattern}")
    collisions = contract.get("collision_policy", {})
    if collisions.get("same_id_different_hash") != "HARD_CONFLICT":
        errors.append("same ID with a different identity hash must hard-fail")
    return errors


def validate_worker_protocol(contract: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != "1.0" or contract.get("protocol_version") != "1.0":
        errors.append("worker protocol and registry versions must be 1.0")
    if contract.get("transport") != "LOCAL_STDIO_JSONL":
        errors.append("R3 transport must remain local stdio JSONL")
    if contract.get("network_service_required") is not False:
        errors.append("R3 must not require a network service")
    if contract.get("schemas") != {
        "message": "schemas/worker_protocol_v1.schema.json",
        "artifact_reference": "schemas/artifact_reference_v1.schema.json",
        "component_identity": "schemas/component_identity_v1.schema.json",
    }:
        errors.append("R3 schema registry must pin all three accepted schemas")
    compatibility = contract.get("compatibility", {})
    expected_compatibility = {
        "negotiation": "HIGHEST_EXACT_COMMON_PROTOCOL_VERSION",
        "schema_policy": "EXACT_SCHEMA_VERSION",
        "unknown_protocol": "FAIL_CLOSED",
        "unknown_schema": "FAIL_CLOSED",
        "backward_compatible_protocol_versions": [],
    }
    if compatibility != expected_compatibility:
        errors.append("R3 compatibility policy must remain exact and fail closed")
    expected_message_types = {
        "HANDSHAKE_REQUEST", "HANDSHAKE_RESPONSE", "JOB_REQUEST", "PROGRESS",
        "RESULT", "ERROR", "CANCEL_REQUEST", "CANCEL_ACK",
    }
    if set(contract.get("message_types", [])) != expected_message_types:
        errors.append("R3 message type inventory is incomplete")
    artifact_policy = contract.get("artifact_policy", {})
    if artifact_policy.get("content_identity") != "SHA256_CANONICAL_BYTES":
        errors.append("R3 artifacts must be content-addressed by SHA-256")
    if artifact_policy.get("paths") != "NORMALIZED_RELATIVE_ONLY":
        errors.append("R3 artifact paths must be normalized and relative")
    job_policy = contract.get("job_policy", {})
    if job_policy.get("unknown_outcome_retry") != "DENIED":
        errors.append("R3 must deny automatic retry for unknown outcomes")
    if job_policy.get("mutable_write") != "VALID_PROJECT_LEASE_AND_ARTIFACT_PRECONDITION_REQUIRED":
        errors.append("R3 mutable jobs must require the accepted Project Lease")
    if contract.get("component_baseline_manifest") != "state/component_baselines_v1.json":
        errors.append("R3 worker identity must use the pinned R1 component baseline")
    fixtures = contract.get("fixtures", {})
    expected_fixtures = {"success", "cancellation", "retry", "incompatibility", "provenance"}
    if set(fixtures) != expected_fixtures:
        errors.append("R3 fixture inventory is incomplete")
    for name, fixture in fixtures.items():
        path = fixture.get("path", "")
        if not path or not (root / path).is_file():
            errors.append(f"missing R3 {name} fixture: {path}")
            continue
        try:
            loaded = load_json(root / path)
        except (OSError, json.JSONDecodeError):
            errors.append(f"invalid JSON in R3 {name} fixture: {path}")
            continue
        if loaded.get("expected") != fixture.get("expected"):
            errors.append(f"R3 {name} fixture expectation does not match registry")
    if contract.get("status") != "ACCEPTED":
        errors.append("R3 contract status must be ACCEPTED")
    return errors


def validate_adapter_spike(evidence: dict, baselines: dict) -> list[str]:
    errors: list[str] = []
    if evidence.get("schema_version") != "1.0":
        errors.append("R4 evidence schema_version must be 1.0")
    if evidence.get("protocol_contract") != "state/worker_protocol_v1.json":
        errors.append("R4 must use the accepted R3 protocol")
    if evidence.get("source_repositories_changed") is not False:
        errors.append("R4 must not modify source repositories")
    if evidence.get("status") != "PASS":
        errors.append("R4 acceptance status must be PASS")
    controller = evidence.get("controller", {})
    for field in ("commit_sha", "tree_sha"):
        value = controller.get(field, "")
        if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
            errors.append(f"R4 controller has invalid {field}")
    policy = evidence.get("policy", {})
    expected_policy = {
        "source_checkouts": "TEMPORARY_PINNED_READ_ONLY_INPUTS",
        "outputs": "SEPARATE_NON_SOURCE_DIRECTORIES",
        "source_mutation": "DENIED",
        "network_service": "NOT_USED",
        "private_data": "NOT_ACCESSED",
        "external_action": "NOT_PERFORMED",
    }
    if policy != expected_policy:
        errors.append("R4 safety policy differs from the accepted boundary")
    baseline_by_id = {item.get("id"): item for item in baselines.get("components", [])}
    components = evidence.get("components", [])
    if {item.get("id") for item in components} != {"seminartext", "videotext"}:
        errors.append("R4 must contain exactly one probe for each pinned component")
    expected_sequence = [
        "HANDSHAKE_REQUEST", "HANDSHAKE_RESPONSE", "JOB_REQUEST",
        "PROGRESS", "PROGRESS", "RESULT",
    ]
    for component in components:
        component_id = component.get("id")
        baseline = baseline_by_id.get(component_id, {})
        if component.get("commit_sha") != baseline.get("commit_sha"):
            errors.append(f"R4 {component_id} commit differs from the R1 baseline")
        if component.get("tree_sha") != baseline.get("tree_sha"):
            errors.append(f"R4 {component_id} tree differs from the R1 baseline")
        if component.get("message_sequence") != expected_sequence:
            errors.append(f"R4 {component_id} message sequence is incomplete")
        if component.get("source_before") != "CLEAN" or component.get("source_after") != "CLEAN":
            errors.append(f"R4 {component_id} source checkout was not preserved")
        if component.get("status") != "PASS":
            errors.append(f"R4 {component_id} probe did not pass")
        for field in (
            "input_sha256", "protocol_stream_sha256", "report_sha256",
            "stdout_sha256", "stderr_sha256",
        ):
            value = component.get(field, "")
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                errors.append(f"R4 {component_id} has invalid {field}")
    contract_evidence = evidence.get("contract_evidence", {})
    required_checks = {
        "handshake", "bounded_request_per_component", "progress", "cancellation",
        "input_and_output_hashes", "structured_failure_reporting",
        "timeout_unknown_outcome", "source_checkout_unchanged", "separate_output",
    }
    if set(contract_evidence) != required_checks or any(
        value != "PASS" for value in contract_evidence.values()
    ):
        errors.append("R4 contract evidence is incomplete")
    return errors


def validate_capability_benchmark(evidence: dict, baselines: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        validate_benchmark_record(evidence)
    except BenchmarkValidationError as exc:
        errors.extend(str(exc).splitlines())
        return errors
    fixture_reference = evidence["fixture_manifest"]
    fixture_path = root / fixture_reference["path"]
    if not fixture_path.is_file() or sha256_file(fixture_path) != fixture_reference["sha256"]:
        errors.append("R5 normalized fixture hash differs from the governed record")
    raw_reference = evidence["raw_replay"]
    raw_path = root / raw_reference["path"]
    if not raw_path.is_file() or sha256_file(raw_path) != raw_reference["sha256"]:
        errors.append("R5 raw replay hash differs from the governed record")
        return errors
    raw = load_json(raw_path)
    if raw.get("source_before") != raw.get("source_after"):
        errors.append("R5 source checkout state changed during replay")
    baseline_by_id = {item["id"]: item for item in baselines.get("components", [])}
    for component_id, source in raw.get("source_before", {}).items():
        baseline = baseline_by_id.get(component_id, {})
        if source.get("commit_sha") != baseline.get("commit_sha"):
            errors.append(f"R5 {component_id} commit differs from R1")
        if source.get("tree_sha") != baseline.get("tree_sha"):
            errors.append(f"R5 {component_id} tree differs from R1")
        if source.get("status") != "CLEAN":
            errors.append(f"R5 {component_id} checkout was not clean")
    return errors


def validate_core_alpha_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version",
        "status",
        "issue",
        "pipeline",
        "execution_mode",
        "manifest_schema",
        "fixture",
        "component_baselines",
        "capability_selections",
        "acceptance",
        "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top_level:
        return ["R6 evidence fields must match the v1 contract"]
    expected_values = {
        "schema_version": "1.0",
        "status": "PARTIAL",
        "issue": 8,
        "pipeline": "INTEGRA_CORE_ALPHA_V1",
        "execution_mode": "CONTRACT_REPLAY",
        "manifest_schema": "schemas/core_alpha_manifest_v1.schema.json",
        "component_baselines": "state/component_baselines_v1.json",
        "capability_selections": "state/capability_benchmark_v1.json",
    }
    for field, expected in expected_values.items():
        if evidence.get(field) != expected:
            errors.append(f"R6 evidence has invalid {field}")
    fixture = evidence.get("fixture", {})
    if not isinstance(fixture, dict) or set(fixture) != {"path", "sha256"}:
        errors.append("R6 fixture reference is invalid")
    else:
        fixture_path = root / fixture.get("path", "")
        if not fixture_path.is_file():
            errors.append("R6 replay fixture is missing")
        elif sha256_file(fixture_path) != fixture.get("sha256"):
            errors.append("R6 replay fixture hash differs from the governed record")
        else:
            try:
                ReplayStageWorker(load_json(fixture_path))
            except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
                errors.append(f"R6 replay fixture is invalid: {error}")
    expected_acceptance = {
        "stage_sequence_complete": True,
        "exact_artifact_lineage": True,
        "pinned_component_identities": True,
        "project_lease_enforced": True,
        "concurrent_writer_blocked": True,
        "store_path_symlinks_rejected": True,
        "stage_output_contract_enforced": True,
        "manifest_provenance_revalidated": True,
        "cancellation_checkpoint": True,
        "resume_revalidates_source_component_artifact_and_lineage": True,
        "deterministic_outputs": True,
        "semantic_authority": "PROVISIONAL_ONLY",
        "semantic_status_persisted_and_payload_checked": True,
        "source_repositories_changed": False,
        "protected_data_accessed": False,
        "gold_accessed": False,
        "external_actions_performed": False,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("R6 checkpoint evidence differs from the fail-closed contract")
    limitations = evidence.get("limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) < 3
        or len(limitations) != len(set(limitations))
        or not all(isinstance(item, str) and item for item in limitations)
    ):
        errors.append("R6 limitations must contain at least three unique statements")
    return errors


def validate_core_alpha_real_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors = validate_actual_evidence(evidence)
    if content_sha256(evidence) != EXPECTED_CORE_ALPHA_REAL_SHA256:
        errors.append("R6 actual evidence differs from the independently reproduced governed record")
    if evidence.get("issue") != 8:
        errors.append("R6 actual evidence must belong to Issue #8")
    baseline_components = {
        item["id"]: {
            "repository": item["repository"],
            "commit_sha": item["commit_sha"],
            "tree_sha": item["tree_sha"],
            "version": item["version"],
        }
        for item in baselines.get("components", [])
    }
    if evidence.get("component_identities") != baseline_components:
        errors.append("R6 actual component identities differ from the R1 baseline")
    implementation = evidence.get("implementation")
    if not isinstance(implementation, list) or len(implementation) != len(EXPECTED_CORE_ALPHA_REAL_IMPLEMENTATION):
        errors.append("R6 actual implementation inventory must be exact")
    else:
        paths = []
        for record in implementation:
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                errors.append("R6 actual implementation record is invalid")
                continue
            paths.append(record["path"])
            path = root / record["path"]
            if not path.is_file():
                errors.append(f"R6 actual implementation is missing: {record['path']}")
            elif sha256_file(path) != record["sha256"]:
                errors.append(f"R6 actual implementation hash differs: {record['path']}")
        if len(paths) != len(set(paths)):
            errors.append("R6 actual implementation paths must be unique")
        if set(paths) != EXPECTED_CORE_ALPHA_REAL_IMPLEMENTATION:
            errors.append("R6 actual implementation inventory must be exact")
    acceptance = evidence.get("acceptance", {})
    required_acceptance = {
        "real_local_video_decoded": True,
        "pinned_components_executed": True,
        "source_grounded_provenance": True,
        "videotext_review_checkpoint": "SOURCE_TRANSCRIPT",
        "seminartext_topics_generated": True,
        "canonical_evidence_valid": True,
        "exception_review_package_generated": True,
        "provisional_knowledge_generated": True,
        "videotext_media_clip_rendered": True,
        "semantic_authority": "PROVISIONAL_ONLY",
        "human_decisions_applied": 0,
        "source_repositories_changed": False,
        "protected_data_accessed": False,
        "gold_accessed": False,
    }
    if acceptance != required_acceptance:
        errors.append("R6 actual acceptance evidence differs from the governed contract")
    determinism = evidence.get("determinism", {})
    if (
        determinism.get("independent_runs_compared") != 2
        or determinism.get("all_stage_hashes_identical") is not True
        or not isinstance(determinism.get("runs"), list)
        or len(determinism["runs"]) != 2
    ):
        errors.append("R6 actual stage hashes must match across two independent runs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 3 or len(limitations) != len(set(limitations)):
        errors.append("R6 actual limitations must contain at least three unique statements")
    return errors


def validate_operations_evidence(
    evidence: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version",
        "issue",
        "status",
        "semantic_authority",
        "protected_data_accessed",
        "external_actions_performed",
        "implementation",
        "fixture_inventory",
        "acceptance",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top_level:
        return ["Operations evidence fields must match the v1 contract"]
    if evidence.get("schema_version") != "1.0":
        errors.append("Operations evidence schema_version must be 1.0")
    if evidence.get("issue") != 46 or evidence.get("status") != "PASS":
        errors.append("Operations evidence must certify Issue #46 as PASS")
    if evidence.get("semantic_authority") != "NONE":
        errors.append("Operations evidence cannot claim semantic authority")
    if evidence.get("protected_data_accessed") is not False:
        errors.append("Operations evidence must not access protected data")
    if evidence.get("external_actions_performed") is not False:
        errors.append("Operations evidence must not claim external actions")

    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("Operations implementation inventory must be a list")
    else:
        paths = {item.get("path") for item in implementation if isinstance(item, dict)}
        if paths != EXPECTED_OPERATIONS_IMPLEMENTATION or len(implementation) != len(paths):
            errors.append("Operations implementation inventory must be exact")
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("Operations implementation reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"Operations implementation hash differs: {item['path']}")

    fixture_inventory = evidence.get("fixture_inventory")
    if not isinstance(fixture_inventory, list):
        errors.append("Operations fixture inventory must be a list")
    else:
        scenarios = {
            item.get("scenario") for item in fixture_inventory if isinstance(item, dict)
        }
        if scenarios != EXPECTED_OPERATIONS_FIXTURES or len(fixture_inventory) != len(scenarios):
            errors.append("Operations fixture inventory must be exact")
        for item in fixture_inventory:
            if not isinstance(item, dict) or set(item) != {"scenario", "path", "sha256"}:
                errors.append("Operations fixture reference differs from v1")
                continue
            expected_path = f"tests/fixtures/operations_v1/{item['scenario']}.json"
            if item["path"] != expected_path:
                errors.append(f"Operations fixture path differs: {item['scenario']}")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"Operations fixture hash differs: {item['scenario']}")

    expected_acceptance = {
        "job_lifecycle_versioned": True,
        "honest_eta": True,
        "cancellation_acknowledged": True,
        "checkpoint_resume_identity_bound": True,
        "capability_preflight_exact": True,
        "resource_reservations_atomic": True,
        "reference_16gb_policy_enforced": True,
        "calculated_disk_authoritative": True,
        "playlist_sequential": True,
        "redacted_structured_logs": True,
        "integrity_fail_closed": True,
        "model_unload_owner_scoped": True,
        "child_process_cleanup_verified": True,
        "protected_scope_preserved": True,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("Operations acceptance differs from the Issue #46 contract")
    try:
        results = run_operations_fixtures(root)
    except Exception as error:
        errors.append(f"Operations executable fixtures failed: {error}")
    else:
        if set(results) != EXPECTED_OPERATIONS_FIXTURES or any(
            status != "PASS" for status in results.values()
        ):
            errors.append("Operations executable fixture results are incomplete")
    return errors


def validate_migration_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version", "issue", "status", "pinned_components",
        "native_probe_evidence", "implementation", "fixture_inventory",
        "acceptance", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top_level:
        return ["R7 migration evidence fields must match the v1 contract"]
    if evidence.get("schema_version") != "1.0":
        errors.append("R7 migration evidence schema_version must be 1.0")
    if evidence.get("issue") != 9 or evidence.get("status") != "PASS":
        errors.append("R7 migration evidence must certify Issue #9 as PASS")

    baseline_by_id = {
        component.get("id"): component for component in baselines.get("components", [])
    }
    pinned = evidence.get("pinned_components", {})
    if set(pinned) != {"seminartext", "videotext"}:
        errors.append("R7 must pin SeminarText and VideoText exactly")
    else:
        for component_id, record in pinned.items():
            baseline = baseline_by_id.get(component_id, {})
            expected = {
                "commit_sha": baseline.get("commit_sha"),
                "tree_sha": baseline.get("tree_sha"),
                "version": baseline.get("version"),
                "source_repository_changed": False,
            }
            if record != expected:
                errors.append(f"R7 pinned {component_id} identity differs from R1")

    expected_native_probes = [
        {
            "component": "seminartext",
            "commit_sha": "a94936cd77cde13561c97c804ece1ac1134e01a6",
            "probe_path": "tests/test_project_add.py",
            "probe_sha256": "903f550841deda2f963c85fb5184e698038e6456f86410b7c3e58699836a21c0",
            "execution_mode": "PINNED_SOURCE_TEMPORARY_WORKSPACE",
            "command": "PYTHONDONTWRITEBYTECODE=1 python3 tests/test_project_add.py",
            "result": "PASS",
            "observed_stdout": "project-add regression test passed",
        },
        {
            "component": "videotext",
            "commit_sha": "2e098d1705b6815628bee1e023f4742718eabf02",
            "probe_path": "Tests/ProjectSchemaProbe.swift",
            "probe_sha256": "1eff677030ff7411808c642faee280c731bf5ba3c2580d87ebbb43e0df39f313",
            "execution_mode": "PINNED_SOURCE_TEMPORARY_WORKSPACE",
            "command": "swiftc Sources/*.swift Tests/ProjectSchemaProbe.swift -o <temporary>/ProjectSchemaProbe && <temporary>/ProjectSchemaProbe",
            "result": "PASS",
            "observed_stdout": "PROJECT_SCHEMA_PROBE_PASS",
        },
    ]
    if evidence.get("native_probe_evidence") != expected_native_probes:
        errors.append("R7 native source compatibility evidence differs from pinned probes")

    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("R7 implementation inventory must be a list")
    else:
        paths = {item.get("path") for item in implementation if isinstance(item, dict)}
        if paths != EXPECTED_MIGRATION_IMPLEMENTATION or len(paths) != len(implementation):
            errors.append("R7 implementation inventory must be exact")
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R7 implementation reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R7 implementation hash differs: {item['path']}")

    fixtures = evidence.get("fixture_inventory")
    if not isinstance(fixtures, list):
        errors.append("R7 fixture inventory must be a list")
    else:
        paths = {item.get("path") for item in fixtures if isinstance(item, dict)}
        if paths != EXPECTED_MIGRATION_FIXTURES or len(paths) != len(fixtures):
            errors.append("R7 fixture inventory must be exact")
        for item in fixtures:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R7 fixture reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R7 fixture hash differs: {item['path']}")

    expected_acceptance = {
        "read_only_discovery": True,
        "dry_run_has_zero_writes": True,
        "copy_on_write_target": True,
        "stable_ids_path_independent": True,
        "source_and_target_hashes_verified": True,
        "target_collision_fails_without_overwrite": True,
        "validation_precedes_activation": True,
        "exact_owned_target_rollback": True,
        "interrupted_copy_recovery": True,
        "seminartext_source_compatibility_preserved": True,
        "videotext_source_compatibility_preserved": True,
        "source_native_open_probes_passed": True,
        "external_references_not_accessed": True,
        "source_repositories_changed": False,
        "private_data_accessed": False,
        "protected_data_accessed": False,
        "external_actions_performed": False,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("R7 acceptance evidence differs from the governed contract")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 2 or len(limitations) != len(set(limitations)):
        errors.append("R7 limitations must contain at least two unique statements")
    try:
        results = run_migration_fixtures(root)
    except Exception as error:
        errors.append(f"R7 executable migration fixtures failed: {error}")
    else:
        if set(results) != {
            "seminartext_copy_rollback", "videotext_copy_rollback",
            "stable_ids_after_move", "target_collision_fail_closed",
            "partial_copy_recovery",
        } or any(status != "PASS" for status in results.values()):
            errors.append("R7 executable migration fixture results are incomplete")
    return errors


def validate_playlist_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version", "issue", "status", "implementation", "fixtures",
        "acceptance", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top_level:
        return ["R8A playlist evidence fields must match the v1 contract"]
    if evidence.get("schema_version") != "1.0":
        errors.append("R8A playlist evidence schema_version must be 1.0")
    if evidence.get("issue") != 10 or evidence.get("status") != "PASS":
        errors.append("R8A playlist evidence must certify Issue #10 as PASS")

    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("R8A implementation inventory must be a list")
    else:
        paths = {item.get("path") for item in implementation if isinstance(item, dict)}
        if paths != EXPECTED_PLAYLIST_IMPLEMENTATION or len(paths) != len(implementation):
            errors.append("R8A implementation inventory must be exact")
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R8A implementation reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R8A implementation hash differs: {item['path']}")

    fixtures = evidence.get("fixtures")
    if not isinstance(fixtures, list):
        errors.append("R8A fixture inventory must be a list")
    else:
        paths = {item.get("path") for item in fixtures if isinstance(item, dict)}
        if paths != EXPECTED_PLAYLIST_FIXTURES or len(paths) != len(fixtures):
            errors.append("R8A fixture inventory must be exact")
        for item in fixtures:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R8A fixture reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R8A fixture hash differs: {item['path']}")

    expected_acceptance = {
        "offline_contract_only": True,
        "title_metadata_preserved": True,
        "subset_selection": True,
        "plan_identity_binds_execution": True,
        "sequential_processing": True,
        "storage_estimation": True,
        "checkpoint_resume": True,
        "per_item_checkpoint_emitted": True,
        "completed_items_not_reprocessed": True,
        "completed_artifacts_byte_verified": True,
        "refresh_diff": True,
        "inaccessible_items_recorded": True,
        "remote_removal_preserves_local_evidence": True,
        "per_video_provenance": True,
        "live_youtube_accessed": False,
        "credentials_accessed": False,
        "external_actions_performed": False,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("R8A acceptance evidence differs from the governed contract")
    limitations = evidence.get("limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) < 2
        or len(limitations) != len(set(limitations))
    ):
        errors.append("R8A limitations must contain at least two unique statements")

    try:
        previous = discover_playlist(load_json(root / "tests/fixtures/playlist_v1/snapshot_initial.json"))
        current = discover_playlist(load_json(root / "tests/fixtures/playlist_v1/snapshot_refreshed.json"))
        plan = build_playlist_plan(previous)
        calls: list[str] = []
        persisted: list[dict] = []
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)

            def processor(item: dict) -> dict:
                calls.append(item["video_id"])
                relative_path = f"{item['video_id']}.bin"
                (artifact_root / relative_path).write_bytes(
                    f"processed:{item['video_id']}".encode("utf-8")
                )
                return {"relative_path": relative_path}

            paused = process_playlist(
                plan,
                processor,
                artifact_root=artifact_root,
                checkpoint_writer=persisted.append,
                max_new_items=1,
            )
            complete = process_playlist(
                plan,
                processor,
                paused,
                artifact_root=artifact_root,
                checkpoint_writer=persisted.append,
            )
            replayed = process_playlist(
                plan,
                processor,
                complete,
                artifact_root=artifact_root,
                checkpoint_writer=persisted.append,
            )
            refresh = diff_playlist_refresh(
                previous, current, complete, artifact_root=artifact_root
            )
        if (
            paused["status"] != "PAUSED"
            or complete["status"] != "COMPLETE"
            or replayed != complete
            or calls != ["video-a", "video-b"]
            or not persisted
            or refresh["added_video_ids"] != ["video-d"]
            or refresh["removed_video_ids"] != ["video-c"]
            or refresh["reordered_video_ids"] != ["video-a", "video-b"]
            or refresh["became_inaccessible_video_ids"] != ["video-a"]
            or refresh["retained_completed_evidence"] != complete["completed"]
        ):
            errors.append("R8A executable playlist fixtures are incomplete")
    except Exception as error:
        errors.append(f"R8A executable playlist fixtures failed: {error}")
    return errors


def validate_document_pipeline_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version", "issue", "status", "implementation", "fixtures",
        "acceptance", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_top_level:
        return ["R8B document pipeline evidence fields must match the v1 contract"]
    if evidence.get("schema_version") != "1.0":
        errors.append("R8B document pipeline schema_version must be 1.0")
    if evidence.get("issue") != 11 or evidence.get("status") != "PASS":
        errors.append("R8B document pipeline evidence must certify Issue #11 as PASS")

    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("R8B implementation inventory must be a list")
    else:
        paths = {item.get("path") for item in implementation if isinstance(item, dict)}
        if paths != EXPECTED_DOCUMENT_IMPLEMENTATION or len(paths) != len(implementation):
            errors.append("R8B implementation inventory must be exact")
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R8B implementation reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R8B implementation hash differs: {item['path']}")

    fixtures = evidence.get("fixtures")
    if not isinstance(fixtures, list):
        errors.append("R8B fixture inventory must be a list")
    else:
        paths = {item.get("path") for item in fixtures if isinstance(item, dict)}
        if paths != EXPECTED_DOCUMENT_FIXTURES or len(paths) != len(fixtures):
            errors.append("R8B fixture inventory must be exact")
        for item in fixtures:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R8B fixture reference differs from v1")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"R8B fixture hash differs: {item['path']}")

    expected_acceptance = {
        "pdf_supported": True,
        "pptx_supported": True,
        "docx_supported": True,
        "txt_supported": True,
        "markdown_supported": True,
        "images_and_scans_supported": True,
        "page_locators": True,
        "slide_locators": True,
        "region_locators": True,
        "character_locators": True,
        "embedded_media_extraction": True,
        "ocr_fallback": True,
        "source_fidelity": True,
        "image_heavy_not_plain_text": True,
        "deterministic_records": True,
        "semantic_authority_provisional": True,
        "network_accessed": False,
        "credentials_accessed": False,
        "protected_data_accessed": False,
        "external_actions_performed": False,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("R8B acceptance evidence differs from the governed contract")
    limitations = evidence.get("limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) < 2
        or len(limitations) != len(set(limitations))
    ):
        errors.append("R8B limitations must contain at least two unique statements")

    try:
        fixture = load_json(root / "tests/fixtures/document_v1/cases.json")
        if fixture.get("schema_version") != "1.0" or {
            item.get("format") for item in fixture.get("cases", [])
        } != {"PDF", "PPTX", "DOCX", "TXT", "MARKDOWN", "IMAGE"}:
            errors.append("R8B format fixture inventory is incomplete")
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            text_path = temporary_root / "fixture.txt"
            text_path.write_text("Exact source text.", encoding="utf-8")
            text_record = extract_document(
                text_path, captured_at=fixture["captured_at"]
            )
            scan_path = temporary_root / "fixture.png"
            scan_path.write_bytes(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
                "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
            ))

            def ocr_provider(_request: dict) -> dict:
                return {
                    "provider": {
                        "component_id": "fixture-ocr",
                        "implementation_sha256": "1" * 64,
                        "model_id": "fixture-model",
                        "model_sha256": "2" * 64,
                    },
                    "blocks": [{
                        "unit_kind": "IMAGE",
                        "unit_index": 1,
                        "region": {"x": 0, "y": 0, "width": 1, "height": 1},
                        "text": "OCR region text",
                        "confidence": 1.0,
                    }],
                }

            scan_record = extract_document(
                scan_path,
                captured_at=fixture["captured_at"],
                ocr_provider=ocr_provider,
            )
            validate_document_record(text_record)
            validate_document_against_source(text_record, text_path)
            validate_document_record(scan_record)
            validate_document_against_source(scan_record, scan_path)
        if (
            text_record["native_extraction"]["blocks"][0]["text"] != "Exact source text."
            or text_record["content_mode"] != "TEXT"
            or scan_record["content_mode"] != "SCAN"
            or scan_record["ocr"]["status"] != "COMPLETE"
            or scan_record["ocr"]["blocks"][0]["locator"]["region"]
            != {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        ):
            errors.append("R8B executable document fixtures are incomplete")
    except Exception as error:
        errors.append(f"R8B executable document fixtures failed: {error}")
    return errors


def validate_projects_sources_evidence(
    evidence: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "implementation", "project_kinds",
        "source_types", "dependencies", "acceptance", "safety",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["Projects & Sources evidence fields must match the v1 contract"]
    if evidence.get("schema_version") != "1.0" or evidence.get("status") != "ACCEPTED" or evidence.get("issue") != 47:
        errors.append("Projects & Sources evidence must certify Issue #47 as ACCEPTED")
    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("Projects & Sources implementation inventory must be a list")
    else:
        paths: list[str] = []
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("Projects & Sources implementation reference differs from v1")
                continue
            paths.append(item["path"])
            path = root / item["path"]
            if not path.is_file():
                errors.append(f"Projects & Sources implementation is missing: {item['path']}")
            elif sha256_file(path) != item["sha256"]:
                errors.append(f"Projects & Sources implementation hash differs: {item['path']}")
        if set(paths) != EXPECTED_PROJECTS_SOURCES_IMPLEMENTATION or len(paths) != len(set(paths)):
            errors.append("Projects & Sources implementation inventory must be exact")
    if set(evidence.get("project_kinds", [])) != {"SEMINAR", "COURSE", "SERIES", "EVENT"}:
        errors.append("Projects & Sources project kind inventory differs")
    expected_source_types = {
        "LOCAL_VIDEO", "LOCAL_AUDIO", "YOUTUBE_VIDEO", "YOUTUBE_PLAYLIST",
        "PDF", "PPTX", "DOCX", "TXT", "MARKDOWN", "IMAGE", "SCAN",
    }
    if set(evidence.get("source_types", [])) != expected_source_types:
        errors.append("Projects & Sources source type inventory differs")
    if set(evidence.get("dependencies", [])) != {"R6", "R7", "R8A", "R8B"}:
        errors.append("Projects & Sources accepted dependencies differ")
    expected_acceptance = {
        "stable_project_identity": True,
        "project_lifecycle_history": True,
        "stable_source_identity": True,
        "revision_lineage": True,
        "revision_hash_chain": True,
        "exact_provenance": True,
        "container_signatures_validated": True,
        "reopen_idempotent": True,
        "refresh_idempotent": True,
        "individual_youtube_independent": True,
        "playlist_contract_reused": True,
        "multi_playlist_membership": True,
        "document_contract_reused": True,
        "unavailable_remote_visible": True,
        "conflicts_fail_closed": True,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("Projects & Sources acceptance evidence differs from v1")
    expected_safety = {
        "source_files_modified": False,
        "source_repositories_modified": False,
        "network_access_performed": False,
        "credentials_accessed": False,
        "protected_data_accessed": False,
        "semantic_authority": "NOT_APPLICABLE",
    }
    if evidence.get("safety") != expected_safety:
        errors.append("Projects & Sources safety evidence differs from v1")

    try:
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            captured = "2026-09-11T00:00:00Z"
            later = "2026-09-11T00:01:00Z"
            latest = "2026-09-11T00:02:00Z"
            registry = new_registry("governance-fixture", captured)
            registry, project_id = register_project(
                registry, project_key="fixture-seminar", kind="SEMINAR",
                title="Fixture seminar", occurred_at=captured,
            )
            reopened, reopened_id = register_project(
                loads_registry(dumps_registry(registry)),
                project_key="fixture-seminar", kind="SEMINAR",
                title="Fixture seminar", occurred_at=later,
            )
            if reopened != registry or reopened_id != project_id:
                errors.append("Projects & Sources project reopen is not idempotent")
            audio_path = fixture_root / "fixture.wav"
            audio_path.write_bytes(b"RIFF\x08\x00\x00\x00WAVEfmt ")
            source_before = sha256_file(audio_path)
            registry, _ = register_local_media(
                registry, project_id, audio_path, captured_at=later
            )
            raw_snapshot = load_json(
                root / "tests/fixtures/playlist_v1/snapshot_initial.json"
            )
            discovery = discover_playlist(raw_snapshot)
            registry, standalone_id = register_youtube_video(
                registry, project_id, video_id="video-a", title="Fixture lesson A",
                availability="AVAILABLE", captured_at=later,
            )
            registry, playlist_id, video_ids = register_youtube_playlist(
                registry, project_id, discovery, captured_at=latest
            )
            notes_path = fixture_root / "notes.md"
            notes_path.write_text("# Fixture\n\nSupporting material.", encoding="utf-8")
            document = extract_document(notes_path, captured_at=latest)
            registry, document_id = register_document(
                registry, project_id, document, captured_at=latest
            )
            round_trip = loads_registry(dumps_registry(registry))
            validate_registry(round_trip)
            if (
                source_before != sha256_file(audio_path)
                or standalone_id != discovery["items"][0]["video_source_id"]
                or playlist_id != discovery["collection_id"]
                or standalone_id not in video_ids
                or document_id != document["source"]["source_id"]
                or len(round_trip["projects"]) != 1
                or len(round_trip["sources"]) != 6
                or len({item["source_id"] for item in round_trip["sources"]}) != 6
            ):
                errors.append("Projects & Sources executable acceptance fixture differs")
    except Exception as error:
        errors.append(f"Projects & Sources executable acceptance fixture failed: {error}")
    return errors


def validate_transcript_topic_studio_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "implementation", "dependencies",
        "capability_owners", "topic_levels", "locator_types", "acceptance", "safety",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["Transcript & Topic Studio evidence fields must match v1"]
    if evidence.get("schema_version") != "1.0" or evidence.get("status") != "ACCEPTED" or evidence.get("issue") != 48:
        errors.append("Transcript & Topic Studio must certify Issue #48 as ACCEPTED")
    implementation = evidence.get("implementation")
    if not isinstance(implementation, list):
        errors.append("Transcript & Topic Studio implementation inventory must be a list")
    else:
        paths: list[str] = []
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("Transcript & Topic Studio implementation reference differs")
                continue
            paths.append(item["path"])
            path = root / item["path"]
            if not path.is_file():
                errors.append(f"Transcript & Topic Studio implementation is missing: {item['path']}")
            elif sha256_file(path) != item["sha256"]:
                errors.append(f"Transcript & Topic Studio implementation hash differs: {item['path']}")
        if set(paths) != EXPECTED_TRANSCRIPT_TOPIC_STUDIO_IMPLEMENTATION or len(paths) != len(set(paths)):
            errors.append("Transcript & Topic Studio implementation inventory must be exact")
    if evidence.get("dependencies") != ["R6", "PROJECTS_AND_SOURCES_V1"]:
        errors.append("Transcript & Topic Studio dependency order differs")
    expected_owners = {
        "media_preparation": ["videotext"],
        "asr": ["videotext"],
        "translation": ["videotext"],
        "word_timeline": ["seminartext"],
        "topics": ["seminartext"],
        "review_mechanics": ["seminartext", "videotext"],
        "quality_validation": ["seminartext", "videotext"],
    }
    if evidence.get("capability_owners") != expected_owners:
        errors.append("Transcript & Topic Studio capability owners differ from R5")
    if evidence.get("topic_levels") != ["DETAILED", "NORMAL", "COARSE"]:
        errors.append("Transcript & Topic Studio Topic levels differ")
    if set(evidence.get("locator_types", [])) != {
        "TIME_INTERVAL", "WORD_INTERVAL", "PAGE_RANGE", "SLIDE_RANGE",
        "REGION", "CHARACTER_RANGE", "ARTIFACT_REVISION",
    }:
        errors.append("Transcript & Topic Studio locator inventory differs")
    expected_acceptance = {
        "source_revision_bound": True,
        "media_preparation_exposed": True,
        "asr_exposed": True,
        "translation_lineage_separate": True,
        "canonical_word_timeline_exposed": True,
        "quality_findings_visible": True,
        "three_topic_levels": True,
        "strict_topic_hierarchy": True,
        "per_source_locator_binding": True,
        "exception_clustering_with_neighbors": True,
        "bulk_review_decision_deterministic": True,
        "review_decision_lease_enforced": True,
        "component_model_config_bound": True,
        "cancellation_and_resume_delegated_to_operations": True,
        "serialization_deterministic": True,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("Transcript & Topic Studio acceptance evidence differs")
    expected_safety = {
        "machine_semantics_accepted": False,
        "source_artifacts_modified": False,
        "source_repositories_modified": False,
        "cross_source_alignment_performed": False,
        "protected_data_accessed": False,
        "gold_accessed": False,
        "network_access_performed": False,
        "credentials_accessed": False,
    }
    if evidence.get("safety") != expected_safety:
        errors.append("Transcript & Topic Studio safety boundary differs")

    try:
        component_commits = {item["id"]: item["commit_sha"] for item in baselines["components"]}
        owners = expected_owners
        bindings = []
        for capability, component_ids in owners.items():
            contracts = {
                "media_preparation": ["project_schema_v7"],
                "asr": ["project_schema_v7"],
                "translation": ["project_schema_v7"],
                "word_timeline": ["canonical_evidence_v1"],
                "topics": ["topic_review_workflow_v2"],
                "review_mechanics": ["topic_review_workflow_v2", "project_schema_v7"],
                "quality_validation": ["canonical_evidence_v1", "project_schema_v7"],
            }[capability]
            bindings.append({
                "capability": capability,
                "components": [
                    {
                        "component_id": component_id,
                        "commit_sha": component_commits[component_id],
                        "contract_id": contracts[index],
                        "model_id": (
                            "ggml-large-v3.bin" if capability == "asr"
                            else "gemma3:4b" if capability == "topics"
                            else None
                        ),
                        "model_sha256": (
                            "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2" if capability == "asr"
                            else "ed1e8a40017e648c133188919a5a0105ce1916726dbc657fecb5ccb5d717c46d" if capability == "topics"
                            else None
                        ),
                    }
                    for index, component_id in enumerate(component_ids)
                ],
                "config_sha256": "3" * 64,
                "r5_selection_sha256": "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3",
            })
        registry = new_registry("studio-governance-fixture", "2026-09-11T00:00:00Z")
        registry, project_id = register_project(
            registry, project_key="studio-project", kind="SEMINAR",
            title="Studio fixture", occurred_at="2026-09-11T00:00:00Z",
        )
        registry, source_id = register_youtube_video(
            registry, project_id, video_id="fixture-video", title="Fixture video",
            availability="AVAILABLE", captured_at="2026-09-11T00:01:00Z",
        )
        source = next(item for item in registry["sources"] if item["source_id"] == source_id)
        source_revision_id = source["current_revision_id"]
        source_hash = source["revisions"][-1]["revision_sha256"]
        studio = new_studio(
            registry, project_id=project_id, source_id=source_id,
            source_revision_id=source_revision_id, bindings=bindings,
            created_at="2026-09-11T00:02:00Z",
        )
        locators = [
            {"type": "TIME_INTERVAL", "start_seconds": 0.0, "end_seconds": 4.0},
            {"type": "ARTIFACT_REVISION", "artifact_id": source_id, "revision_id": source_revision_id, "content_sha256": source_hash},
        ]
        studio, transcript_id = register_transcript(
            studio, registry=registry, native_id="transcript-r1", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", language="ru", word_count=4,
            confidence=0.7, locators=locators,
        )
        words = [
            {"word_id": f"word:{index:06d}", "sequence": index, "text": text,
             "start_seconds": float(index), "end_seconds": float(index) + 0.5,
             "confidence": 0.9}
            for index, text in enumerate(("one", "two", "three", "four"))
        ]
        studio, timeline_id = register_word_timeline(
            studio, registry=registry, native_id="timeline-r1", content_sha256="5" * 64,
            created_at="2026-09-11T00:04:00Z", transcript_id=transcript_id,
            words=words, locators=locators,
        )
        studio, _ = add_quality_finding(
            studio, registry=registry, native_id="low-confidence", created_at="2026-09-11T00:05:00Z",
            capability="quality_validation", artifact_id=transcript_id,
            code="LOW_CONFIDENCE", severity="WARN", confidence=0.7,
            locators=[locators[0]], detail="fixture low confidence",
        )
        topic_locators = locators + [{
            "type": "WORD_INTERVAL", "start_word_id": "word:000000",
            "end_word_id": "word:000003", "start_sequence": 0, "end_sequence": 3,
        }]
        studio, _ = register_topic_set(
            studio, registry=registry, native_id="topics-normal", content_sha256="6" * 64,
            created_at="2026-09-11T00:06:00Z", timeline_id=timeline_id,
            level="NORMAL", topics=[{
                "native_id": "topic-1", "title": "Fixture Topic", "summary": "Fixture summary",
                "confidence": 0.6, "conflict": False, "locators": topic_locators,
                "evidence_refs": ["word:000000", "word:000003"],
            }],
        )
        member_ids = [studio["quality_findings"][0]["finding_id"], studio["topic_sets"][0]["topics"][0]["topic_id"]]
        studio, _ = build_exception_package(
            studio, registry=registry, native_id="package-1", created_at="2026-09-11T00:07:00Z",
            member_ids=member_ids,
        )
        round_trip = loads_studio(dumps_studio(studio, registry), registry)
        validate_studio(round_trip, registry)
        if (
            round_trip["semantic_authority"] != "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION"
            or round_trip["source_artifacts_modified"] is not False
            or round_trip["review_packages"][0]["member_ids"] != sorted(member_ids)
        ):
            errors.append("Transcript & Topic Studio executable fixture differs")
    except Exception as error:
        errors.append(f"Transcript & Topic Studio executable fixture failed: {error}")
    return errors


def validate_multi_source_alignment_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "dependencies", "implementation",
        "node_kinds", "relations", "locator_types", "acceptance", "safety",
        "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R8C multi-source alignment evidence fields must match v1"]
    if evidence.get("schema_version") != "1.0" or evidence.get("status") != "ACCEPTED" or evidence.get("issue") != 12:
        errors.append("R8C evidence must certify Issue #12 as ACCEPTED")
    if evidence.get("dependencies") != [
        "R8A", "R8B", "PROJECTS_AND_SOURCES_V1", "TRANSCRIPT_AND_TOPIC_STUDIO_V1"
    ]:
        errors.append("R8C dependency order differs")
    implementation = evidence.get("implementation")
    paths: list[str] = []
    if not isinstance(implementation, list):
        errors.append("R8C implementation inventory must be a list")
    else:
        for item in implementation:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append("R8C implementation reference differs from v1")
                continue
            paths.append(item["path"])
            path = root / item["path"]
            if not path.is_file():
                errors.append(f"R8C implementation is missing: {item['path']}")
            elif sha256_file(path) != item["sha256"]:
                errors.append(f"R8C implementation hash differs: {item['path']}")
        if set(paths) != EXPECTED_MULTI_SOURCE_ALIGNMENT_IMPLEMENTATION or len(paths) != len(set(paths)):
            errors.append("R8C implementation inventory must be exact")
    if evidence.get("node_kinds") != [
        "AUDIO", "EVIDENCE", "PAGE", "SLIDE", "SUPPORTING_DOCUMENT",
        "TOPIC", "TRANSCRIPT", "VIDEO",
    ]:
        errors.append("R8C node kind inventory differs")
    if evidence.get("relations") != [
        "EVIDENCE_TO_DOCUMENT", "TOPIC_TO_PAGE", "TOPIC_TO_SLIDE",
        "VIDEO_TO_SLIDE", "VIDEO_TO_TRANSCRIPT",
    ]:
        errors.append("R8C relation inventory differs")
    if evidence.get("locator_types") != [
        "ARTIFACT_REVISION", "CHARACTER_RANGE", "PAGE_RANGE", "REGION",
        "SLIDE_RANGE", "TIME_INTERVAL", "WORD_INTERVAL",
    ]:
        errors.append("R8C locator inventory differs")
    expected_acceptance = {
        "authoritative_registry_required": True,
        "validated_upstream_records_required": True,
        "upstream_payloads_not_serialized": True,
        "origin_component_binding_verified": True,
        "current_source_revisions_required": True,
        "source_native_locators_required": True,
        "artifact_revision_locator_required": True,
        "node_kind_source_compatible": True,
        "locator_range_consistency_required": True,
        "video_transcript_same_revision_required": True,
        "node_and_link_content_hash_bound": True,
        "video_to_transcript_navigation": True,
        "video_to_slide_navigation": True,
        "topic_to_page_navigation": True,
        "topic_to_slide_navigation": True,
        "evidence_to_document_navigation": True,
        "forward_and_reverse_navigation": True,
        "deterministic_serialization": True,
        "confidence_and_conflict_visible": True,
        "semantic_acceptance_automatic": False,
    }
    if evidence.get("acceptance") != expected_acceptance:
        errors.append("R8C acceptance evidence differs")
    expected_safety = {
        "source_artifacts_modified": False,
        "source_repositories_modified": False,
        "protected_data_accessed": False,
        "gold_accessed": False,
        "network_access_performed": False,
        "credentials_accessed": False,
        "external_actions_performed": False,
    }
    if evidence.get("safety") != expected_safety:
        errors.append("R8C safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 2 or len(limitations) != len(set(limitations)):
        errors.append("R8C limitations must contain at least two unique statements")

    try:
        captured = "2026-09-11T00:00:00Z"
        registry = new_registry("alignment-governance-fixture", captured)
        registry, project_id = register_project(
            registry, project_key="alignment-project", kind="COURSE",
            title="Alignment fixture", occurred_at=captured,
        )
        registry, first_id = register_youtube_video(
            registry, project_id, video_id="alignment-video-1", title="First",
            availability="AVAILABLE", captured_at=captured,
        )
        registry, second_id = register_youtube_video(
            registry, project_id, video_id="alignment-video-2", title="Second",
            availability="AVAILABLE", captured_at=captured,
        )
        sources = {item["source_id"]: item for item in registry["sources"]}
        first_revision = sources[first_id]["revisions"][-1]
        second_revision = sources[second_id]["revisions"][-1]
        component_commits = {
            item["id"]: item["commit_sha"] for item in baselines["components"]
        }
        owners = {
            "media_preparation": ["videotext"], "asr": ["videotext"],
            "translation": ["videotext"], "word_timeline": ["seminartext"],
            "topics": ["seminartext"],
            "review_mechanics": ["seminartext", "videotext"],
            "quality_validation": ["seminartext", "videotext"],
        }
        contracts = {
            "media_preparation": ["project_schema_v7"],
            "asr": ["project_schema_v7"],
            "translation": ["project_schema_v7"],
            "word_timeline": ["canonical_evidence_v1"],
            "topics": ["topic_review_workflow_v2"],
            "review_mechanics": ["topic_review_workflow_v2", "project_schema_v7"],
            "quality_validation": ["canonical_evidence_v1", "project_schema_v7"],
        }
        bindings = []
        for capability, component_ids in owners.items():
            bindings.append({
                "capability": capability,
                "components": [{
                    "component_id": component_id,
                    "commit_sha": component_commits[component_id],
                    "contract_id": contracts[capability][index],
                    "model_id": (
                        "ggml-large-v3.bin" if capability == "asr"
                        else "gemma3:4b" if capability == "topics" else None
                    ),
                    "model_sha256": (
                        "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"
                        if capability == "asr"
                        else "ed1e8a40017e648c133188919a5a0105ce1916726dbc657fecb5ccb5d717c46d"
                        if capability == "topics" else None
                    ),
                } for index, component_id in enumerate(component_ids)],
                "config_sha256": "3" * 64,
                "r5_selection_sha256": "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3",
            })
        common_locator = {
            "type": "ARTIFACT_REVISION", "artifact_id": first_id,
            "revision_id": first_revision["revision_id"],
            "content_sha256": first_revision["revision_sha256"],
        }
        media_locators = [
            {"type": "TIME_INTERVAL", "start_seconds": 0.0, "end_seconds": 2.0},
            common_locator,
        ]
        studio = new_studio(
            registry, project_id=project_id, source_id=first_id,
            source_revision_id=first_revision["revision_id"], bindings=bindings,
            created_at=captured,
        )
        studio, video_artifact = register_artifact(
            studio, registry=registry, kind="MEDIA_PREPARATION", native_id="video",
            content_sha256="1" * 64, created_at=captured,
            capability="media_preparation", parents=[first_revision["revision_id"]],
            locators=media_locators, semantic_status="NOT_APPLICABLE",
        )
        studio, transcript_artifact = register_transcript(
            studio, registry=registry, native_id="transcript",
            content_sha256="2" * 64, created_at=captured, language="ru",
            word_count=2, confidence=0.95, locators=media_locators,
        )
        studio_entities = {item["artifact_id"]: item for item in studio["artifacts"]}
        component_bindings = studio["component_bindings"]

        def artifact_reference(artifact_id: str, kind: str) -> dict:
            entity = studio_entities[artifact_id]
            accepted = component_bindings[entity["capability"]]["components"][0]
            origin = {
                "component_id": accepted["component_id"],
                "repository": f"Yurielo/{accepted['component_id']}",
                "commit_sha": accepted["commit_sha"], "tree_sha": "b" * 40,
                "version": "1.0", "contracts": [accepted["contract_id"]],
                "runtime": {"kind": "python", "version": "3"},
            }
            if accepted["model_id"] is not None:
                origin["models"] = [{
                    "id": accepted["model_id"],
                    "identity_sha256": accepted["model_sha256"],
                }]
            return {
                "artifact_id": artifact_id, "kind": kind,
                "schema_id": "transcript_topic_studio_v1", "schema_version": "1.0",
                "semantic_status": entity["semantic_status"],
                "content_sha256": entity["content_sha256"], "size_bytes": 1,
                "storage_scope": "SOURCE_READ_ONLY", "relative_path": f"studio/{entity['native_id']}.json",
                "origin": origin,
                "provenance": {
                    "parent_artifact_ids": sorted(entity["parent_ids"]),
                    "operation_id": derive_imported_id(
                        "operation", "governance.alignment", entity["native_id"],
                        entity["content_sha256"],
                    ),
                    "source_locator": {
                        "native_id": entity["native_id"], "source_id": first_id,
                        "source_revision_id": first_revision["revision_id"],
                        "source_revision_sha256": first_revision["revision_sha256"],
                        "upstream_record_id": studio["studio_id"],
                        "upstream_record_sha256": studio["record_sha256"],
                        "upstream_entity_id": artifact_id,
                        "locators": entity["locators"],
                    },
                },
            }

        references = [
            artifact_reference(video_artifact, "VIDEO"),
            artifact_reference(transcript_artifact, "TRANSCRIPT"),
        ]
        upstream_records = [{
            "contract": "TRANSCRIPT_TOPIC_STUDIO_V1",
            "record_id": studio["studio_id"],
            "record_sha256": studio["record_sha256"],
            "record": studio,
        }]
        alignment = new_alignment(
            registry, project_id=project_id,
            source_revision_ids=[first_revision["revision_id"], second_revision["revision_id"]],
            artifact_references=references, upstream_records=upstream_records,
            created_at=captured,
        )
        alignment, video_node = add_alignment_node(
            alignment, registry=registry, upstream_records=upstream_records,
            native_id="video", kind="VIDEO",
            source_id=first_id, source_revision_id=first_revision["revision_id"],
            artifact_id=video_artifact, artifact_sha256="1" * 64,
            owner_component="videotext", locators=media_locators,
            lineage_ids=[first_revision["revision_id"], video_artifact],
            semantic_status="NOT_APPLICABLE",
            created_at=captured,
        )
        alignment, transcript_node = add_alignment_node(
            alignment, registry=registry, upstream_records=upstream_records,
            native_id="transcript", kind="TRANSCRIPT",
            source_id=first_id, source_revision_id=first_revision["revision_id"],
            artifact_id=transcript_artifact, artifact_sha256="2" * 64,
            owner_component="videotext", locators=media_locators,
            lineage_ids=[first_revision["revision_id"], transcript_artifact],
            semantic_status="PROVISIONAL",
            created_at=captured,
        )
        alignment, _ = add_alignment_link(
            alignment, registry=registry, upstream_records=upstream_records,
            native_id="video-transcript",
            relation="VIDEO_TO_TRANSCRIPT", from_node_id=video_node,
            to_node_id=transcript_node, evidence_node_ids=[video_node, transcript_node],
            confidence=0.95, conflict=False, method="governance_fixture",
            created_at=captured,
        )
        round_trip = loads_alignment(
            dumps_alignment(alignment, registry, upstream_records), registry,
            upstream_records,
        )
        validate_alignment(round_trip, registry, upstream_records)
        forward = navigate_alignment(
            round_trip, registry, upstream_records, video_node
        )["forward"]
        reverse = navigate_alignment(
            round_trip, registry, upstream_records, transcript_node
        )["reverse"]
        if (
            len(forward) != 1 or len(reverse) != 1
            or forward[0]["node_id"] != transcript_node
            or reverse[0]["node_id"] != video_node
            or round_trip["semantic_authority"] != "MACHINE_ALIGNMENT_REQUIRES_HUMAN_DECISION"
            or round_trip["source_artifacts_modified"] is not False
        ):
            errors.append("R8C executable alignment fixture differs")
    except Exception as error:
        errors.append(f"R8C executable alignment fixture failed: {error}")
    return errors


def validate_knowledge_integration_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "dependencies", "source_component",
        "product_rules_read", "implementation", "acceptance", "safety", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R9A knowledge integration evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 13):
        errors.append("R9A evidence must certify Issue #13 as ACCEPTED")
    if evidence.get("dependencies") != ["R6", "R8C", "TRANSCRIPT_AND_TOPIC_STUDIO_V1"]:
        errors.append("R9A dependency order differs")
    commits = {item["id"]: item["commit_sha"] for item in baselines["components"]}
    if evidence.get("source_component") != {"id": "seminartext", "commit_sha": commits["seminartext"]}:
        errors.append("R9A source component differs from accepted baseline")
    if evidence.get("product_rules_read") != [
        "PR-001", "PR-002", "PR-003", "PR-004", "PR-005", "PR-006", "PR-007", "PR-012"
    ]:
        errors.append("R9A applicable Product Rules evidence differs")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("R9A implementation reference differs")
            continue
        paths.append(item["path"])
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"R9A implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_KNOWLEDGE_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("R9A implementation inventory must be exact")
    if evidence.get("acceptance") != {
        "canonical_evidence_read_only": True,
        "canonical_knowledge_read_only": True,
        "substantive_claims_require_exact_evidence": True,
        "concepts_and_relations_exposed": True,
        "terms_preserve_labels_and_aliases": True,
        "practice_knowledge_preserved_as_source_concepts": True,
        "review_state_preserved": True,
        "machine_semantic_acceptance": False,
        "pinned_source_contracts_validated": True,
        "transcript_assurance_exposed": True,
        "public_reads_require_source_truth": True,
        "knowledge_graph_deterministic": True,
        "knowledge_diff_semantic_interpretation": False,
    }:
        errors.append("R9A acceptance evidence differs")
    if evidence.get("safety") != {
        "source_repositories_modified": False, "source_artifacts_modified": False,
        "protected_data_accessed": False, "gold_accessed": False,
        "semantic_authoring_performed": False, "domain_review_performed": False,
    }:
        errors.append("R9A safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("R9A limitations must be a non-empty unique list")
    return errors


def validate_media_integration_evidence(
    evidence: dict, baselines: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "dependencies", "source_component",
        "implementation", "acceptance", "safety", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R9B media integration evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 14):
        errors.append("R9B evidence must certify Issue #14 as ACCEPTED")
    if evidence.get("dependencies") != ["R5", "R6", "OPERATIONS_AND_DIAGNOSTICS_V1"]:
        errors.append("R9B dependency order differs")
    components = {item["id"]: item for item in baselines["components"]}
    videotext = components["videotext"]
    expected_source = {
        "id": "videotext", "commit_sha": videotext["commit_sha"],
        "tree_sha": videotext["tree_sha"], "version": videotext["version"],
    }
    if evidence.get("source_component") != expected_source:
        errors.append("R9B source component differs from accepted baseline")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("R9B implementation reference differs")
            continue
        paths.append(item["path"])
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"R9B implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_MEDIA_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("R9B implementation inventory must be exact")
    if evidence.get("acceptance") != {
        "all_required_capabilities_exposed": True,
        "artifact_integrity_reverified": True,
        "cancellation_owned_by_operations": True,
        "child_process_cleanup_owned_by_operations": True,
        "component_and_contracts_pinned": True,
        "configuration_and_models_bound": True,
        "derivative_output_independently_probed": True,
        "derivative_output_qa_artifact_bound": True,
        "durable_exact_execution_checkpoint_required": True,
        "external_inputs_content_bound": True,
        "external_input_bytes_reverified": True,
        "exact_videotext_functions_pinned": True,
        "published_schemas_closed": True,
        "knowledge_truth_immutable": True,
        "model_lifecycle_owned_by_operations": True,
        "models_remeasured_before_registration": True,
        "playlist_resource_scheduling_delegated": True,
        "progress_owned_by_operations": True,
        "recipe_serialization_deterministic": True,
        "recovery_owned_by_operations": True,
        "source_and_locator_bound": True,
    }:
        errors.append("R9B acceptance evidence differs")
    if evidence.get("safety") != {
        "external_actions_performed": False,
        "gold_accessed": False,
        "knowledge_artifacts_modified": False,
        "protected_data_accessed": False,
        "semantic_acceptance_performed": False,
        "source_projects_modified": False,
        "source_repositories_modified": False,
    }:
        errors.append("R9B safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("R9B limitations must be a non-empty unique list")
    return errors


def validate_cross_navigation_evidence(
    evidence: dict, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "status", "issue", "corrective_issues", "dependencies", "implementation",
        "surfaces", "acceptance", "safety", "limitations",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R9C cross-navigation evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 15):
        errors.append("R9C evidence must certify Issue #15 as ACCEPTED")
    if evidence.get("corrective_issues") != [61]:
        errors.append("R9C corrective Issue inventory differs")
    if evidence.get("dependencies") != ["R8C", "R9A", "R9B"]:
        errors.append("R9C dependency order differs")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("R9C implementation reference differs")
            continue
        paths.append(item["path"])
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"R9C implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_CROSS_NAVIGATION_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("R9C implementation inventory must be exact")
    if evidence.get("surfaces") != [
        "AUDIO", "DOCUMENT", "EVIDENCE", "KNOWLEDGE_ENTITY", "MEDIA_CLIP", "MEDIA_SOURCE",
        "PAGE", "SLIDE", "TOPIC", "TRANSCRIPT", "VIDEO", "WORD_TIMELINE",
    ]:
        errors.append("R9C navigation surface inventory differs")
    if evidence.get("acceptance") != {
        "validated_r8c_alignment_required": True,
        "validated_r9a_knowledge_required": True,
        "registered_r9b_derivative_required": True,
        "stable_ids_preserved": True,
        "exact_locators_preserved": True,
        "source_revision_mappings_required": True,
        "exact_project_source_coverage_required": True,
        "canonical_project_identity_binding_required": True,
        "partial_mapping_coverage_rejected": True,
        "multi_source_aggregate_actions_restricted": True,
        "authoritative_bridge_catalog_required": True,
        "authoritative_availability_catalog_required": True,
        "forward_and_reverse_navigation": True,
        "topic_to_word_timeline": True,
        "knowledge_to_evidence": True,
        "media_source_to_clip": True,
        "document_page_and_slide_actions": True,
        "unavailable_sources_fail_closed": True,
        "deterministic_serialization": True,
        "semantic_promotion_automatic": False,
    }:
        errors.append("R9C acceptance evidence differs")
    if evidence.get("safety") != {
        "source_artifacts_modified": False,
        "source_repositories_modified": False,
        "protected_data_accessed": False,
        "gold_accessed": False,
        "semantic_authoring_performed": False,
        "domain_review_performed": False,
        "external_actions_performed": False,
    }:
        errors.append("R9C safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("R9C limitations must be a non-empty unique list")
    return errors


def validate_obsidian_export_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_fields = {"schema_version", "status", "issue", "dependencies", "implementation", "acceptance", "safety", "limitations"}
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R10 Obsidian export evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 16):
        errors.append("R10 evidence must certify Issue #16 as ACCEPTED")
    if evidence.get("dependencies") != ["R9C"]:
        errors.append("R10 dependency order differs")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("R10 implementation reference differs")
            continue
        paths.append(item["path"])
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"R10 implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_OBSIDIAN_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("R10 implementation inventory must be exact")
    if evidence.get("acceptance") != {
        "complete_marker_written_last": True, "deterministic_package_identity": True,
        "exact_r9a_r9c_bindings": True, "immutable_version_promotion": True,
        "interruption_recovery": True, "managed_markdown_and_json": True,
        "preview_writes_nothing": True, "r6_source_export_revalidated": True,
        "project_lease_required": True,
        "shared_nonblocking_target_lock": True, "size_and_hash_verification": True,
        "symlink_and_traversal_rejected": True, "user_owned_collisions_fail_closed": True,
    }:
        errors.append("R10 acceptance evidence differs")
    if evidence.get("safety") != {
        "cloud_publication_performed": False, "external_actions_performed": False,
        "protected_data_accessed": False, "real_user_vault_accessed": False,
        "semantic_acceptance_performed": False, "source_artifacts_modified": False,
        "source_repositories_modified": False,
    }:
        errors.append("R10 safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("R10 limitations must be a non-empty unique list")
    return errors


def validate_onedrive_publication_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_fields = {"schema_version", "status", "issue", "dependencies", "implementation", "acceptance", "safety", "limitations"}
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["OneDrive publication evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 63):
        errors.append("OneDrive evidence must certify Issue #63 as ACCEPTED")
    if evidence.get("dependencies") != ["R10"]:
        errors.append("OneDrive dependency order differs")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("OneDrive implementation reference differs")
            continue
        paths.append(item["path"])
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"OneDrive implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_ONEDRIVE_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("OneDrive implementation inventory must be exact")
    if evidence.get("acceptance") != {
        "ambiguous_completion_fails_closed": True, "complete_marker_written_last": True,
        "conflict_copies_detected": True, "deterministic_package_identity": True,
        "files_on_demand_detected": True, "immutable_versions": True,
        "mutual_exclusion_with_obsidian": True, "offline_queueing": True,
        "outside_sync_staging": True, "physical_size_and_hash_verified": True,
        "project_lease_required": True, "verified_recovery": True,
    }:
        errors.append("OneDrive acceptance evidence differs")
    if evidence.get("safety") != {
        "cloud_publication_verified": False, "credentials_accessed": False,
        "external_actions_performed": False, "live_account_accessed": False,
        "microsoft_graph_used": False, "protected_data_accessed": False,
        "real_sync_root_accessed": False, "semantic_acceptance_performed": False,
        "source_artifacts_modified": False, "source_repositories_modified": False,
    }:
        errors.append("OneDrive safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("OneDrive limitations must be a non-empty unique list")
    return errors


def validate_native_macos_app_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_fields = {"schema_version", "status", "issue", "dependencies", "implementation", "acceptance", "reference_mac", "safety", "limitations"}
    if not isinstance(evidence, dict) or set(evidence) != expected_fields:
        return ["R12 native macOS evidence fields must match v1"]
    if (evidence.get("schema_version"), evidence.get("status"), evidence.get("issue")) != ("1.0", "ACCEPTED", 28):
        errors.append("R12 evidence must certify Issue #28 as ACCEPTED")
    if evidence.get("dependencies") != ["ONEDRIVE_PUBLICATION_V1"]:
        errors.append("R12 dependency order differs")
    paths = []
    for item in evidence.get("implementation", []):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append("R12 implementation reference differs"); continue
        paths.append(item["path"]); path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"R12 implementation hash differs: {item['path']}")
    if set(paths) != EXPECTED_NATIVE_MACOS_APP_IMPLEMENTATION or len(paths) != len(set(paths)):
        errors.append("R12 implementation inventory must be exact")
    if evidence.get("acceptance") != {
        "appkit_native_ui": True, "buildable_without_full_xcode": True,
        "closed_local_bridge": True, "controlled_local_publication_tested": True,
        "create_and_open_project_tested": True, "deferred_actions_unavailable": True,
        "deterministic_source_first_workflow": True, "exact_navigation_visible": True,
        "last_window_close_terminates_app": True,
        "launch_probe_passed": True, "persisted_job_inspection_tested": True,
        "approved_app_icon_hash_verified": True,
        "bundle_icon_verified": True, "deterministic_icon_generation": True,
        "dock_icon_verified": True, "finder_icon_verified": True,
        "cmdtab_icon_verified": True, "small_size_assets_verified": True,
        "onedrive_preview_visible": True,
        "operations_diagnostics_visible": True, "obsidian_preview_visible": True,
        "required_surfaces_visible": True,
    }:
        errors.append("R12 acceptance evidence differs")
    if evidence.get("reference_mac") != {
        "architecture": "arm64", "macos_version": "26.5.2", "swift_version": "6.3.3",
        "build_result": "PASS", "launch_result": "PASS",
    }:
        errors.append("R12 reference Mac evidence differs")
    if evidence.get("safety") != {
        "credentials_accessed": False, "external_actions_performed": False,
        "live_publication_performed": False, "private_data_accessed": False,
        "real_onedrive_accessed": True, "real_vault_accessed": False,
        "release_performed": False, "semantic_acceptance_performed": False,
        "signed_or_notarized_for_distribution": False, "source_repositories_modified": False,
    }:
        errors.append("R12 safety evidence differs")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not limitations or len(limitations) != len(set(limitations)):
        errors.append("R12 limitations must be a non-empty unique list")
    return errors

def validate_ready_app_evidence(evidence: dict, root: Path = ROOT) -> list[str]:
    errors=[]
    fields={"schema_version","status","issue","dependencies","implementation","acceptance","safety","limitations"}
    if not isinstance(evidence,dict) or set(evidence)!=fields: return ["R13 evidence fields must match v1"]
    if (evidence.get("schema_version"),evidence.get("status"),evidence.get("issue")) != ("1.0","ACCEPTED",29): errors.append("R13 must certify Issue #29")
    if evidence.get("dependencies") != ["R12"]: errors.append("R13 dependency differs")
    paths=[]
    for item in evidence.get("implementation",[]):
        if not isinstance(item,dict) or set(item)!={"path","sha256"}: errors.append("R13 implementation reference differs"); continue
        paths.append(item["path"]); path=root/item["path"]
        if not path.is_file() or sha256_file(path)!=item["sha256"]: errors.append(f"R13 implementation hash differs: {item['path']}")
    if set(paths)!=EXPECTED_READY_APP_IMPLEMENTATION or len(paths)!=len(set(paths)): errors.append("R13 implementation inventory must be exact")
    expected_acceptance={"backup_verification":True,"bridge_path_redaction":True,"bundle_identifier_final":True,"dependency_preflight":True,"local_ad_hoc_seal_verified":True,"minimum_macos_declared":True,"reproducible_tree_hash":True,"self_test_passed":True}
    if evidence.get("acceptance")!=expected_acceptance: errors.append("R13 acceptance differs")
    expected_safety={"credentials_accessed":False,"developer_id_used":False,"external_actions_performed":False,"notarization_performed":False,"private_data_accessed":False,"public_distribution_performed":False,"real_user_data_used":False}
    if evidence.get("safety")!=expected_safety: errors.append("R13 safety differs")
    if not isinstance(evidence.get("limitations"),list) or not evidence["limitations"]: errors.append("R13 limitations required")
    return errors


def main() -> int:
    state = load_json(STATE_PATH)
    baselines = load_json(BASELINES_PATH)
    ownership = load_json(OWNERSHIP_PATH)
    worker_protocol = load_json(WORKER_PROTOCOL_PATH)
    adapter_spike = load_json(ADAPTER_SPIKE_PATH)
    capability_benchmark = load_json(CAPABILITY_BENCHMARK_PATH)
    agent_team = load_registry(AGENT_TEAM_PATH)
    core_alpha = load_json(CORE_ALPHA_PATH)
    core_alpha_real = load_json(CORE_ALPHA_REAL_PATH)
    operations = load_json(OPERATIONS_PATH)
    migration = load_json(MIGRATION_PATH)
    playlist = load_json(PLAYLIST_PATH)
    document_pipeline = load_json(DOCUMENT_PIPELINE_PATH)
    projects_sources = load_json(PROJECTS_SOURCES_PATH)
    transcript_topic_studio = load_json(TRANSCRIPT_TOPIC_STUDIO_PATH)
    multi_source_alignment = load_json(MULTI_SOURCE_ALIGNMENT_PATH)
    knowledge_integration = load_json(KNOWLEDGE_INTEGRATION_PATH)
    media_integration = load_json(MEDIA_INTEGRATION_PATH)
    cross_navigation = load_json(CROSS_NAVIGATION_PATH)
    obsidian_export = load_json(OBSIDIAN_EXPORT_PATH)
    onedrive_publication = load_json(ONEDRIVE_PUBLICATION_PATH)
    native_macos_app = load_json(NATIVE_MACOS_APP_PATH)
    ready_app = load_json(READY_APP_PATH)
    load_json(SCHEMA_PATH)
    load_json(BASELINES_SCHEMA_PATH)
    load_json(OWNERSHIP_SCHEMA_PATH)
    load_json(LEASE_SCHEMA_PATH)
    load_json(WORKER_PROTOCOL_SCHEMA_PATH)
    load_json(ARTIFACT_REFERENCE_SCHEMA_PATH)
    load_json(COMPONENT_IDENTITY_SCHEMA_PATH)
    load_json(ADAPTER_SPIKE_SCHEMA_PATH)
    load_json(ADAPTER_REPORT_SCHEMA_PATH)
    load_json(CAPABILITY_BENCHMARK_SCHEMA_PATH)
    load_json(AGENT_TEAM_SCHEMA_PATH)
    load_json(CORE_ALPHA_EVIDENCE_SCHEMA_PATH)
    load_json(CORE_ALPHA_MANIFEST_SCHEMA_PATH)
    load_json(CORE_ALPHA_REAL_SCHEMA_PATH)
    load_json(OPERATIONS_SCHEMA_PATH)
    load_json(MIGRATION_SCHEMA_PATH)
    load_json(PLAYLIST_SCHEMA_PATH)
    load_json(DOCUMENT_PIPELINE_SCHEMA_PATH)
    load_json(PROJECTS_SOURCES_SCHEMA_PATH)
    load_json(PROJECT_SOURCE_REGISTRY_SCHEMA_PATH)
    load_json(TRANSCRIPT_TOPIC_STUDIO_EVIDENCE_SCHEMA_PATH)
    load_json(TRANSCRIPT_TOPIC_STUDIO_SCHEMA_PATH)
    load_json(MULTI_SOURCE_ALIGNMENT_EVIDENCE_SCHEMA_PATH)
    load_json(MULTI_SOURCE_ALIGNMENT_SCHEMA_PATH)
    load_json(KNOWLEDGE_INTEGRATION_EVIDENCE_SCHEMA_PATH)
    load_json(KNOWLEDGE_VIEW_SCHEMA_PATH)
    load_json(MEDIA_INTEGRATION_EVIDENCE_SCHEMA_PATH)
    load_json(MEDIA_RECIPE_SCHEMA_PATH)
    load_json(MEDIA_DERIVATIVE_SCHEMA_PATH)
    load_json(CROSS_NAVIGATION_EVIDENCE_SCHEMA_PATH)
    load_json(CROSS_NAVIGATION_SCHEMA_PATH)
    load_json(OBSIDIAN_EXPORT_EVIDENCE_SCHEMA_PATH)
    load_json(OBSIDIAN_PACKAGE_SCHEMA_PATH)
    load_json(OBSIDIAN_RECEIPT_SCHEMA_PATH)
    load_json(ONEDRIVE_EVIDENCE_SCHEMA_PATH)
    load_json(ONEDRIVE_PACKAGE_SCHEMA_PATH)
    load_json(ONEDRIVE_RECEIPT_SCHEMA_PATH)
    load_json(NATIVE_MACOS_APP_SCHEMA_PATH)
    load_json(READY_APP_SCHEMA_PATH)
    load_json(ROOT / "schemas/youtube_playlist_snapshot_v1.schema.json")
    load_json(ROOT / "schemas/youtube_playlist_plan_v1.schema.json")
    load_json(ROOT / "schemas/youtube_playlist_checkpoint_v1.schema.json")
    load_json(ROOT / "schemas/youtube_playlist_refresh_v1.schema.json")
    load_json(ROOT / "schemas/document_extraction_v1.schema.json")
    errors = (
        validate_state(state)
        + validate_component_baselines(baselines)
        + validate_data_ownership(ownership)
        + validate_worker_protocol(worker_protocol)
        + validate_adapter_spike(adapter_spike, baselines)
        + validate_capability_benchmark(capability_benchmark, baselines)
        + validate_agent_team(agent_team)
        + validate_core_alpha_evidence(core_alpha)
        + validate_core_alpha_real_evidence(core_alpha_real, baselines)
        + validate_operations_evidence(operations)
        + validate_migration_evidence(migration, baselines)
        + validate_playlist_evidence(playlist)
        + validate_document_pipeline_evidence(document_pipeline)
        + validate_projects_sources_evidence(projects_sources)
        + validate_transcript_topic_studio_evidence(transcript_topic_studio, baselines)
        + validate_multi_source_alignment_evidence(multi_source_alignment, baselines)
        + validate_knowledge_integration_evidence(knowledge_integration, baselines)
        + validate_media_integration_evidence(media_integration, baselines)
        + validate_cross_navigation_evidence(cross_navigation)
        + validate_obsidian_export_evidence(obsidian_export)
        + validate_onedrive_publication_evidence(onedrive_publication)
        + validate_native_macos_app_evidence(native_macos_app)
        + validate_ready_app_evidence(ready_app)
    )
    if errors:
        print("INTEGRA_GOVERNANCE_VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("INTEGRA_GOVERNANCE_VALIDATION: PASS")
    print(f"ROADMAP_ITEMS: {len(state['roadmap'])}")
    print(f"DELIVERY_TARGET: {state['delivery_target']['id']}")
    print(f"REQUIRED_MODULES: {len(state['release_scope']['required_modules'])}")
    print(f"DEFERRED_MODULES: {len(state['release_scope']['deferred_modules'])}")
    print(
        "DEFERRED_SOCIAL_PLATFORMS: "
        f"{len(state['release_scope']['deferred_social_platforms'])}"
    )
    print("STANDALONE_PRODUCTS_PRESERVED: YES")
    print(f"PINNED_COMPONENTS: {len(baselines['components'])}")
    print(f"R1_ACCEPTANCE: {baselines['r1_acceptance']['status']}")
    print(f"R2_OWNERSHIP_ENTRIES: {len(ownership['ownership'])}")
    print("R2_PROJECT_LEASE: DEFINED")
    print("R3_WORKER_PROTOCOL: ACCEPTED")
    print(f"R3_PROTOCOL_FIXTURES: {len(worker_protocol['fixtures'])}")
    print(f"R4_ADAPTER_SPIKE: {adapter_spike['status']}")
    print(f"R4_COMPONENT_PROBES: {len(adapter_spike['components'])}")
    print(f"R5_CAPABILITY_BENCHMARK: {capability_benchmark['status']}")
    print(f"R5_CAPABILITY_GROUPS: {len(capability_benchmark['capabilities'])}")
    print(f"AGENT_TEAM_ROLES: {len(agent_team['roles'])}")
    print(f"LEAD_AGENT: {agent_team['lead_agent']}")
    print(f"R6_CONTRACT_REPLAY: {core_alpha['status']}")
    print(f"R6_REPLAY_EXECUTION_MODE: {core_alpha['execution_mode']}")
    print(f"R6_REAL_MEDIA: {core_alpha_real['status']}")
    print("R6_ACCEPTANCE: ACCEPTED")
    print(f"OPERATIONS_AND_DIAGNOSTICS_V1: {operations['status']}")
    print(f"R7_MIGRATION: {migration['status']}")
    print(f"R8A_YOUTUBE_PLAYLIST: {playlist['status']}")
    print(f"R8B_DOCUMENT_AND_OCR: {document_pipeline['status']}")
    print(f"PROJECTS_AND_SOURCES_V1: {projects_sources['status']}")
    print(f"TRANSCRIPT_AND_TOPIC_STUDIO_V1: {transcript_topic_studio['status']}")
    print(f"R8C_MULTI_SOURCE_ALIGNMENT: {multi_source_alignment['status']}")
    print(f"R9A_KNOWLEDGE_INTEGRATION: {knowledge_integration['status']}")
    print(f"R9B_MEDIA_INTEGRATION: {media_integration['status']}")
    print(f"R9C_CROSS_NAVIGATION: {cross_navigation['status']}")
    print(f"ONEDRIVE_PUBLICATION_V1: {onedrive_publication['status']}")
    print(f"R12_NATIVE_MACOS_APP: {native_macos_app['status']}")
    print(f"R13_READY_APP_PACKAGE: {ready_app['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
