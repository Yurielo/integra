#!/usr/bin/env python3
"""Execute the pinned BookText CLI and normalize only its emitted OCR evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path


def _page_result(payload: dict, page: int) -> dict:
    value = payload.get(f"page-{page:04d}", {})
    return value[0] if isinstance(value, list) and value else value if isinstance(value, dict) else {}


def _confidence(page: dict) -> float:
    values = [item.get("confidence") for item in page.get("blocks", []) if isinstance(item, dict) and type(item.get("confidence")) in (int, float)]
    if not values:
        raise ValueError("BookText Surya output has no numeric confidence")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("BookText Surya output confidence is invalid")
    return sum(values) / len(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--booktext", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--surya", required=True)
    parser.add_argument("--vision", required=True)
    parser.add_argument("--pages")
    parser.add_argument("--exclude-pages")
    args = parser.parse_args()
    source, entrypoint, output = Path(args.source), Path(args.booktext), Path(args.output_dir)
    if any(path.is_symlink() or not path.is_file() for path in (source, entrypoint)):
        raise ValueError("BookText worker received an unsafe source or runtime")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="integra_booktext_", dir=output) as temporary:
        staging = Path(temporary) / ("source" + source.suffix.lower())
        shutil.copy2(source, staging)
        spec = importlib.util.spec_from_file_location("pinned_booktext", entrypoint)
        if spec is None or spec.loader is None:
            raise ValueError("BookText entrypoint cannot be loaded")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.SURYA_CLI = Path(args.surya)
        module.VISION_OCR = Path(args.vision)
        previous = sys.argv
        try:
            sys.argv = [str(entrypoint), "--ocr", "surya", "--raw-ocr", "--no-descriptions", str(staging)]
            for flag, value in (("--pages", args.pages), ("--exclude-pages", args.exclude_pages)):
                if value is not None:
                    sys.argv.extend([flag, value])
            module.main()
        finally:
            sys.argv = previous
        result = staging.parent / "source_book"
        if not result.is_dir() or result.is_symlink():
            raise ValueError("BookText produced no result directory")
        for item in result.iterdir():
            destination = output / item.name
            if destination.exists():
                raise ValueError("BookText output directory is not empty")
            shutil.move(str(item), destination)
    book = json.loads((output / "book.json").read_bytes())
    raw_files = sorted((output / "surya").rglob("results.json"))
    if not raw_files:
        raise ValueError("BookText Surya output is missing")
    raw = json.loads(raw_files[0].read_bytes())
    blocks = []
    for page in book.get("pages", []):
        number, text = page.get("page"), page.get("text")
        if not isinstance(number, int) or not isinstance(text, str) or not text.strip():
            raise ValueError("BookText returned an empty OCR page")
        blocks.append({"unit_index": number, "text": text.strip(), "confidence": _confidence(_page_result(raw, number))})
    if not blocks or any(item["confidence"] < 0 or item["confidence"] > 1 for item in blocks):
        raise ValueError("BookText OCR evidence is invalid")
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha256:
        raise ValueError("BookText source changed during OCR")
    outputs = {"text": "book_clean.txt", "markdown": "book.md", "record": "book.json", "review": "review.txt", "review_json": "review.json", "searchable_pdf": "book_ocr.pdf", "pages": "pages", "surya": "surya", "vision": "vision"}
    outputs = {key: value for key, value in outputs.items() if not (output / value).is_symlink() and ((output / value).is_dir() or ((output / value).is_file() and (output / value).stat().st_size > 0))}
    manifest = {
        "component": "booktext", "commit_sha": "46396649214275eb18054b670a842bace02d02e1",
        "entrypoint_sha256": hashlib.sha256(entrypoint.read_bytes()).hexdigest(),
        "blocks": blocks,
        "source_sha256": source_sha256,
        "selection": {"pages": args.pages, "exclude_pages": args.exclude_pages},
        "processed_pages": [item["unit_index"] for item in blocks],
        "qa_status": "COMPLETED" if book.get("qa_pages") and all("error" not in item for item in book["qa_pages"]) else "UNAVAILABLE_OR_PARTIAL",
        "searchable_pdf_status": "COMPLETED" if "searchable_pdf" in outputs else "UNAVAILABLE",
        "outputs": outputs,
    }
    (output / "integra_booktext_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
