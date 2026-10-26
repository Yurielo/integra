"""Integra-owned, fail-closed local TranslateGemma runtime.

The source products remain read-only.  Integra owns only translation inference,
the bounded Ollama request, and validation of the derivative it creates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .ollama_runtime import resolve_ollama

COMPONENT = "integra.translation"
PROVIDER = "ollama"
MODEL = "translategemma:4b-it-q4_K_M"
# An installed tag is usable only with the exact governed manifest and layers.
# Artifact contracts retain MODEL; the actual request tag is separately bound.
INSTALLED_ALIAS = "translategemma:4b"
MODEL_FAMILY = "translategemma"
MODEL_DIGEST = "c49d986b0764f5881c476eb21435bb62b7abc62347aab3d4a6071e811be510a1"
WEIGHTS_DIGEST = "bdbf939b402e2f88fbe3e918beb777813009335756b4c17be7fe008dfe4815d4"
TEMPLATE_VERSION = "translategemma-ollama-v1"
ENDPOINT = "http://127.0.0.1:11434/api/chat"
SUPPORTED_LANGUAGES = frozenset({"ru", "en"})
_TIMESTAMP = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")


def _seconds(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise ValueError("translation input has an invalid SRT timestamp")
    hours, minutes, seconds, milliseconds = (int(item) for item in match.groups())
    if minutes > 59 or seconds > 59:
        raise ValueError("translation input has an invalid SRT timestamp")
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def _srt_cues(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("translation input subtitles are unavailable")
    blocks = re.split(r"\r?\n\r?\n", path.read_text(encoding="utf-8").strip())
    cues: list[dict[str, Any]] = []
    for block in blocks:
        lines = block.replace("\r\n", "\n").split("\n")
        if len(lines) < 3 or not lines[0].strip().isdigit() or " --> " not in lines[1]:
            raise ValueError("translation input subtitles are invalid")
        start, end = lines[1].split(" --> ", 1)
        start_seconds, end_seconds = _seconds(start), _seconds(end)
        text = "\n".join(lines[2:]).strip()
        if end_seconds <= start_seconds or not text:
            raise ValueError("translation input subtitles are invalid")
        cue_id = int(lines[0].strip())
        if cues and cue_id <= cues[-1]["id"]:
            raise ValueError("translation input subtitle IDs are invalid")
        cues.append({"id": cue_id, "start_seconds": start_seconds, "end_seconds": end_seconds, "text": text})
    if not cues:
        raise ValueError("translation input subtitles are empty")
    return cues


def _model_identity() -> tuple[str, str]:
    """Resolve the governed bytes, preferring their canonical daemon tag.

    A present but invalid canonical entry is an error, never a reason to try
    the installed alias. No model registration or download occurs here.
    """
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:
            payload = json.loads(response.read())
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ValueError("TranslateGemma model inventory is invalid")
        for tag in (MODEL, INSTALLED_ALIAS):
            matches = [m for m in models if isinstance(m, dict) and m.get("name") == tag]
            if matches:
                if len(matches) != 1 or matches[0].get("digest") != MODEL_DIGEST:
                    raise ValueError("TranslateGemma model identity is ambiguous or differs")
                return tag, MODEL_DIGEST
        raise ValueError("TranslateGemma model is unavailable")
    except (OSError, URLError, ValueError) as error:
        raise ValueError("TranslateGemma is unavailable or its exact model digest differs") from error


def _sha_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("TranslateGemma retained model bytes are unavailable")
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _verify_model_bytes(*, model: str = MODEL, hash_layers: bool = True) -> None:
    try:
        if model not in (MODEL, INSTALLED_ALIAS):
            raise ValueError("TranslateGemma request tag is unsupported")
        root = Path(os.environ.get('OLLAMA_MODELS', Path.home() / '.ollama/models'))
        manifest = root / 'manifests/registry.ollama.ai/library/translategemma' / model.split(':', 1)[1]
        if _sha_file(manifest) != MODEL_DIGEST:
            raise ValueError("TranslateGemma model manifest differs from the governed pin")
        record = json.loads(manifest.read_bytes())
        layers = record['layers'] + [record['config']]
        if not any(layer.get('digest') == 'sha256:' + WEIGHTS_DIGEST for layer in layers):
            raise ValueError("TranslateGemma weights differ from the governed pin")
        for layer in layers:
            name = layer.get('digest', '')
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', name):
                raise ValueError("TranslateGemma model layer identity is invalid")
            blob = root / 'blobs' / name.replace(':', '-')
            if blob.is_symlink() or not blob.is_file() or blob.stat().st_size != layer['size']:
                raise ValueError("TranslateGemma model layer bytes differ")
            if hash_layers and _sha_file(blob) != name[7:]:
                raise ValueError("TranslateGemma model layer bytes differ")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("TranslateGemma retained model bytes are unavailable or invalid") from error


def preflight(*, hash_model: bool = True) -> dict[str, Any]:
    """Return the pinned local identity without downloading or selecting a fallback.

    UI capability discovery may skip rereading every content-addressed layer;
    actual translation and Candidate validation retain the full byte hash.
    """
    executable = resolve_ollama()
    request_model, model_id = _model_identity()
    _verify_model_bytes(model=request_model, hash_layers=hash_model)
    try:
        version = subprocess.check_output([str(executable), '--version'], text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('TranslateGemma Ollama runtime is unavailable') from error
    identity = {
        "component": COMPONENT, "provider": PROVIDER, "model": MODEL,
        "model_family": MODEL_FAMILY, "model_id": model_id,
        "template_version": TEMPLATE_VERSION, "endpoint": ENDPOINT,
        "weights_sha256": WEIGHTS_DIGEST, "ollama_sha256": _sha_file(executable),
        "ollama_version": version,
    }
    # Preserve the canonical-only identity and its existing cache contracts.
    # Alias execution is explicit provenance and receives a distinct identity.
    if request_model != MODEL:
        identity["request_model"] = request_model
    return {
        "state": "READY", "ollama": str(executable), **identity,
        "runtime_identity_sha256": hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _prompt(text: str, source: str, target: str) -> str:
    # Keep the model responsible only for target-language text.  Integra owns
    # cue identity, timing and serialization instead of asking an LLM for JSON.
    return (
        f"You are a professional { {'ru': 'Russian', 'en': 'English'}[source]} ({source}) "
        f"to { {'ru': 'Russian', 'en': 'English'}[target]} ({target}) translator. "
        "Preserve meaning, names, terminology, numbers and line breaks. "
        f"Produce only the { {'ru': 'Russian', 'en': 'English'}[target]} translation, without commentary. "
        f"Translate the following { {'ru': 'Russian', 'en': 'English'}[source]} text:\n\n\n"
        f"{text}"
    )


def _translate_text(text: str, source: str, target: str, runtime: dict[str, Any]) -> str:
    request_model = runtime.get("request_model", runtime["model"])
    if runtime["model"] != MODEL or _model_identity() != (request_model, MODEL_DIGEST):
        raise ValueError("TranslateGemma request model differs from preflight")
    body = {
        "model": request_model, "stream": False,
        "messages": [{"role": "user", "content": _prompt(text, source, target)}],
        "options": {"temperature": 0.0, "num_predict": 1024},
    }
    request = Request(ENDPOINT, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("TranslateGemma did not return a validated translation") from error
    if not isinstance(payload, dict) or not isinstance(payload.get('message'), dict):
        raise ValueError("TranslateGemma runtime identity or response is invalid")
    content = payload['message'].get('content')
    if (payload.get("model") != request_model or payload.get('done') is not True
            or payload.get('done_reason') != 'stop' or not isinstance(content, str) or not content.strip()):
        raise ValueError("TranslateGemma runtime identity or response is invalid")
    if _model_identity() != (request_model, MODEL_DIGEST):
        raise ValueError("TranslateGemma request model differs from preflight")
    return content.strip()


def translate(subtitles: Path, output: Path, *, source: str, target: str,
              runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    """Translate an SRT as independently validated cues without source fallback."""
    if source not in SUPPORTED_LANGUAGES or target not in SUPPORTED_LANGUAGES or source == target:
        raise ValueError("translation languages are unsupported or identical")
    observed = preflight()
    runtime = observed if runtime is None else runtime
    if runtime != observed:
        raise ValueError("TranslateGemma runtime differs from the required configuration")
    cues = _srt_cues(subtitles)
    translated = []
    for cue in cues:
        text = _translate_text(cue["text"], source, target, runtime)
        translated.append({**cue, "text": text})
    payload = {
        "schema_version": "1.0", "component": COMPONENT, "capability": "translation",
        "provider": PROVIDER, "model": runtime["model"], "model_id": runtime["model_id"],
        "runtime_identity_sha256": runtime["runtime_identity_sha256"],
        "template_version": TEMPLATE_VERSION, "source_language": source, "target_language": target,
        "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED", "cues": translated, "issues": [],
    }
    if "request_model" in runtime:
        payload["request_model"] = runtime["request_model"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise ValueError("translation output destination already exists")
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload
