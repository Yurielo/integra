"""Real component smoke from a candidate bundle; synthetic fixtures only.

Run with Python 3.14. This proves bundled adapter execution, NOT native UI,
ASR quality, semantic acceptance or cloud publication. No checkout overrides.
Results/fixtures are retained in a new caller-selected directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_execution_guard import require_execution_path


def bundle_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0symlink\0" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def pdf_fixture(path):
    """Small three-page PDF with distinct rasterizable, non-private text."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [4 0 R 6 0 R 8 0 R] /Count 3 >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for number, word in enumerate(("ALPHA", "BRAVO", "CHARLIE"), 1):
        content_id = 5 + (number - 1) * 2
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        stream = f"BT /F1 28 Tf 60 680 Td (INTEGRA {word} PAGE {number}) Tj 0 -50 Td (Synthetic OCR acceptance fixture.) Tj ET".encode()
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ocr", action="store_true", help="Run real local OCR as well (may take minutes)")
    args = parser.parse_args()
    require_execution_path(args.app)
    require_execution_path(args.output)
    resources = args.app.resolve(strict=True) / "Contents/Resources"
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.output.resolve()
    for key in list(os.environ):
        if key.startswith("INTEGRA_"): del os.environ[key]
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONPATH"] = str(resources)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(resources))
    os.chdir(root)
    from integra_core import videotext_media_runtime as media
    from integra_core import seminartext_evidence_runtime as evidence
    from integra_core import booktext_runtime as book
    assert Path(media.__file__).is_relative_to(resources)
    report = {"level": "BUNDLE_COMPONENT_NOT_NATIVE_UI", "bundle": str(args.app.resolve()),
              "started_at": datetime.now(timezone.utc).isoformat(),
              "bundle_sha256": bundle_digest(args.app.resolve()), "results": {}}
    report_path = root / "smoke.json"
    def record(name, value):
        report["results"][name] = value
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(name + ": " + value["status"], flush=True)
    try:
        source = root / "synthetic.mp4"
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                        "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True, timeout=30)
        before = media.digest(source)
        srt = root / "fixture.srt"; srt.write_text("1\n00:00:00,100 --> 00:00:01,500\nIntegra synthetic fixture\n")
        clipped = media.cut(source, root / "clip.mp4", .2, 1.2, timeout=60)
        speed = media.adjust_speed(source, root / "speed.mp4", 1.25, timeout=60)
        burn = media.burn(source, srt, root / "burn.mp4", timeout=60)
        analysis = media.analyze_audio(source, root / "analysis.json", timeout=60)
        assert abs(clipped["duration_seconds"] - 1) < .25
        assert abs(speed["duration_seconds"] - 1.6) < .25
        assert before == media.digest(source)
        record("videotext", {"status": "PASS", "clip": clipped, "speed": speed, "burn": burn, "analysis": analysis})
        text = root / "transcript.txt"; text.write_text("Раз проверка\n")
        timeline = root / "timeline.json"
        timeline.write_text(json.dumps({"model": {"id": "synthetic-test", "revision": "fixture", "weights_sha256": "0" * 64},
            "aligner": {"name": "supplied-fixture-not-ASR", "version": "1"}, "words": [
            {"text": "Раз", "start_seconds": .1, "end_seconds": .3, "score": 1, "alignment_status": "ALIGNED"},
            {"text": "проверка", "start_seconds": .4, "end_seconds": .7, "score": 1, "alignment_status": "ALIGNED"}]}))
        result = evidence.create_machine_evidence(root, source_id="urn:integra:source:bundle-smoke", media_path=str(source),
            transcript_path=str(text), word_timeline_path=str(timeline))
        canonical = json.loads(Path(result["seminartext"]["canonical_evidence_path"]).read_text())
        revision = canonical["transcript_revisions"][0]
        assert revision["authority"] == "candidate"
        assert revision["transcript_provenance"]["verification_state"] == "machine_unverified"
        assert evidence._runtime_root()[1] == "BUNDLED_PERSONAL_RUNTIME"
        assert not list(root.rglob("canonical_knowledge.json"))
        record("seminartext", {"status": "PASS", "scope": "supplied synthetic transcript/timeline -> real Evidence, not ASR", "result": result})
        if args.ocr:
            pdf = root / "selection.pdf"; pdf_fixture(pdf)
            result = book.run_ocr(pdf, root / "ocr", pages="1-3", exclude_pages="2")
            assert result["processed_pages"] == [1, 3], result["processed_pages"]
            texts = {item["unit_index"]: item["text"].upper() for item in result["blocks"]}
            assert "ALPHA" in texts[1] and "CHARLIE" in texts[3], texts
            assert all("BRAVO" not in value for value in texts.values())
            assert result["source_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
            record("booktext", {"status": "PASS", "result": result})
        else:
            record("booktext", {"status": "NOT_RUN", "reason": "explicit --ocr not supplied"})
        assert bundle_digest(args.app.resolve()) == report["bundle_sha256"], "bundle changed during smoke"
    except Exception as error:
        record("failure", {"status": "FAIL", "type": type(error).__name__, "message": str(error)})
        raise


if __name__ == "__main__":
    main()
