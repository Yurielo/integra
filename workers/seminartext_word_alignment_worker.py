#!/usr/bin/env python3
"""Build a real word timeline from an existing Integra transcript with WhisperX."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

MODEL_REVISION = "2329100508896c6d9b157019803ab5601e6f3406"
MODEL_SHA256 = "d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c"
MODEL_ID = "jonatasgrosman/wav2vec2-large-xlsr-53-russian"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seconds(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return round(int(hours) * 3600 + int(minutes) * 60 + float(rest), 3)


def parse_srt(path: Path) -> list[dict]:
    result = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace").strip()):
        lines = block.splitlines(); timing = next((line for line in lines if " --> " in line), None)
        if not timing:
            continue
        index = lines.index(timing); text = " ".join(lines[index + 1:]).strip()
        if not text:
            continue
        start, end = timing.split(" --> ")
        result.append({"start": seconds(start), "end": seconds(end), "text": text})
    if not result:
        raise ValueError("timed transcript has no speech segments")
    return result


def detect_language(segments: list[dict]) -> str:
    text = " ".join(segment["text"] for segment in segments)
    if re.search(r"[А-Яа-яЁё]", text):
        return "ru"
    raise ValueError("word alignment currently requires a Russian transcript")


def align(audio: Path, subtitles: Path, model_dir: Path) -> dict:
    import whisperx

    if not audio.is_file() or audio.is_symlink() or not subtitles.is_file() or subtitles.is_symlink():
        raise ValueError("owned audio or subtitles are unavailable")
    expected_weights = model_dir / "pytorch_model.bin"
    if not model_dir.is_dir() or not expected_weights.exists():
        raise ValueError("pinned Russian alignment model is unavailable")
    weights = expected_weights.resolve(strict=True)
    if not weights.is_file() or sha256(weights) != MODEL_SHA256:
        raise ValueError("pinned Russian alignment model hash differs")
    segments = parse_srt(subtitles)
    language = detect_language(segments)
    model, metadata = whisperx.load_align_model(
        language_code=language, device="cpu", model_name=str(model_dir), model_cache_only=True,
    )
    aligned = whisperx.align(segments, model, metadata, str(audio), device="cpu", return_char_alignments=False)
    words = []
    for segment_index, segment in enumerate(aligned.get("segments", [])):
        for raw in segment.get("words", []):
            text = str(raw.get("word", "")).strip()
            if not text:
                continue
            start, end = raw.get("start"), raw.get("end")
            is_aligned = isinstance(start, (int, float)) and isinstance(end, (int, float)) and float(end) > float(start)
            item = {
                "word_id": f"word:{len(words) + 1}", "sequence": len(words), "text": text,
                "source_segment_index": segment_index, "alignment_status": "ALIGNED" if is_aligned else "UNALIGNED",
                "start_seconds": round(float(start), 3) if is_aligned else None,
                "end_seconds": round(float(end), 3) if is_aligned else None,
                "score": round(float(raw["score"]), 6) if is_aligned and isinstance(raw.get("score"), (int, float)) else None,
                "timing_provenance": "WHISPERX_FORCED_ALIGNMENT" if is_aligned else "UNAVAILABLE",
                "qa_flags": [] if is_aligned else ["UNALIGNED_REVIEW_REQUIRED"],
            }
            words.append(item)
    if not words:
        raise ValueError("WhisperX produced no words")
    return {
        "schema_version": "1.0", "component": "seminartext", "capability": "word_timeline",
        "semantic_status": "MACHINE_ALIGNMENT_UNREVIEWED", "audio_sha256": sha256(audio),
        "subtitles_sha256": sha256(subtitles), "language": language,
        "aligner": {"name": "WhisperX", "version": "3.8.6", "mode": "ALIGNMENT_ONLY", "device": "cpu"},
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "weights_sha256": MODEL_SHA256},
        "words": words,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = align(args.audio.resolve(strict=True), args.srt.resolve(strict=True), args.model_dir.resolve(strict=True))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "word_count": len(result["words"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
