import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from integra_core import documents as document_module
from integra_core.documents import (
    DocumentError,
    extract_document,
    materialize_embedded_media,
    validate_document_against_source,
    validate_document_record,
)
from integra_core.protocol import content_sha256


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "document_v1" / "cases.json"
CAPTURED_AT = "2026-09-11T00:00:00Z"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
)


def office_zip(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            archive.writestr(info, members[name])
    return output.getvalue()


def docx_bytes(first_paragraph: bytes = b"First paragraph") -> bytes:
    return office_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": (
                b'<w:document xmlns:w="urn:w"><w:body>'
                b"<w:p><w:r><w:t>" + first_paragraph + b"</w:t></w:r></w:p>"
                b"<w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>"
                b"</w:body></w:document>"
            ),
            "word/media/image1.png": PNG,
        }
    )


def docx_with_leading_empty_paragraph() -> bytes:
    return office_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": (
                b'<w:document xmlns:w="urn:w"><w:body>'
                b"<w:p/><w:p><w:r><w:t>Second source paragraph</w:t></w:r></w:p>"
                b"</w:body></w:document>"
            ),
        }
    )


def pptx_bytes() -> bytes:
    return office_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "ppt/presentation.xml": (
                b'<p:presentation xmlns:p="urn:p" '
                b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                b'<p:sldIdLst><p:sldId id="256" r:id="rId1"/>'
                b'<p:sldId id="257" r:id="rId2"/></p:sldIdLst></p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": (
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>'
                b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>'
                b'</Relationships>'
            ),
            "ppt/slides/slide1.xml": (
                b'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:cSld>'
                b"<a:t>Slide one</a:t><a:t>Body</a:t></p:cSld></p:sld>"
            ),
            "ppt/slides/slide2.xml": (
                b'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:cSld>'
                b"<a:t>Slide two</a:t></p:cSld></p:sld>"
            ),
            "ppt/notesSlides/notesSlide1.xml": (
                b'<p:notes xmlns:p="urn:p" xmlns:a="urn:a"><a:t>Speaker note</a:t></p:notes>'
            ),
            "ppt/slides/_rels/slide1.xml.rels": (
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rIdNotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>'
                b'</Relationships>'
            ),
            "ppt/media/image1.png": PNG,
        }
    )


def text_pdf(
    *,
    image: bool = False,
    filtered: bool = False,
    stream: bytes = b"BT (PDF page text) Tj ET",
) -> bytes:
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj",
    ]
    filter_part = b" /Filter /FlateDecode" if filtered else b""
    objects.append(
        b"4 0 obj << /Length " + str(len(stream)).encode() + filter_part + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj"
    )
    if image:
        payload = b"synthetic-image-stream"
        objects.append(
            b"5 0 obj << /Type /XObject /Subtype /Image /Width 1 /Height 1 /Length "
            + str(len(payload)).encode() + b" >>\nstream\n" + payload + b"\nendstream\nendobj"
        )
    return b"%PDF-1.4\n" + b"\n".join(objects) + b"\n%%EOF\n"


def partially_supported_two_page_pdf() -> bytes:
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 5 0 R >> endobj",
        b"4 0 obj << /Type /Page /Parent 2 0 R /Contents 6 0 R >> endobj",
        b"5 0 obj << /Length 19 >>\nstream\nBT <4869> Tj ET\nendstream\nendobj",
        b"6 0 obj << /Length 23 >>\nstream\nBT (Visible) Tj ET\nendstream\nendobj",
    ]
    return b"%PDF-1.4\n" + b"\n".join(objects) + b"\n%%EOF\n"


def direct_contents_pdf() -> bytes:
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R "
            b"/Contents << /Length 18 >> >>\nstream\nBT (Direct) Tj ET\n"
            b"endstream\nendobj"
        ),
    ]
    return b"%PDF-1.4\n" + b"\n".join(objects) + b"\n%%EOF\n"


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, payload: bytes) -> Path:
        path = self.root / name
        path.write_bytes(payload)
        return path

    def extract(self, name: str, payload: bytes, **kwargs: object) -> dict:
        return extract_document(
            self.write(name, payload), captured_at=CAPTURED_AT, **kwargs
        )

    def test_fixture_inventory_covers_every_required_format(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema_version"], "1.0")
        self.assertEqual(
            {case["format"] for case in fixture["cases"]},
            {"TXT", "MARKDOWN", "DOCX", "PPTX", "PDF", "IMAGE"},
        )

    def test_txt_and_markdown_preserve_exact_characters_and_locator(self) -> None:
        for name, text in (
            ("notes.txt", "Exact source text."),
            ("guide.md", "# Guide\n\nEvidence-linked notes."),
        ):
            with self.subTest(name=name):
                record = self.extract(name, text.encode())
                block = record["native_extraction"]["blocks"][0]
                self.assertEqual(block["text"], text)
                self.assertEqual(block["locator"]["character_end"], len(text))
                self.assertEqual(record["content_mode"], "TEXT")
                self.assertEqual(record["ocr"]["status"], "NOT_REQUIRED")

    def test_docx_preserves_paragraph_structure_and_embedded_media(self) -> None:
        path = self.write("handout.docx", docx_bytes())
        record = extract_document(path, captured_at=CAPTURED_AT)
        self.assertEqual(
            [item["text"] for item in record["native_extraction"]["blocks"]],
            ["First paragraph", "Second paragraph"],
        )
        self.assertTrue(all(item["locator"]["unit_kind"] == "PARAGRAPH" for item in record["native_extraction"]["blocks"]))
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["status"], "REQUIRED")
        media = record["embedded_media"][0]
        self.assertEqual(media["sha256"], hashlib.sha256(PNG).hexdigest())
        output = (self.root / "materialized").resolve(strict=False)
        written = materialize_embedded_media(record, path, output)
        self.assertEqual((output / written[0]["relative_path"]).read_bytes(), PNG)

    def test_docx_locator_preserves_source_ordinal_across_empty_paragraphs(self) -> None:
        record = self.extract("gapped.docx", docx_with_leading_empty_paragraph())
        block = record["native_extraction"]["blocks"][0]
        self.assertEqual(block["text"], "Second source paragraph")
        self.assertEqual(block["locator"]["unit_kind"], "PARAGRAPH")
        self.assertEqual(block["locator"]["unit_index"], 2)

    def test_pptx_preserves_slides_notes_and_media(self) -> None:
        record = self.extract("slides.pptx", pptx_bytes())
        self.assertEqual(record["page_or_slide_count"], 2)
        blocks = record["native_extraction"]["blocks"]
        self.assertEqual([item["locator"]["unit_kind"] for item in blocks], ["SLIDE", "SLIDE", "SLIDE_NOTES"])
        self.assertEqual([item["locator"]["unit_index"] for item in blocks], [1, 2, 2])
        self.assertEqual(blocks[0]["text"], "Slide two")
        self.assertEqual(blocks[1]["text"], "Slide one\nBody")
        self.assertEqual(blocks[2]["text"], "Speaker note")
        self.assertEqual(len(record["embedded_media"]), 1)
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["reason"], "IMAGE_HEAVY_DOCUMENT")

    def test_pdf_native_page_text_has_page_and_character_locator(self) -> None:
        record = self.extract("paper.pdf", text_pdf())
        self.assertEqual(record["page_or_slide_count"], 1)
        block = record["native_extraction"]["blocks"][0]
        self.assertEqual(block["text"], "PDF page text")
        self.assertEqual(block["locator"]["unit_kind"], "PAGE")
        self.assertEqual(record["content_mode"], "TEXT")

    def test_image_heavy_pdf_is_not_plain_text_and_requests_ocr(self) -> None:
        record = self.extract("scan.pdf", text_pdf(image=True))
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["status"], "REQUIRED")
        self.assertTrue(record["fidelity"]["image_heavy_not_plain_text"])
        self.assertEqual(len(record["embedded_media"]), 1)

    def test_filtered_pdf_fails_to_ocr_required_instead_of_fabricating_text(self) -> None:
        record = self.extract("encoded.pdf", text_pdf(filtered=True))
        self.assertEqual(record["native_extraction"]["status"], "PARTIAL_UNSUPPORTED_ENCODING")
        self.assertEqual(record["native_extraction"]["blocks"], [])
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["reason"], "UNSUPPORTED_PDF_TEXT_ENCODING")

    def test_partly_unsupported_pdf_cannot_claim_complete_native_extraction(self) -> None:
        record = self.extract("partial.pdf", partially_supported_two_page_pdf())
        self.assertEqual(record["page_or_slide_count"], 2)
        self.assertEqual(
            record["native_extraction"]["status"],
            "PARTIAL_UNSUPPORTED_ENCODING",
        )
        self.assertEqual(
            [block["text"] for block in record["native_extraction"]["blocks"]],
            ["Visible"],
        )
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["status"], "REQUIRED")

    def test_pdf_octal_escape_is_decoded_and_mixed_tj_fails_to_ocr(self) -> None:
        octal = self.extract("octal.pdf", text_pdf(stream=b"BT (\\101) Tj ET"))
        self.assertEqual(octal["native_extraction"]["status"], "COMPLETE")
        self.assertEqual(octal["native_extraction"]["blocks"][0]["text"], "A")
        mixed = self.extract(
            "mixed.pdf",
            text_pdf(stream=b"BT [(A) <42>] TJ ET"),
        )
        self.assertEqual(
            mixed["native_extraction"]["status"],
            "PARTIAL_UNSUPPORTED_ENCODING",
        )
        self.assertEqual(mixed["native_extraction"]["blocks"][0]["text"], "A")
        self.assertEqual(mixed["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(mixed["ocr"]["status"], "REQUIRED")
        invalid_octal = self.extract(
            "invalid-octal.pdf",
            text_pdf(stream=b"BT (\\777) Tj ET"),
        )
        self.assertEqual(
            invalid_octal["native_extraction"]["status"],
            "PARTIAL_UNSUPPORTED_ENCODING",
        )

    def test_unsupported_pdf_text_show_operators_cannot_drop_text_as_complete(self) -> None:
        for name, stream in (
            ("single-quote.pdf", b"BT (First) Tj (Second) ' ET"),
            ("double-quote.pdf", b'BT (First) Tj 10 20 (Second) " ET'),
            (
                "comment-single-quote.pdf",
                b"BT (First) Tj (Second) % comment\n' ET",
            ),
            (
                "comment-double-quote.pdf",
                b'BT (First) Tj 10 20 (Second) % comment\n" ET',
            ),
        ):
            with self.subTest(name=name):
                record = self.extract(name, text_pdf(stream=stream))
                self.assertEqual(
                    record["native_extraction"]["status"],
                    "PARTIAL_UNSUPPORTED_ENCODING",
                )
                self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
                self.assertEqual(record["ocr"]["status"], "REQUIRED")

    def test_pdf_operator_words_inside_literals_and_comments_are_not_counted(self) -> None:
        for name, stream, expected in (
            ("literal-token.pdf", b"BT (Say Tj literally) Tj ET", "Say Tj literally"),
            ("comment-token.pdf", b"BT (Only) Tj % Tj is a comment\nET", "Only"),
            (
                "commented-text.pdf",
                b"BT (Only) Tj % (Ignored) Tj\nET",
                "Only",
            ),
        ):
            with self.subTest(name=name):
                record = self.extract(name, text_pdf(stream=stream))
                self.assertEqual(record["native_extraction"]["status"], "COMPLETE")
                self.assertEqual(
                    record["native_extraction"]["blocks"][0]["text"],
                    expected,
                )
                self.assertEqual(record["content_mode"], "TEXT")
                self.assertEqual(record["ocr"]["status"], "NOT_REQUIRED")

    def test_nested_pdf_literal_string_uses_documented_ocr_fallback(self) -> None:
        record = self.extract(
            "nested-literal.pdf",
            text_pdf(stream=b"BT (Outer (inner) end) Tj ET"),
        )
        self.assertEqual(
            record["native_extraction"]["status"],
            "PARTIAL_UNSUPPORTED_ENCODING",
        )
        self.assertEqual(record["native_extraction"]["blocks"], [])
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["status"], "REQUIRED")

    def test_unsupported_direct_pdf_contents_routes_to_ocr(self) -> None:
        record = self.extract("direct.pdf", direct_contents_pdf())
        self.assertEqual(
            record["native_extraction"]["status"],
            "PARTIAL_UNSUPPORTED_ENCODING",
        )
        self.assertEqual(record["content_mode"], "IMAGE_HEAVY")
        self.assertEqual(record["ocr"]["status"], "REQUIRED")

    def test_scan_uses_region_ocr_and_retains_provisional_authority(self) -> None:
        seen: list[dict] = []

        def ocr(request: dict) -> dict:
            seen.append(request)
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
                    "region": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.3},
                    "text": "OCR region text",
                    "confidence": 0.91,
                }],
            }

        record = self.extract("scan.png", PNG, ocr_provider=ocr)
        self.assertEqual(record["content_mode"], "SCAN")
        self.assertEqual(record["ocr"]["status"], "COMPLETE")
        self.assertEqual(record["ocr"]["blocks"][0]["locator"]["unit_kind"], "IMAGE")
        self.assertEqual(record["ocr"]["blocks"][0]["confidence"], 0.91)
        self.assertEqual(record["fidelity"]["semantic_authority"], "PROVISIONAL_MACHINE_EXTRACTION")
        self.assertEqual(seen[0]["source_bytes"], PNG)

    def test_record_is_deterministic_and_path_independent_except_display_name(self) -> None:
        first = self.extract("same.txt", b"same")
        second_path = self.root / "other" / "same.txt"
        second_path.parent.mkdir()
        second_path.write_bytes(b"same")
        second = extract_document(second_path, captured_at=CAPTURED_AT)
        self.assertEqual(first, second)

    def test_embedded_media_identity_is_bound_to_source_revision(self) -> None:
        first = self.extract("first.docx", docx_bytes())
        second = self.extract(
            "second.docx",
            docx_bytes(b"Other paragraph"),
        )
        self.assertEqual(
            first["embedded_media"][0]["sha256"],
            second["embedded_media"][0]["sha256"],
        )
        self.assertNotEqual(
            first["embedded_media"][0]["media_id"],
            second["embedded_media"][0]["media_id"],
        )

    def test_tampered_source_block_or_media_fails_closed(self) -> None:
        path = self.write("handout.docx", docx_bytes())
        record = extract_document(path, captured_at=CAPTURED_AT)
        for mutation in ("source", "block", "media"):
            changed = copy.deepcopy(record)
            if mutation == "source":
                changed["source"]["size_bytes"] += 1
            elif mutation == "block":
                changed["native_extraction"]["blocks"][0]["text"] = "tampered"
            else:
                changed["embedded_media"][0]["sha256"] = "0" * 64
            with self.subTest(mutation=mutation), self.assertRaises(DocumentError):
                validate_document_record(changed)
        path.write_bytes(docx_bytes() + b"changed")
        with self.assertRaises(DocumentError):
            validate_document_against_source(record, path)

    def test_rehashed_false_display_name_fails_against_source_path(self) -> None:
        path = self.write("truth.txt", b"truth")
        record = extract_document(path, captured_at=CAPTURED_AT)
        record["source"]["display_name"] = "false-name.md"
        identity = dict(record)
        identity.pop("record_sha256")
        record["record_sha256"] = content_sha256(identity)
        validate_document_record(record)
        with self.assertRaises(DocumentError):
            validate_document_against_source(record, path)

    def test_rehashed_omitted_native_or_media_inventory_fails_against_source(self) -> None:
        path = self.write("handout.docx", docx_bytes())
        record = extract_document(path, captured_at=CAPTURED_AT)
        without_block = copy.deepcopy(record)
        without_block["native_extraction"]["blocks"].pop()
        without_block["native_extraction"]["text_characters"] = len("First paragraph")
        identity = dict(without_block)
        identity.pop("record_sha256")
        without_block["record_sha256"] = content_sha256(identity)
        validate_document_record(without_block)
        with self.assertRaises(DocumentError):
            validate_document_against_source(without_block, path)
        without_media = copy.deepcopy(record)
        without_media["embedded_media"].clear()
        without_media["content_mode"] = "TEXT"
        without_media["ocr"] = {
            "status": "NOT_REQUIRED",
            "reason": "NONE",
            "provider": None,
            "blocks": [],
        }
        identity = dict(without_media)
        identity.pop("record_sha256")
        without_media["record_sha256"] = content_sha256(identity)
        validate_document_record(without_media)
        with self.assertRaises(DocumentError):
            validate_document_against_source(without_media, path)

    def test_rehashed_visual_record_cannot_masquerade_as_plain_text(self) -> None:
        record = self.extract("scan.png", PNG)
        changed = copy.deepcopy(record)
        changed["content_mode"] = "TEXT"
        changed["ocr"]["reason"] = "NONE"
        changed["ocr"]["status"] = "NOT_REQUIRED"
        identity = dict(changed)
        identity.pop("record_sha256")
        changed["record_sha256"] = content_sha256(identity)
        with self.assertRaises(DocumentError):
            validate_document_record(changed)

    def test_invalid_ocr_region_confidence_and_unit_fail_closed(self) -> None:
        cases = [
            {"unit_kind": "PAGE", "unit_index": 1, "region": {"x": 0, "y": 0, "width": 1, "height": 1}, "text": "x", "confidence": 1},
            {"unit_kind": "IMAGE", "unit_index": 1, "region": {"x": 0.8, "y": 0, "width": 0.5, "height": 1}, "text": "x", "confidence": 1},
            {"unit_kind": "IMAGE", "unit_index": 1, "region": {"x": 0, "y": 0, "width": 1, "height": 1}, "text": "x", "confidence": True},
        ]
        for result in cases:
            with self.subTest(result=result), self.assertRaises(DocumentError):
                self.extract(
                    "scan.png",
                    PNG,
                    ocr_provider=lambda _request, value=result: {
                        "provider": {
                            "component_id": "fixture-ocr",
                            "implementation_sha256": "1" * 64,
                            "model_id": "fixture-model",
                            "model_sha256": "2" * 64,
                        },
                        "blocks": [value],
                    },
                )

    def test_ocr_must_cover_every_required_page(self) -> None:
        with self.assertRaises(DocumentError):
            self.extract(
                "partial.pdf",
                partially_supported_two_page_pdf(),
                ocr_provider=lambda _request: {
                    "provider": {
                        "component_id": "fixture-ocr",
                        "implementation_sha256": "1" * 64,
                        "model_id": "fixture-model",
                        "model_sha256": "2" * 64,
                    },
                    "blocks": [{
                        "unit_kind": "PAGE",
                        "unit_index": 2,
                        "region": {"x": 0, "y": 0, "width": 1, "height": 1},
                        "text": "Visible",
                        "confidence": 1.0,
                    }],
                },
            )

    def test_truncated_png_signature_is_rejected(self) -> None:
        with self.assertRaises(DocumentError):
            self.extract("invalid.png", b"\x89PNG\r\n\x1a\nfixture-image-bytes")
        png_without_idat = PNG[:33] + PNG[55:]
        with self.assertRaises(DocumentError):
            self.extract("no-idat.png", png_without_idat)

    def test_extension_mismatch_symlink_and_unsafe_output_fail_closed(self) -> None:
        with self.assertRaises(DocumentError):
            self.extract("fake.pdf", b"not-pdf")
        source = self.write("source.txt", b"source")
        link = self.root / "link.txt"
        link.symlink_to(source)
        with self.assertRaises(DocumentError):
            extract_document(link, captured_at=CAPTURED_AT)
        docx_path = self.write("media.docx", docx_bytes())
        record = extract_document(docx_path, captured_at=CAPTURED_AT)
        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaises(DocumentError):
            materialize_embedded_media(record, docx_path, existing)
        canonical_parent = self.root.resolve() / "canonical"
        canonical_parent.mkdir()
        linked_parent = self.root / "linked"
        linked_parent.symlink_to(canonical_parent)
        with self.assertRaises(DocumentError):
            materialize_embedded_media(record, docx_path, linked_parent / "output")

    def test_materialization_rejects_output_root_symlink_swap(self) -> None:
        docx_path = self.write("race.docx", docx_bytes())
        record = extract_document(docx_path, captured_at=CAPTURED_AT)
        output = self.root / "race-output"
        external = self.root / "external"
        external.mkdir()
        captured = self.root / "captured-output"
        real_mkdir = os.mkdir

        def swap_after_mkdir(path: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
            real_mkdir(path, mode, dir_fd=dir_fd)
            if dir_fd is not None and path == output.name:
                os.rename(path, captured.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                os.symlink(external, path, dir_fd=dir_fd)

        with patch("integra_core.documents.os.mkdir", side_effect=swap_after_mkdir):
            with self.assertRaises(DocumentError):
                materialize_embedded_media(record, docx_path, output)
        self.assertEqual(list(external.iterdir()), [])

    def test_materialization_rejects_intermediate_ancestor_symlink_swap(self) -> None:
        docx_path = self.write("ancestor-race.docx", docx_bytes())
        record = extract_document(docx_path, captured_at=CAPTURED_AT)
        base = self.root / "base"
        safe = base / "safe"
        inner = safe / "inner"
        inner.mkdir(parents=True)
        external = self.root / "external-ancestor"
        (external / "inner").mkdir(parents=True)
        held = base / "held"
        output = inner / "output"
        real_open_chain = document_module._open_directory_chain

        def swap_before_open(path: Path) -> tuple[list[int], list[tuple[int, str, os.stat_result]]]:
            safe.rename(held)
            safe.symlink_to(external, target_is_directory=True)
            return real_open_chain(path)

        with patch(
            "integra_core.documents._open_directory_chain",
            side_effect=swap_before_open,
        ):
            with self.assertRaises(DocumentError):
                materialize_embedded_media(record, docx_path, output)
        self.assertEqual(list((external / "inner").iterdir()), [])

    def test_zip_traversal_duplicate_and_oversized_members_fail_closed(self) -> None:
        malicious = office_zip(
            {"word/document.xml": b"<w:document xmlns:w='urn:w'/>", "../escape": b"x"}
        )
        with self.assertRaises(DocumentError):
            self.extract("bad.docx", malicious)
        corrupted = bytearray(docx_bytes())
        marker = corrupted.find(b"First paragraph")
        self.assertGreater(marker, 0)
        corrupted[marker] ^= 1
        with self.assertRaises(DocumentError):
            self.extract("corrupt.docx", bytes(corrupted))


if __name__ == "__main__":
    unittest.main()
