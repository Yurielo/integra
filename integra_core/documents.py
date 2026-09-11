"""Deterministic document, presentation, embedded-media and OCR contracts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Callable
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .identity import derive_imported_id
from .protocol import content_sha256


class DocumentError(RuntimeError):
    """Raised when document bytes, locators, or extraction evidence differ."""


OcrProvider = Callable[[dict[str, Any]], dict[str, Any]]
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 64 * 1024 * 1024
MAX_DECODED_IMAGE_BYTES = 128 * 1024 * 1024
MAX_IMAGE_DIMENSION = 100_000
MAX_IMAGE_PIXELS = 100_000_000
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
FORMAT_BY_SUFFIX = {
    ".txt": ("TXT", "text/plain"),
    ".md": ("MARKDOWN", "text/markdown"),
    ".markdown": ("MARKDOWN", "text/markdown"),
    ".docx": (
        "DOCX",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".pptx": (
        "PPTX",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".pdf": ("PDF", "application/pdf"),
    ".png": ("IMAGE", "image/png"),
    ".jpg": ("IMAGE", "image/jpeg"),
    ".jpeg": ("IMAGE", "image/jpeg"),
    ".tif": ("IMAGE", "image/tiff"),
    ".tiff": ("IMAGE", "image/tiff"),
}


def extract_document(
    source_path: Path,
    *,
    captured_at: str,
    ocr_provider: OcrProvider | None = None,
) -> dict[str, Any]:
    """Extract one local source without changing it or claiming semantic truth."""

    captured_at = _timestamp(captured_at)
    path = Path(source_path)
    source_bytes = _read_regular_file(path)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_format, media_type = _detect_format(path, source_bytes)
    source_identity = content_sha256(
        {"component": "integra.document_source", "sha256": source_sha256}
    )
    source_id = derive_imported_id(
        "source", "integra.document_source", source_sha256, source_identity
    )
    revision_id = derive_imported_id(
        "revision", "integra.document_source", source_id, source_sha256
    )

    native_blocks, embedded, page_count, native_status = _native_from_source(
        source_format, source_bytes, source_sha256
    )
    image_count = 1 if source_format == "IMAGE" else len(embedded)

    native_characters = sum(len(item["text"]) for item in native_blocks)
    if source_format == "IMAGE":
        content_mode = "SCAN"
        ocr_reason = "IMAGE_SOURCE"
    elif source_format in {"PDF", "PPTX", "DOCX"} and image_count and native_characters < 80 * (page_count or 1):
        content_mode = "IMAGE_HEAVY"
        ocr_reason = "IMAGE_HEAVY_PDF" if source_format == "PDF" else "IMAGE_HEAVY_DOCUMENT"
    elif source_format == "PDF" and native_status != "COMPLETE":
        content_mode = "IMAGE_HEAVY"
        ocr_reason = "UNSUPPORTED_PDF_TEXT_ENCODING"
    elif embedded:
        content_mode = "MIXED"
        ocr_reason = "NONE"
    else:
        content_mode = "TEXT"
        ocr_reason = "NONE"

    ocr_required = content_mode in {"SCAN", "IMAGE_HEAVY"}
    ocr_blocks: list[dict[str, Any]] = []
    if ocr_required and ocr_provider is not None:
        request = {
            "schema_version": "1.0",
            "source_sha256": source_sha256,
            "source_format": source_format,
            "media_type": media_type,
            "page_count": page_count or 1,
            "reason": ocr_reason,
            "source_bytes": source_bytes,
        }
        raw_ocr = ocr_provider(request)
        ocr_provider_identity, ocr_blocks = _normalize_ocr(
            raw_ocr, source_sha256, source_format, page_count or 1
        )
        ocr_status = "COMPLETE"
    elif ocr_required:
        ocr_status = "REQUIRED"
        ocr_provider_identity = None
    else:
        ocr_status = "NOT_REQUIRED"
        ocr_provider_identity = None

    document_id = derive_imported_id(
        "artifact", "integra.document", source_id, source_sha256
    )
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "document_id": document_id,
        "source": {
            "source_id": source_id,
            "revision_id": revision_id,
            "display_name": path.name,
            "format": source_format,
            "media_type": media_type,
            "sha256": source_sha256,
            "size_bytes": len(source_bytes),
        },
        "captured_at": captured_at,
        "page_or_slide_count": page_count,
        "content_mode": content_mode,
        "native_extraction": {
            "status": native_status,
            "text_characters": native_characters,
            "blocks": native_blocks,
        },
        "ocr": {
            "status": ocr_status,
            "reason": ocr_reason,
            "provider": ocr_provider_identity,
            "blocks": ocr_blocks,
        },
        "embedded_media": embedded,
        "fidelity": {
            "source_hash_verified": True,
            "exact_locators": True,
            "embedded_media_hashes_verified": True,
            "image_heavy_not_plain_text": content_mode not in {"SCAN", "IMAGE_HEAVY"}
            or ocr_status in {"REQUIRED", "COMPLETE"},
            "semantic_authority": "PROVISIONAL_MACHINE_EXTRACTION",
        },
    }
    record["record_sha256"] = content_sha256(record)
    validate_document_record(record)
    validate_document_against_source(record, path)
    return record


def validate_document_record(record: dict[str, Any]) -> None:
    required = {
        "schema_version", "document_id", "source", "captured_at",
        "page_or_slide_count", "content_mode", "native_extraction", "ocr",
        "embedded_media", "fidelity", "record_sha256",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise DocumentError("document record differs from v1")
    if record["schema_version"] != "1.0":
        raise DocumentError("document schema version is unsupported")
    _timestamp(record["captured_at"])
    source = record["source"]
    if not isinstance(source, dict) or set(source) != {
        "source_id", "revision_id", "display_name", "format", "media_type",
        "sha256", "size_bytes",
    }:
        raise DocumentError("document source differs from v1")
    if source["format"] not in {value[0] for value in FORMAT_BY_SUFFIX.values()}:
        raise DocumentError("document source format is unsupported")
    if not isinstance(source["display_name"], str) or not source["display_name"]:
        raise DocumentError("document display name is required")
    _digest(source["sha256"])
    _nonnegative_integer(source["size_bytes"], "source size")
    source_identity = content_sha256(
        {"component": "integra.document_source", "sha256": source["sha256"]}
    )
    expected_source_id = derive_imported_id(
        "source", "integra.document_source", source["sha256"], source_identity
    )
    if source["source_id"] != expected_source_id:
        raise DocumentError("document source identity differs")
    if source["revision_id"] != derive_imported_id(
        "revision", "integra.document_source", source["source_id"], source["sha256"]
    ):
        raise DocumentError("document revision identity differs")
    if record["document_id"] != derive_imported_id(
        "artifact", "integra.document", source["source_id"], source["sha256"]
    ):
        raise DocumentError("document artifact identity differs")
    count = record["page_or_slide_count"]
    if count is not None:
        _positive_integer(count, "page or slide count")
    if record["content_mode"] not in {"TEXT", "MIXED", "IMAGE_HEAVY", "SCAN"}:
        raise DocumentError("document content mode differs")

    native = record["native_extraction"]
    if not isinstance(native, dict) or set(native) != {"status", "text_characters", "blocks"}:
        raise DocumentError("native extraction differs from v1")
    if native["status"] not in {"COMPLETE", "PARTIAL_UNSUPPORTED_ENCODING", "NOT_APPLICABLE"}:
        raise DocumentError("native extraction status differs")
    _nonnegative_integer(native["text_characters"], "native character count")
    _validate_blocks(native["blocks"], source["sha256"], "NATIVE")
    if native["text_characters"] != sum(len(item["text"]) for item in native["blocks"]):
        raise DocumentError("native character count differs")

    ocr = record["ocr"]
    if not isinstance(ocr, dict) or set(ocr) != {"status", "reason", "provider", "blocks"}:
        raise DocumentError("OCR record differs from v1")
    if ocr["status"] not in {"NOT_REQUIRED", "REQUIRED", "COMPLETE"}:
        raise DocumentError("OCR status differs")
    if ocr["reason"] not in {
        "NONE", "IMAGE_SOURCE", "IMAGE_HEAVY_PDF", "IMAGE_HEAVY_DOCUMENT",
        "UNSUPPORTED_PDF_TEXT_ENCODING",
    }:
        raise DocumentError("OCR reason differs")
    _validate_blocks(ocr["blocks"], source["sha256"], "OCR")
    if ocr["provider"] is not None:
        _validate_ocr_provider(ocr["provider"])
    if ocr["status"] == "COMPLETE" and not ocr["blocks"]:
        raise DocumentError("completed OCR requires blocks")
    if ocr["status"] == "COMPLETE" and ocr["provider"] is None:
        raise DocumentError("completed OCR requires provider provenance")
    if ocr["status"] != "COMPLETE" and ocr["blocks"]:
        raise DocumentError("non-complete OCR cannot contain blocks")
    if ocr["status"] != "COMPLETE" and ocr["provider"] is not None:
        raise DocumentError("non-complete OCR cannot claim a provider")
    visual = record["content_mode"] in {"IMAGE_HEAVY", "SCAN"}
    if visual and ocr["status"] not in {"REQUIRED", "COMPLETE"}:
        raise DocumentError("visual content must retain explicit OCR state")
    expected_mode, expected_reason = _expected_mode_and_ocr_reason(record)
    if record["content_mode"] != expected_mode or ocr["reason"] != expected_reason:
        raise DocumentError("content mode or OCR reason differs from extraction evidence")
    if expected_reason == "NONE" and ocr["status"] != "NOT_REQUIRED":
        raise DocumentError("ordinary native text cannot claim OCR completion")
    _validate_format_locators(record)

    if not isinstance(record["embedded_media"], list):
        raise DocumentError("embedded media must be a list")
    media_ids: set[str] = set()
    part_paths: set[str] = set()
    for item in record["embedded_media"]:
        _validate_media(item, source["sha256"])
        if item["media_id"] in media_ids or item["part_path"] in part_paths:
            raise DocumentError("embedded media identity or part path is duplicated")
        media_ids.add(item["media_id"])
        part_paths.add(item["part_path"])

    fidelity = record["fidelity"]
    if not isinstance(fidelity, dict) or fidelity != {
        "source_hash_verified": True,
        "exact_locators": True,
        "embedded_media_hashes_verified": True,
        "image_heavy_not_plain_text": True,
        "semantic_authority": "PROVISIONAL_MACHINE_EXTRACTION",
    }:
        raise DocumentError("document fidelity claims differ from v1")
    identity = dict(record)
    supplied = identity.pop("record_sha256")
    _digest(supplied)
    if supplied != content_sha256(identity):
        raise DocumentError("document record hash differs")


def validate_document_against_source(record: dict[str, Any], source_path: Path) -> None:
    validate_document_record(record)
    path = Path(source_path)
    source_bytes = _read_regular_file(path)
    source = record["source"]
    if source["display_name"] != path.name:
        raise DocumentError("document source display name differs from source path")
    if len(source_bytes) != source["size_bytes"]:
        raise DocumentError("document source size changed")
    if hashlib.sha256(source_bytes).hexdigest() != source["sha256"]:
        raise DocumentError("document source bytes changed")
    source_format, media_type = _detect_format(path, source_bytes)
    if (source_format, media_type) != (source["format"], source["media_type"]):
        raise DocumentError("document source type changed")
    expected_blocks, expected_embedded, expected_count, expected_status = _native_from_source(
        source_format, source_bytes, source["sha256"]
    )
    if record["native_extraction"] != {
        "status": expected_status,
        "text_characters": sum(len(item["text"]) for item in expected_blocks),
        "blocks": expected_blocks,
    }:
        raise DocumentError("native extraction differs from source bytes")
    if record["page_or_slide_count"] != expected_count:
        raise DocumentError("page or slide count differs from source bytes")
    if record["embedded_media"] != expected_embedded:
        raise DocumentError("embedded media inventory differs from source bytes")
    expected_media = _embedded_payloads(source_format, source_bytes)
    for item in record["embedded_media"]:
        payload = expected_media.get(item["part_path"])
        if payload is None:
            raise DocumentError("embedded media part is missing from source")
        if len(payload) != item["size_bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise DocumentError("embedded media bytes changed")


def materialize_embedded_media(
    record: dict[str, Any], source_path: Path, output_root: Path
) -> list[dict[str, Any]]:
    """Copy verified embedded bytes into a new Integra-owned directory without overwrite."""

    validate_document_against_source(record, source_path)
    root = _validate_new_output_root(Path(output_root))
    directory_chain, chain_entries = _open_directory_chain(root.parent)
    parent_fd = directory_chain[-1]
    root_fd: int | None = None
    try:
        _assert_directory_chain(directory_chain, chain_entries)
        os.mkdir(root.name, mode=0o700, dir_fd=parent_fd)
        root_fd = os.open(root.name, _directory_open_flags(), dir_fd=parent_fd)
        created = os.fstat(root_fd)
        _assert_directory_entry(parent_fd, root.name, created)

        source_bytes = _read_regular_file(Path(source_path))
        if (
            len(source_bytes) != record["source"]["size_bytes"]
            or hashlib.sha256(source_bytes).hexdigest() != record["source"]["sha256"]
        ):
            raise DocumentError("document source changed before media materialization")
        payloads = _embedded_payloads(record["source"]["format"], source_bytes)
        written: list[dict[str, Any]] = []
        for item in record["embedded_media"]:
            extension = _extension_for_media_type(item["media_type"])
            relative_path = f"{item['media_id'].rsplit(':', 1)[-1]}{extension}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(relative_path, flags, 0o600, dir_fd=root_fd)
            try:
                payload = payloads[item["part_path"]]
                with os.fdopen(fd, "wb", closefd=False) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                os.close(fd)
            if _read_regular_at(root_fd, relative_path) != payload:
                raise DocumentError("materialized embedded media bytes differ")
            written.append(
                {
                    "media_id": item["media_id"],
                    "relative_path": relative_path,
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
            )
        _assert_directory_chain(directory_chain, chain_entries)
        _assert_directory_entry(parent_fd, root.name, created)
        return written
    except OSError as exc:
        raise DocumentError("embedded media materialization failed closed") from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
        for descriptor in reversed(directory_chain):
            os.close(descriptor)


def _native_from_source(
    source_format: str, source_bytes: bytes, source_sha256: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None, str]:
    if source_format in {"TXT", "MARKDOWN"}:
        text = _decode_utf8(source_bytes)
        blocks = (
            [_block(source_sha256, "DOCUMENT", 1, None, text, "NATIVE", 0)]
            if text
            else []
        )
        return blocks, [], None, "COMPLETE"
    if source_format == "DOCX":
        blocks, media = _extract_docx(source_bytes, source_sha256)
        return blocks, media, None, "COMPLETE"
    if source_format == "PPTX":
        blocks, media, count = _extract_pptx(source_bytes, source_sha256)
        return blocks, media, count, "COMPLETE"
    if source_format == "PDF":
        return _extract_pdf(source_bytes, source_sha256)
    if source_format == "IMAGE":
        return [], [], 1, "NOT_APPLICABLE"
    raise DocumentError("document source format is unsupported")


def _extract_docx(data: bytes, source_sha256: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    members = _safe_zip(data, "DOCX")
    document = members.get("word/document.xml")
    if document is None:
        raise DocumentError("DOCX document.xml is missing")
    root = _xml(document, "DOCX document")
    blocks: list[dict[str, Any]] = []
    paragraph_index = 0
    for node in root.iter():
        if _local(node.tag) == "p":
            paragraph_index += 1
            text = _ooxml_text(node)
            if text:
                blocks.append(
                    _block(
                        source_sha256,
                        "PARAGRAPH",
                        paragraph_index,
                        None,
                        text,
                        "NATIVE",
                        0,
                    )
                )
    media = _office_media(members, source_sha256, "DOCX")
    return blocks, media


def _extract_pptx(
    data: bytes, source_sha256: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    members = _safe_zip(data, "PPTX")
    slide_paths = _pptx_slide_order(members)
    if not slide_paths:
        raise DocumentError("PPTX contains no slides")
    blocks: list[dict[str, Any]] = []
    for slide_index, name in enumerate(slide_paths, 1):
        root = _xml(members[name], "PPTX slide")
        text = _ooxml_text(root, separator="\n")
        if text:
            blocks.append(_block(source_sha256, "SLIDE", slide_index, None, text, "NATIVE", 0))
        notes_name = _related_part(
            members,
            name,
            relation_type_suffix="/notesSlide",
        )
        if notes_name is not None and notes_name in members:
            notes_root = _xml(members[notes_name], "PPTX notes")
            notes = _ooxml_text(notes_root, separator="\n")
            if notes:
                blocks.append(_block(source_sha256, "SLIDE_NOTES", slide_index, None, notes, "NATIVE", 0))
    media = _office_media(members, source_sha256, "PPTX")
    return blocks, media, len(slide_paths)


def _extract_pdf(
    data: bytes, source_sha256: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, str]:
    objects = _pdf_objects(data)
    pages = [(number, objects[number]) for number in _pdf_page_order(objects)]
    if not pages:
        raise DocumentError("PDF contains no page objects")
    blocks: list[dict[str, Any]] = []
    unsupported = False
    for page_index, (_, body) in enumerate(pages, 1):
        refs = []
        single = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", body)
        array = re.search(rb"/Contents\s*\[(.*?)\]", body, re.S)
        if single:
            refs.append(int(single.group(1)))
        if array:
            refs.extend(int(value) for value in re.findall(rb"(\d+)\s+\d+\s+R", array.group(1)))
        if b"/Contents" in body and not refs:
            unsupported = True
        chunks: list[str] = []
        for ref in refs:
            stream_body = objects.get(ref)
            if stream_body is None:
                unsupported = True
                continue
            if b"/Filter" in stream_body:
                unsupported = True
                continue
            stream = _pdf_stream(stream_body)
            if stream is None:
                unsupported = True
                continue
            extracted, complete = _pdf_text_strings(stream)
            chunks.extend(extracted)
            if not complete:
                unsupported = True
        text = " ".join(chunk for chunk in chunks if chunk)
        if text:
            blocks.append(_block(source_sha256, "PAGE", page_index, None, text, "NATIVE", 0))
    embedded = []
    for object_number, body in sorted(objects.items()):
        if not re.search(rb"/Subtype\s*/Image\b", body):
            continue
        payload = _pdf_stream(body)
        if payload is None:
            raise DocumentError("PDF image object has no stream")
        media_type = "application/octet-stream"
        if b"/DCTDecode" in body:
            media_type = "image/jpeg"
        elif b"/JPXDecode" in body:
            media_type = "image/jp2"
        part_path = f"pdf/object-{object_number}"
        embedded.append(_media(source_sha256, part_path, media_type, payload, "PDF_OBJECT", object_number))
    if not blocks:
        unsupported = True
    status = "PARTIAL_UNSUPPORTED_ENCODING" if unsupported else "COMPLETE"
    return blocks, embedded, len(pages), status


def _normalize_ocr(
    raw: Any, source_sha256: str, source_format: str, page_count: int
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not isinstance(raw, dict) or set(raw) != {"provider", "blocks"}:
        raise DocumentError("OCR adapter result differs from v1")
    provider = raw["provider"]
    _validate_ocr_provider(provider)
    raw_blocks = raw["blocks"]
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise DocumentError("OCR adapter must return at least one region")
    blocks = []
    for index, item in enumerate(raw_blocks):
        if not isinstance(item, dict) or set(item) != {
            "unit_kind", "unit_index", "region", "text", "confidence"
        }:
            raise DocumentError("OCR region differs from v1")
        expected_kind = {
            "IMAGE": "IMAGE",
            "PDF": "PAGE",
            "PPTX": "SLIDE",
            "DOCX": "DOCUMENT",
        }.get(source_format)
        if expected_kind is None:
            raise DocumentError("OCR is not applicable to this source format")
        if item["unit_kind"] != expected_kind:
            raise DocumentError("OCR unit kind differs from source")
        _positive_integer(item["unit_index"], "OCR unit index")
        if item["unit_index"] > page_count:
            raise DocumentError("OCR unit index is outside source")
        region = _region(item["region"])
        text = item["text"]
        if not isinstance(text, str) or not text:
            raise DocumentError("OCR text is required")
        confidence = item["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise DocumentError("OCR confidence is invalid")
        block = _block(source_sha256, expected_kind, item["unit_index"], region, text, "OCR", index)
        block["confidence"] = float(confidence)
        blocks.append(block)
    covered_units = {item["locator"]["unit_index"] for item in blocks}
    if covered_units != set(range(1, page_count + 1)):
        raise DocumentError("OCR result does not cover every required page or image")
    return dict(provider), blocks


def _block(
    source_sha256: str,
    unit_kind: str,
    unit_index: int,
    region: dict[str, float] | None,
    text: str,
    method: str,
    ordinal: int,
) -> dict[str, Any]:
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    locator = {
        "unit_kind": unit_kind,
        "unit_index": unit_index,
        "region": region,
        "character_start": 0,
        "character_end": len(text),
    }
    native_id = content_sha256(
        {"method": method, "locator": locator, "text_sha256": text_sha256, "ordinal": ordinal}
    )
    block = {
        "block_id": derive_imported_id("artifact", "integra.document_block", native_id, source_sha256),
        "text": text,
        "text_sha256": text_sha256,
        "extraction_method": method,
        "locator": locator,
    }
    if method == "OCR":
        block["confidence"] = None
    return block


def _validate_blocks(blocks: Any, source_sha256: str, expected_method: str) -> None:
    if not isinstance(blocks, list):
        raise DocumentError("document blocks must be a list")
    ids: set[str] = set()
    for ordinal, item in enumerate(blocks):
        keys = {"block_id", "text", "text_sha256", "extraction_method", "locator"}
        if expected_method == "OCR":
            keys.add("confidence")
        if not isinstance(item, dict) or set(item) != keys:
            raise DocumentError("document block differs from v1")
        if item["extraction_method"] != expected_method:
            raise DocumentError("document extraction method differs")
        if not isinstance(item["text"], str) or not item["text"]:
            raise DocumentError("document block text is required")
        expected_text_hash = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        if item["text_sha256"] != expected_text_hash:
            raise DocumentError("document block text hash differs")
        locator = item["locator"]
        if not isinstance(locator, dict) or set(locator) != {
            "unit_kind", "unit_index", "region", "character_start", "character_end"
        }:
            raise DocumentError("document block locator differs")
        if locator["unit_kind"] not in {"DOCUMENT", "PARAGRAPH", "PAGE", "SLIDE", "SLIDE_NOTES", "IMAGE"}:
            raise DocumentError("document block unit differs")
        _positive_integer(locator["unit_index"], "locator unit index")
        if locator["region"] is not None:
            _region(locator["region"])
        if expected_method == "OCR" and locator["region"] is None:
            raise DocumentError("OCR block requires a region locator")
        if locator["character_start"] != 0 or locator["character_end"] != len(item["text"]):
            raise DocumentError("document character locator differs")
        native_id = content_sha256(
            {
                "method": expected_method,
                "locator": locator,
                "text_sha256": expected_text_hash,
                "ordinal": ordinal if expected_method == "OCR" else 0,
            }
        )
        expected_id = derive_imported_id(
            "artifact", "integra.document_block", native_id, source_sha256
        )
        if item["block_id"] != expected_id or item["block_id"] in ids:
            raise DocumentError("document block identity differs or is duplicated")
        ids.add(item["block_id"])
        if expected_method == "OCR":
            confidence = item["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise DocumentError("OCR block confidence differs")


def _validate_ocr_provider(provider: Any) -> None:
    if not isinstance(provider, dict) or set(provider) != {
        "component_id", "implementation_sha256", "model_id", "model_sha256"
    }:
        raise DocumentError("OCR provider provenance differs from v1")
    for field in ("component_id", "model_id"):
        if not isinstance(provider[field], str) or not provider[field].strip():
            raise DocumentError("OCR provider identity is incomplete")
    _digest(provider["implementation_sha256"])
    _digest(provider["model_sha256"])


def _validate_format_locators(record: dict[str, Any]) -> None:
    source_format = record["source"]["format"]
    count = record["page_or_slide_count"]
    expected_native = {
        "TXT": {"DOCUMENT"},
        "MARKDOWN": {"DOCUMENT"},
        "DOCX": {"PARAGRAPH"},
        "PPTX": {"SLIDE", "SLIDE_NOTES"},
        "PDF": {"PAGE"},
        "IMAGE": set(),
    }[source_format]
    native_blocks = record["native_extraction"]["blocks"]
    if any(item["locator"]["unit_kind"] not in expected_native for item in native_blocks):
        raise DocumentError("native locator kind differs from source format")
    if source_format in {"PDF", "PPTX"}:
        if count is None:
            raise DocumentError("paged source must declare page or slide count")
        if any(item["locator"]["unit_index"] > count for item in native_blocks):
            raise DocumentError("native locator is outside source range")
    elif source_format == "IMAGE":
        if count != 1 or native_blocks:
            raise DocumentError("image source native structure differs")
    elif count is not None:
        raise DocumentError("non-paged source cannot claim page or slide count")
    expected_ocr = {
        "IMAGE": "IMAGE",
        "PDF": "PAGE",
        "PPTX": "SLIDE",
        "DOCX": "DOCUMENT",
        "TXT": "DOCUMENT",
        "MARKDOWN": "DOCUMENT",
    }[source_format]
    if any(
        item["locator"]["unit_kind"] != expected_ocr
        or item["locator"]["unit_index"] > (count or 1)
        for item in record["ocr"]["blocks"]
    ):
        raise DocumentError("OCR locator differs from source format")


def _expected_mode_and_ocr_reason(record: dict[str, Any]) -> tuple[str, str]:
    source_format = record["source"]["format"]
    native = record["native_extraction"]
    count = record["page_or_slide_count"] or 1
    media_count = len(record["embedded_media"])
    if source_format == "IMAGE":
        return "SCAN", "IMAGE_SOURCE"
    if source_format in {"PDF", "PPTX", "DOCX"} and media_count and native["text_characters"] < 80 * count:
        reason = "IMAGE_HEAVY_PDF" if source_format == "PDF" else "IMAGE_HEAVY_DOCUMENT"
        return "IMAGE_HEAVY", reason
    if source_format == "PDF" and native["status"] != "COMPLETE":
        return "IMAGE_HEAVY", "UNSUPPORTED_PDF_TEXT_ENCODING"
    if media_count:
        return "MIXED", "NONE"
    return "TEXT", "NONE"


def _media(
    source_sha256: str,
    part_path: str,
    media_type: str,
    payload: bytes,
    parent_kind: str,
    parent_index: int,
) -> dict[str, Any]:
    sha256 = hashlib.sha256(payload).hexdigest()
    native_id = f"{source_sha256}:{part_path}"
    return {
        "media_id": derive_imported_id("artifact", "integra.document_media", native_id, sha256),
        "part_path": part_path,
        "media_type": media_type,
        "sha256": sha256,
        "size_bytes": len(payload),
        "parent_locator": {"unit_kind": parent_kind, "unit_index": parent_index},
        "source_sha256": source_sha256,
    }


def _validate_media(item: Any, source_sha256: str) -> None:
    if not isinstance(item, dict) or set(item) != {
        "media_id", "part_path", "media_type", "sha256", "size_bytes",
        "parent_locator", "source_sha256",
    }:
        raise DocumentError("embedded media record differs from v1")
    if item["source_sha256"] != source_sha256:
        raise DocumentError("embedded media source hash differs")
    path = PurePosixPath(item["part_path"])
    if path.is_absolute() or not item["part_path"] or any(part in {"", ".", ".."} for part in path.parts):
        raise DocumentError("embedded media part path is unsafe")
    if not isinstance(item["media_type"], str) or not item["media_type"]:
        raise DocumentError("embedded media type is required")
    _digest(item["sha256"])
    _nonnegative_integer(item["size_bytes"], "embedded media size")
    parent = item["parent_locator"]
    if not isinstance(parent, dict) or set(parent) != {"unit_kind", "unit_index"}:
        raise DocumentError("embedded media parent locator differs")
    if parent["unit_kind"] not in {"DOCUMENT", "PRESENTATION", "PDF_OBJECT"}:
        raise DocumentError("embedded media parent unit differs")
    _positive_integer(parent["unit_index"], "embedded media parent index")
    native_id = f"{source_sha256}:{item['part_path']}"
    if item["media_id"] != derive_imported_id(
        "artifact", "integra.document_media", native_id, item["sha256"]
    ):
        raise DocumentError("embedded media identity differs")


def _office_media(members: dict[str, bytes], source_sha256: str, kind: str) -> list[dict[str, Any]]:
    prefix = "word/media/" if kind == "DOCX" else "ppt/media/"
    media = []
    for name in sorted(key for key in members if key.startswith(prefix)):
        payload = members[name]
        media_type = _media_type_from_name(name)
        parent_kind = "DOCUMENT" if kind == "DOCX" else "PRESENTATION"
        media.append(_media(source_sha256, name, media_type, payload, parent_kind, 1))
    return media


def _embedded_payloads(source_format: str, data: bytes) -> dict[str, bytes]:
    if source_format in {"DOCX", "PPTX"}:
        members = _safe_zip(data, source_format)
        prefix = "word/media/" if source_format == "DOCX" else "ppt/media/"
        return {name: payload for name, payload in members.items() if name.startswith(prefix)}
    if source_format == "PDF":
        result = {}
        for number, body in _pdf_objects(data).items():
            if re.search(rb"/Subtype\s*/Image\b", body):
                payload = _pdf_stream(body)
                if payload is not None:
                    result[f"pdf/object-{number}"] = payload
        return result
    return {}


def _safe_zip(data: bytes, expected: str) -> dict[str, bytes]:
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names: set[str] = set()
            total = 0
            result: dict[str, bytes] = {}
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if (
                    info.filename in names
                    or path.is_absolute()
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or info.file_size > MAX_ZIP_MEMBER_BYTES
                ):
                    raise DocumentError(f"{expected} member is unsafe")
                names.add(info.filename)
                total += info.file_size
                if total > MAX_ZIP_TOTAL_BYTES:
                    raise DocumentError(f"{expected} expanded size exceeds limit")
                if info.is_dir():
                    continue
                result[info.filename] = archive.read(info)
            return result
    except DocumentError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
        OSError,
        RuntimeError,
    ) as exc:
        raise DocumentError(f"{expected} container is invalid") from exc


def _pdf_objects(data: bytes) -> dict[int, bytes]:
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(rb"(\d+)\s+\d+\s+obj\b(.*?)\bendobj\b", data, re.S)
    }


def _pdf_page_order(objects: dict[int, bytes]) -> list[int]:
    catalog = next(
        (body for _, body in sorted(objects.items()) if re.search(rb"/Type\s*/Catalog\b", body)),
        None,
    )
    if catalog is None:
        raise DocumentError("PDF catalog is missing")
    root_match = re.search(rb"/Pages\s+(\d+)\s+\d+\s+R", catalog)
    if root_match is None:
        raise DocumentError("PDF page tree root is missing")
    result: list[int] = []
    visiting: set[int] = set()

    def visit(reference: int) -> None:
        if reference in visiting:
            raise DocumentError("PDF page tree contains a cycle")
        body = objects.get(reference)
        if body is None:
            raise DocumentError("PDF page tree reference is missing")
        if re.search(rb"/Type\s*/Page\b", body) and not re.search(rb"/Type\s*/Pages\b", body):
            if reference in result:
                raise DocumentError("PDF page appears more than once")
            result.append(reference)
            return
        if not re.search(rb"/Type\s*/Pages\b", body):
            raise DocumentError("PDF page tree points to a non-page object")
        kids = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
        if kids is None:
            raise DocumentError("PDF page tree node has no Kids array")
        references = [int(value) for value in re.findall(rb"(\d+)\s+\d+\s+R", kids.group(1))]
        if not references:
            raise DocumentError("PDF page tree node is empty")
        visiting.add(reference)
        for child in references:
            visit(child)
        visiting.remove(reference)

    visit(int(root_match.group(1)))
    if not result:
        raise DocumentError("PDF contains no pages")
    return result


def _pdf_stream(body: bytes) -> bytes | None:
    match = re.search(rb"\bstream\r?\n(.*?)\r?\nendstream\b", body, re.S)
    return match.group(1) if match else None


def _pdf_text_strings(stream: bytes) -> tuple[list[str], bool]:
    stream = _pdf_without_comments(stream)
    result: list[str] = []
    complete = True
    tj_matches = re.findall(rb"\((?:\\.|[^\\)])*\)\s*Tj\b", stream)
    for raw in tj_matches:
        decoded = _pdf_string(raw[: raw.rfind(b")") + 1])
        if decoded is None:
            complete = False
        else:
            result.append(decoded)
    tj_array_matches = re.findall(rb"\[(.*?)\]\s*TJ\b", stream, re.S)
    for array in tj_array_matches:
        values = re.findall(rb"\((?:\\.|[^\\)])*\)", array)
        remainder = re.sub(rb"\((?:\\.|[^\\)])*\)", b" ", array)
        if not re.fullmatch(
            rb"(?:\s|[+-]?(?:\d+(?:\.\d*)?|\.\d+))*",
            remainder,
        ):
            complete = False
        if values:
            decoded_values = [_pdf_string(value) for value in values]
            if any(value is None for value in decoded_values):
                complete = False
            else:
                result.append("".join(value for value in decoded_values if value is not None))
        else:
            complete = False
    operators = _pdf_code_tokens(stream)
    operator_count = sum(value in {b"Tj", b"TJ"} for value in operators)
    recognized_count = len(tj_matches) + len(tj_array_matches)
    unsupported_text_show = any(value in {b"'", b'"'} for value in operators)
    return (
        result,
        complete and operator_count == recognized_count and not unsupported_text_show,
    )


def _pdf_without_comments(stream: bytes) -> bytes:
    result = bytearray(stream)
    literal_depth = 0
    escaped = False
    in_comment = False
    in_hex = False
    index = 0
    while index < len(stream):
        value = stream[index]
        if in_comment:
            if value in {ord("\r"), ord("\n")}:
                in_comment = False
            else:
                result[index] = ord(" ")
            index += 1
            continue
        if literal_depth:
            if escaped:
                escaped = False
            elif value == ord("\\"):
                escaped = True
            elif value == ord("("):
                literal_depth += 1
            elif value == ord(")"):
                literal_depth -= 1
            index += 1
            continue
        if in_hex:
            if value == ord(">"):
                in_hex = False
            index += 1
            continue
        if value == ord("%"):
            in_comment = True
            result[index] = ord(" ")
        elif value == ord("("):
            literal_depth = 1
        elif value == ord("<"):
            if index + 1 < len(stream) and stream[index + 1] == ord("<"):
                index += 2
                continue
            in_hex = True
        index += 1
    return bytes(result)


def _pdf_code_tokens(stream: bytes) -> list[bytes]:
    tokens: list[bytes] = []
    current = bytearray()
    index = 0

    def flush() -> None:
        if current:
            tokens.append(bytes(current))
            current.clear()

    while index < len(stream):
        value = stream[index]
        if value in b" \t\r\n\f\x00":
            flush()
            index += 1
            continue
        if value == ord("("):
            flush()
            depth = 1
            index += 1
            escaped = False
            while index < len(stream) and depth:
                item = stream[index]
                if escaped:
                    escaped = False
                elif item == ord("\\"):
                    escaped = True
                elif item == ord("("):
                    depth += 1
                elif item == ord(")"):
                    depth -= 1
                index += 1
            continue
        if value == ord("<"):
            flush()
            if index + 1 < len(stream) and stream[index + 1] == ord("<"):
                index += 2
                continue
            index += 1
            while index < len(stream) and stream[index] != ord(">"):
                index += 1
            index += index < len(stream)
            continue
        if value == ord("/"):
            flush()
            index += 1
            while index < len(stream) and stream[index] not in b" \t\r\n\f\x00()<>[]{}/%":
                index += 1
            continue
        if value in b"[]{}>":
            flush()
            index += 1
            continue
        if value in {ord("'"), ord('"')}:
            flush()
            tokens.append(bytes([value]))
            index += 1
            continue
        current.append(value)
        index += 1
    flush()
    return tokens


def _pdf_string(value: bytes) -> str | None:
    inner = value[1:-1]
    decoded = bytearray()
    index = 0
    escapes = {
        ord("n"): ord("\n"),
        ord("r"): ord("\r"),
        ord("t"): ord("\t"),
        ord("b"): ord("\b"),
        ord("f"): ord("\f"),
        ord("("): ord("("),
        ord(")"): ord(")"),
        ord("\\"): ord("\\"),
    }
    while index < len(inner):
        current = inner[index]
        if current != ord("\\"):
            decoded.append(current)
            index += 1
            continue
        index += 1
        if index >= len(inner):
            return None
        escaped = inner[index]
        if escaped in escapes:
            decoded.append(escapes[escaped])
            index += 1
            continue
        if ord("0") <= escaped <= ord("7"):
            end = index + 1
            while end < min(index + 3, len(inner)) and ord("0") <= inner[end] <= ord("7"):
                end += 1
            octet = int(inner[index:end], 8)
            if octet > 255:
                return None
            decoded.append(octet)
            index = end
            continue
        if escaped == ord("\n"):
            index += 1
            continue
        if escaped == ord("\r"):
            index += 1
            if index < len(inner) and inner[index] == ord("\n"):
                index += 1
            continue
        return None
    try:
        return bytes(decoded).decode("utf-8")
    except UnicodeDecodeError:
        return None


def _read_regular_file(path: Path) -> bytes:
    if not path.is_absolute():
        path = path.absolute()
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
    except (OSError, ValueError) as exc:
        if isinstance(exc, DocumentError):
            raise
        raise DocumentError("document source cannot be opened safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
            raise DocumentError("document source is not a supported regular file")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise DocumentError("document source ended before declared size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise DocumentError("document source grew during read")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise DocumentError("document source changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _detect_format(path: Path, data: bytes) -> tuple[str, str]:
    suffix = path.suffix.lower()
    expected = FORMAT_BY_SUFFIX.get(suffix)
    if expected is None:
        raise DocumentError("document filename extension is unsupported")
    source_format, media_type = expected
    if source_format in {"DOCX", "PPTX"} and not data.startswith(b"PK"):
        raise DocumentError("OOXML extension does not match source bytes")
    if source_format == "PDF" and not data.startswith(b"%PDF-"):
        raise DocumentError("PDF extension does not match source bytes")
    if media_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentError("PNG extension does not match source bytes")
    if media_type == "image/jpeg" and not data.startswith(b"\xff\xd8"):
        raise DocumentError("JPEG extension does not match source bytes")
    if media_type == "image/tiff" and not data.startswith((b"II*\x00", b"MM\x00*")):
        raise DocumentError("TIFF extension does not match source bytes")
    if source_format == "IMAGE":
        _validate_image_bytes(data, media_type)
    if source_format == "DOCX" and b"word/" not in data:
        raise DocumentError("DOCX container identity is missing")
    if source_format == "PPTX" and b"ppt/" not in data:
        raise DocumentError("PPTX container identity is missing")
    return expected


def _validate_image_bytes(data: bytes, media_type: str) -> None:
    if media_type == "image/png":
        if len(data) < 45:
            raise DocumentError("PNG source is incomplete")
        offset = 8
        seen_ihdr = False
        seen_iend = False
        seen_idat = False
        idat_finished = False
        idat_payloads: list[bytes] = []
        image_properties: tuple[int, int, int, int, int] | None = None
        while offset + 12 <= len(data):
            length = int.from_bytes(data[offset:offset + 4], "big")
            kind = data[offset + 4:offset + 8]
            end = offset + 12 + length
            if length > MAX_SOURCE_BYTES or end > len(data):
                raise DocumentError("PNG chunk is truncated or oversized")
            payload = data[offset + 8:offset + 8 + length]
            supplied_crc = int.from_bytes(data[offset + 8 + length:end], "big")
            if zlib.crc32(kind + payload) & 0xFFFFFFFF != supplied_crc:
                raise DocumentError("PNG chunk checksum differs")
            if not seen_ihdr:
                if kind != b"IHDR" or length != 13:
                    raise DocumentError("PNG IHDR is missing")
                width = int.from_bytes(payload[0:4], "big")
                height = int.from_bytes(payload[4:8], "big")
                if (
                    width < 1
                    or height < 1
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise DocumentError("PNG dimensions are invalid")
                bit_depth = payload[8]
                color_type = payload[9]
                compression = payload[10]
                filtering = payload[11]
                interlace = payload[12]
                allowed_depths = {
                    0: {1, 2, 4, 8, 16},
                    2: {8, 16},
                    3: {1, 2, 4, 8},
                    4: {8, 16},
                    6: {8, 16},
                }
                if (
                    bit_depth not in allowed_depths.get(color_type, set())
                    or compression != 0
                    or filtering != 0
                    or interlace not in {0, 1}
                ):
                    raise DocumentError("PNG IHDR fields are unsupported or invalid")
                image_properties = (width, height, bit_depth, color_type, interlace)
                seen_ihdr = True
            elif kind == b"IHDR":
                raise DocumentError("PNG contains duplicate IHDR")
            elif kind == b"IDAT":
                if idat_finished or seen_iend:
                    raise DocumentError("PNG IDAT order differs")
                seen_idat = True
                idat_payloads.append(payload)
            elif seen_idat:
                idat_finished = True
            if kind == b"IEND":
                if length != 0 or end != len(data):
                    raise DocumentError("PNG IEND differs")
                seen_iend = True
                break
            offset = end
        if not seen_ihdr or not seen_idat or not seen_iend or image_properties is None:
            raise DocumentError("PNG structure is incomplete")
        _validate_png_image_data(b"".join(idat_payloads), *image_properties)
        return
    if media_type == "image/jpeg":
        if len(data) < 8 or not data.endswith(b"\xff\xd9"):
            raise DocumentError("JPEG source is incomplete")
        offset = 2
        dimensions = None
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset < len(data) - 2:
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                raise DocumentError("JPEG segment is truncated")
            length = int.from_bytes(data[offset:offset + 2], "big")
            if length < 2 or offset + length > len(data):
                raise DocumentError("JPEG segment length differs")
            if marker in sof_markers:
                if length < 7:
                    raise DocumentError("JPEG frame header is incomplete")
                height = int.from_bytes(data[offset + 3:offset + 5], "big")
                width = int.from_bytes(data[offset + 5:offset + 7], "big")
                if width < 1 or height < 1 or width * height > 1_000_000_000:
                    raise DocumentError("JPEG dimensions are invalid")
                dimensions = (width, height)
            offset += length
        if dimensions is None:
            raise DocumentError("JPEG frame dimensions are missing")
        return
    if media_type == "image/tiff":
        if len(data) < 14:
            raise DocumentError("TIFF source is incomplete")
        byteorder = "little" if data[:2] == b"II" else "big"
        if int.from_bytes(data[2:4], byteorder) != 42:
            raise DocumentError("TIFF version differs")
        directory = int.from_bytes(data[4:8], byteorder)
        if directory + 2 > len(data):
            raise DocumentError("TIFF directory is outside source")
        entries = int.from_bytes(data[directory:directory + 2], byteorder)
        if directory + 2 + entries * 12 + 4 > len(data):
            raise DocumentError("TIFF directory is truncated")
        dimensions: dict[int, int] = {}
        for index in range(entries):
            start = directory + 2 + index * 12
            tag = int.from_bytes(data[start:start + 2], byteorder)
            kind = int.from_bytes(data[start + 2:start + 4], byteorder)
            count = int.from_bytes(data[start + 4:start + 8], byteorder)
            if tag in {256, 257} and count == 1 and kind in {3, 4}:
                size = 2 if kind == 3 else 4
                dimensions[tag] = int.from_bytes(data[start + 8:start + 8 + size], byteorder)
        if dimensions.get(256, 0) < 1 or dimensions.get(257, 0) < 1:
            raise DocumentError("TIFF dimensions are missing")
        if dimensions[256] * dimensions[257] > 1_000_000_000:
            raise DocumentError("TIFF dimensions are invalid")
        return
    raise DocumentError("image media type is unsupported")


def _validate_png_image_data(
    compressed: bytes,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace: int,
) -> None:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    passes = [(width, height)]
    if interlace == 1:
        passes = []
        for x_start, y_start, x_step, y_step in (
            (0, 0, 8, 8),
            (4, 0, 8, 8),
            (0, 4, 4, 8),
            (2, 0, 4, 4),
            (0, 2, 2, 4),
            (1, 0, 2, 2),
            (0, 1, 1, 2),
        ):
            pass_width = (
                (width - x_start + x_step - 1) // x_step
                if width > x_start
                else 0
            )
            pass_height = (
                (height - y_start + y_step - 1) // y_step
                if height > y_start
                else 0
            )
            if pass_width and pass_height:
                passes.append((pass_width, pass_height))
    layout: list[tuple[int, int]] = []
    expected_size = 0
    for pass_width, pass_height in passes:
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        layout.append((row_bytes, pass_height))
        expected_size += (row_bytes + 1) * pass_height
    if expected_size < 1 or expected_size > MAX_DECODED_IMAGE_BYTES:
        raise DocumentError("PNG decoded size exceeds limit")
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(compressed, expected_size + 1)
    except zlib.error as exc:
        raise DocumentError("PNG image data cannot be decompressed") from exc
    if (
        not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or len(decoded) != expected_size
    ):
        raise DocumentError("PNG image data length differs")
    offset = 0
    for row_bytes, pass_height in layout:
        for _ in range(pass_height):
            if decoded[offset] > 4:
                raise DocumentError("PNG row filter is invalid")
            offset += row_bytes + 1


def _validate_new_output_root(root: Path) -> Path:
    if not root.is_absolute():
        raise DocumentError("embedded media output root must be absolute")
    if root.name in {"", ".", ".."}:
        raise DocumentError("embedded media output root name is invalid")
    if root.parent.resolve() != root.parent:
        raise DocumentError("embedded media output has a symlinked ancestor")
    if root.exists() or root.is_symlink():
        raise DocumentError("embedded media output root must not already exist")
    current = Path(root.anchor)
    for part in root.parent.parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except OSError as exc:
            raise DocumentError("embedded media output parent is missing") from exc
        if stat.S_ISLNK(mode):
            raise DocumentError("embedded media output has a symlinked ancestor")
    return root


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _open_directory_chain(
    path: Path,
) -> tuple[list[int], list[tuple[int, str, os.stat_result]]]:
    if not path.is_absolute():
        raise DocumentError("directory chain must be absolute")
    descriptors: list[int] = []
    entries: list[tuple[int, str, os.stat_result]] = []
    try:
        descriptors.append(os.open(path.anchor, _directory_open_flags()))
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise DocumentError("directory chain component is unsafe")
            parent_index = len(descriptors) - 1
            descriptor = os.open(
                component,
                _directory_open_flags(),
                dir_fd=descriptors[parent_index],
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(descriptor)
                raise DocumentError("directory chain component is not a directory")
            entries.append((parent_index, component, metadata))
            descriptors.append(descriptor)
        return descriptors, entries
    except DocumentError:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise
    except OSError as exc:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise DocumentError("directory chain cannot be opened safely") from exc


def _assert_directory_chain(
    descriptors: list[int], entries: list[tuple[int, str, os.stat_result]]
) -> None:
    for parent_index, name, expected in entries:
        _assert_directory_entry(descriptors[parent_index], name, expected)


def _assert_directory_entry(parent_fd: int, name: str, expected: os.stat_result) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise DocumentError("embedded media output root disappeared") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
    ):
        raise DocumentError("embedded media output root identity changed")


def _read_regular_at(directory_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise DocumentError("materialized embedded media cannot be reopened") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise DocumentError("materialized embedded media is not an isolated regular file")
        chunks = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise DocumentError("materialized embedded media is truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise DocumentError("materialized embedded media grew during verification")
        after = os.fstat(fd)
        if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
            after.st_dev, after.st_ino, after.st_size
        ):
            raise DocumentError("materialized embedded media changed during verification")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _decode_utf8(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError("text document is not UTF-8") from exc


def _xml(data: bytes, label: str) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise DocumentError(f"{label} contains forbidden XML declarations")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise DocumentError(f"{label} XML is invalid") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ooxml_text(root: ET.Element, *, separator: str = "") -> str:
    fragments: list[str] = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind == "t" and node.text:
            fragments.append(node.text)
        elif kind == "tab":
            fragments.append("\t")
        elif kind in {"br", "cr"}:
            fragments.append("\n")
    if separator:
        return separator.join(fragment for fragment in fragments if fragment)
    return "".join(fragments)


def _pptx_slide_order(members: dict[str, bytes]) -> list[str]:
    presentation_path = "ppt/presentation.xml"
    if presentation_path not in members:
        raise DocumentError("PPTX presentation.xml is missing")
    root = _xml(members[presentation_path], "PPTX presentation")
    relationships = _relationships(members, presentation_path)
    ordered: list[str] = []
    relationship_attribute = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for node in root.iter():
        if _local(node.tag) != "sldId":
            continue
        relationship_id = node.attrib.get(relationship_attribute)
        if not relationship_id or relationship_id not in relationships:
            raise DocumentError("PPTX slide relationship is missing")
        target, relation_type = relationships[relationship_id]
        if not relation_type.endswith("/slide") or target not in members:
            raise DocumentError("PPTX slide relationship differs")
        if target in ordered:
            raise DocumentError("PPTX slide relationship is duplicated")
        ordered.append(target)
    if not ordered:
        raise DocumentError("PPTX contains no ordered slides")
    actual_slides = {
        name for name in members if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
    }
    if set(ordered) != actual_slides:
        raise DocumentError("PPTX slide inventory differs from presentation order")
    return ordered


def _related_part(
    members: dict[str, bytes], part_path: str, *, relation_type_suffix: str
) -> str | None:
    matches = [
        target
        for target, relation_type in _relationships(members, part_path).values()
        if relation_type.endswith(relation_type_suffix)
    ]
    if len(matches) > 1:
        raise DocumentError("OOXML part has duplicate typed relationships")
    return matches[0] if matches else None


def _relationships(
    members: dict[str, bytes], part_path: str
) -> dict[str, tuple[str, str]]:
    part = PurePosixPath(part_path)
    rels_path = str(part.parent / "_rels" / f"{part.name}.rels")
    payload = members.get(rels_path)
    if payload is None:
        return {}
    root = _xml(payload, "OOXML relationships")
    relationships: dict[str, tuple[str, str]] = {}
    for node in root.iter():
        if _local(node.tag) != "Relationship":
            continue
        relationship_id = node.attrib.get("Id")
        relation_type = node.attrib.get("Type")
        target = node.attrib.get("Target")
        if not relationship_id or not relation_type or not target:
            raise DocumentError("OOXML relationship is incomplete")
        if relationship_id in relationships:
            raise DocumentError("OOXML relationship ID is duplicated")
        if node.attrib.get("TargetMode", "Internal") != "Internal":
            continue
        combined = part.parent / PurePosixPath(target)
        stack: list[str] = []
        for component in combined.parts:
            if component in {"", "."}:
                continue
            if component == "..":
                if not stack:
                    raise DocumentError("OOXML relationship escapes package root")
                stack.pop()
            else:
                stack.append(component)
        normalized = "/".join(stack)
        if not normalized:
            raise DocumentError("OOXML relationship target is empty")
        relationships[relationship_id] = (normalized, relation_type)
    return relationships


def _region(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"}:
        raise DocumentError("OCR region differs from v1")
    result = {}
    for key in ("x", "y", "width", "height"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise DocumentError("OCR region coordinate is invalid")
        result[key] = float(number)
    if not (
        0 <= result["x"] < 1
        and 0 <= result["y"] < 1
        and 0 < result["width"] <= 1
        and 0 < result["height"] <= 1
        and result["x"] + result["width"] <= 1
        and result["y"] + result["height"] <= 1
    ):
        raise DocumentError("OCR region is outside normalized source bounds")
    return result


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DocumentError("timestamp must be UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DocumentError("timestamp is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise DocumentError("timestamp must be UTC")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise DocumentError("SHA-256 value is invalid")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DocumentError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DocumentError(f"{label} must be a non-negative integer")
    return value


def _media_type_from_name(name: str) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".tif": "image/tiff", ".tiff": "image/tiff",
        ".svg": "image/svg+xml", ".emf": "image/emf", ".wmf": "image/wmf",
    }.get(PurePosixPath(name).suffix.lower(), "application/octet-stream")


def _extension_for_media_type(media_type: str) -> str:
    return {
        "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/tiff": ".tiff", "image/svg+xml": ".svg", "image/jp2": ".jp2",
        "image/emf": ".emf", "image/wmf": ".wmf",
    }.get(media_type, ".bin")
