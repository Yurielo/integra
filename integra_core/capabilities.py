"""Central source detection, capability registry, and dependency planner for UI."""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from .documents import FORMAT_BY_SUFFIX, DocumentError, extract_document
from .protocol import content_sha256
from .user_media import SUPPORTED as MEDIA_EXTENSIONS, ffmpeg_preflight, preflight
from .seminartext_runtime import preflight as seminartext_preflight
from .word_timeline_runtime import preflight as word_timeline_preflight
from .videotext_runtime import preflight as videotext_preflight
from .booktext_runtime import preflight as booktext_preflight
from .youtube_runtime import preflight as youtube_preflight

VIDEO = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
AUDIO = MEDIA_EXTENSIONS - VIDEO
YOUTUBE = re.compile(r"^(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/", re.I)
PLAYLIST = re.compile(r"[?&]list=", re.I)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capability(identifier: str, title: str, category: str, source_types: set[str],
                component: str, implemented: bool, dependencies: list[str],
                *, available: bool = False, reason: str = "") -> dict[str, Any]:
    if not implemented:
        ui_state = "В разработке"
    elif available:
        ui_state = "Доступно"
    else:
        ui_state = f"Недоступно: {reason}" if reason else "Недоступно"
    return {
        "id": identifier, "title": title, "category": category,
        "source_types": sorted(source_types), "component": component,
        "implementation_state": "IMPLEMENTED" if implemented else "NOT_IMPLEMENTED",
        "runtime_available": available if implemented else False,
        "dependencies": dependencies, "reason": reason, "ui_state": ui_state,
    }


def detect_source(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip(): raise ValueError("source is required")
    value = value.strip()
    if YOUTUBE.match(value):
        source_type = "YOUTUBE_PLAYLIST" if PLAYLIST.search(value) else "YOUTUBE_VIDEO"
        return {"source_id":f"url:{content_sha256({'url':value})}", "display_name":value,
                "input":value, "source_type":source_type, "kind":"URL",
                "properties":{"remote_ingest_supported":source_type == "YOUTUBE_VIDEO"}}
    path = Path(value)
    if path.is_symlink() or not path.is_file(): raise ValueError("source must be a regular local file")
    path = path.resolve(strict=True); suffix = path.suffix.lower()
    if suffix in VIDEO: source_type="LOCAL_VIDEO"
    elif suffix in AUDIO: source_type="LOCAL_AUDIO"
    elif suffix in FORMAT_BY_SUFFIX:
        try: record=extract_document(path,captured_at="2000-01-01T00:00:00Z")
        except DocumentError as error: raise ValueError(str(error)) from error
        source_type=record["source"]["format"]
        properties={"content_mode":record["content_mode"],"ocr_status":record["ocr"]["status"],
                    "page_or_slide_count":record["page_or_slide_count"],
                    "native_text_characters":record["native_extraction"]["text_characters"],
                    "embedded_media_count":len(record["embedded_media"])}
        return {"source_id":record["source"]["source_id"],"display_name":path.name,"input":str(path),
                "source_type":source_type,"kind":"DOCUMENT","properties":properties}
    else: raise ValueError(f"unsupported source format: {suffix or 'no extension'}")
    digest = _sha256_file(path)
    return {"source_id":f"urn:integra:source:{uuid.uuid5(uuid.NAMESPACE_URL, digest)}",
            "display_name":path.name,"input":str(path),"source_type":source_type,"kind":"MEDIA",
            "properties":{"media_kind":"VIDEO" if source_type=="LOCAL_VIDEO" else "AUDIO",
                          "content_sha256":digest}}


def capability_registry(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    types={item["source_type"] for item in sources}; media=bool(types & {"LOCAL_VIDEO","LOCAL_AUDIO"})
    youtube_video="YOUTUBE_VIDEO" in types
    documents=bool(types & set(value[0] for value in FORMAT_BY_SUFFIX.values()))
    youtube=bool(types & {"YOUTUBE_VIDEO","YOUTUBE_PLAYLIST"})
    runtime={}; media_ready=False; media_reason=""; enhancement_ready=False; enhancement_reason=""; topics_ready=False; topics_reason=""; timeline_ready=False; timeline_reason=""; translation_ready=False; translation_reason=""; ocr_ready=False; ocr_reason=""; youtube_ready=False; youtube_reason=""
    if media or youtube_video:
        try: runtime=preflight(hash_model=False); media_ready=True
        except ValueError as error: media_reason=str(error)
        try: ffmpeg_preflight(); enhancement_ready=True
        except ValueError as error: enhancement_reason=str(error)
        try: seminartext_preflight(); topics_ready=True
        except ValueError as error: topics_reason=str(error)
        try: word_timeline_preflight(); timeline_ready=True
        except ValueError as error: timeline_reason=str(error)
        try: videotext_preflight(); translation_ready=True
        except ValueError as error: translation_reason=str(error)
    if youtube_video or "YOUTUBE_PLAYLIST" in types:
        try: youtube_preflight(); youtube_ready=True
        except ValueError as error: youtube_reason=str(error)
    if documents:
        try: booktext_preflight(); ocr_ready=True
        except ValueError as error: ocr_reason=str(error)
    native_docs=documents and all(item.get("properties",{}).get("ocr_status")!="REQUIRED" for item in sources if item["kind"]=="DOCUMENT")
    caps = [
        _capability("transcript","Расшифровка","Основная обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","YOUTUBE_VIDEO"},"integra.local_media_adapter",True,["youtube_ingest","media_preparation"] if youtube_video and not media else ["media_preparation"],available=(media or youtube_video) and media_ready and (not youtube_video or youtube_ready),reason=youtube_reason or media_reason),
        _capability("subtitles","Субтитры (SRT)","Основная обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","YOUTUBE_VIDEO"},"integra.local_media_adapter",True,["transcript"],available=(media or youtube_video) and media_ready and (not youtube_video or youtube_ready),reason=youtube_reason or media_reason),
        _capability("word_timeline","Word Timeline","Основная обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","YOUTUBE_VIDEO"},"seminartext",True,["transcript"],available=(media or youtube_video) and timeline_ready and (not youtube_video or youtube_ready),reason=youtube_reason or timeline_reason),
        _capability("topics","Темы и таймкоды","Основная обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","YOUTUBE_VIDEO"},"seminartext",True,["word_timeline"],available=(media or youtube_video) and topics_ready and timeline_ready and (not youtube_video or youtube_ready),reason=youtube_reason or topics_reason or timeline_reason),
        _capability("translation","Перевод","Основная обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","YOUTUBE_VIDEO"},"videotext",True,["transcript"],available=(media or youtube_video) and translation_ready and (not youtube_video or youtube_ready),reason=youtube_reason or translation_reason),
        _capability("review","Проверка / Review","Смысловая обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"seminartext",False,["topics"]),
        _capability("evidence","Evidence","Смысловая обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"seminartext",False,["review"]),
        _capability("knowledge","База знаний","Смысловая обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"seminartext",False,["evidence"]),
        _capability("summary","Краткое содержание","Смысловая обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"seminartext",False,["evidence"]),
        _capability("detailed_notes","Подробный конспект","Смысловая обработка",{"LOCAL_VIDEO","LOCAL_AUDIO","PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"seminartext",False,["evidence"]),
        _capability("burn_subtitles","Встроить субтитры","Видео / медиа",{"LOCAL_VIDEO"},"integra.local_media_adapter",True,["subtitles"],available=media and media_ready,reason=media_reason),
        _capability("clips","Создать тематические клипы","Видео / медиа",{"LOCAL_VIDEO"},"videotext",False,["topics"]),
        _capability("enhance_audio","Улучшить звук","Видео / медиа",{"LOCAL_VIDEO","LOCAL_AUDIO"},"integra.local_media_adapter",True,["media_preparation"],available=media and enhancement_ready,reason=enhancement_reason),
        _capability("social_versions","Версии для соцсетей","Видео / медиа",{"LOCAL_VIDEO"},"videotext",False,["clips"]),
        _capability("document_text","Извлечь текст","Основная обработка",{"PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"integra.document_adapter",True,["document_analysis"],available=documents and (native_docs or ocr_ready),reason=ocr_reason if documents and not native_docs else ""),
        _capability("document_structure","Сохранить структуру страниц","Структура",{"PDF","DOCX","PPTX","TXT","MARKDOWN","IMAGE"},"integra.document_adapter",True,["document_analysis"],available=documents),
        _capability("discover_images","Определить встроенные изображения","Основная обработка",{"PDF","DOCX","PPTX"},"integra.document_adapter",True,["document_analysis"],available=documents),
        _capability("ocr","OCR / извлечение текста","Основная обработка",{"PDF","IMAGE"},"booktext",True,["document_analysis"],available=documents and ocr_ready,reason=ocr_reason),
        _capability("extract_images","Извлечь изображения","Основная обработка",{"PDF","DOCX","PPTX"},"integra.document_adapter",True,["discover_images"],available=documents),
        _capability("document_outline","Главы, разделы и оглавление","Структура",{"PDF","DOCX","PPTX","TXT","MARKDOWN"},"booktext",False,["document_text"]),
        _capability("learning","Учебные материалы","Материалы",set(),"integra.learning",False,["knowledge"]),
        _capability("marketing","Маркетинговые материалы","Материалы",set(),"integra.marketing",False,["knowledge"]),
        _capability("publication_package","Подготовка публикации","Материалы",set(),"integra.publishing",False,["evidence"]),
        _capability("youtube_ingest","Загрузить видео из YouTube","Основная обработка",{"YOUTUBE_VIDEO"},"integra.youtube_adapter",True,[],available=youtube_video and youtube_ready,reason=youtube_reason),
        _capability("youtube_playlist_ingest","Загрузить плейлист YouTube","Основная обработка",{"YOUTUBE_PLAYLIST"},"integra.youtube_playlist_adapter",True,[],available="YOUTUBE_PLAYLIST" in types and youtube_ready,reason=youtube_reason),
        _capability("collection_alignment","Сопоставить источники коллекции","Коллекция",set(),"integra.alignment",False,["topics"]),
    ]
    result=[]
    for cap in caps:
        applies=(not cap["source_types"]) or bool(types & set(cap["source_types"]))
        if applies and (not youtube or cap["id"] in {"youtube_ingest", "youtube_playlist_ingest"} or (youtube_video and "YOUTUBE_VIDEO" in cap["source_types"]) or len(types)>1): result.append(cap)
    if media_ready:
        for cap in result:
            if cap["id"] in {"transcript","subtitles"}: cap["runtime"]={"engine":"whisper-cli","model":"verified at execution"}
    return result


def build_plan(sources: list[dict[str, Any]], selected: list[str]) -> dict[str, Any]:
    if not sources: raise ValueError("add at least one source")
    registry={item["id"]:item for item in capability_registry(sources)}
    if not selected: raise ValueError("select at least one available output")
    for identifier in selected:
        cap=registry.get(identifier)
        if not cap: raise ValueError(f"capability does not apply: {identifier}")
        if cap["implementation_state"]!="IMPLEMENTED" or not cap["runtime_available"]:
            raise ValueError(f"capability is not executable: {cap['title']} — {cap['ui_state']}")
    stages=[]
    def add(identifier: str) -> None:
        if identifier in {"media_preparation","document_analysis"}:
            title={"media_preparation":"Подготовка медиа","document_analysis":"Анализ документа"}[identifier]
            if identifier not in [item["id"] for item in stages]: stages.append({"id":identifier,"title":title,"technical":True})
            return
        cap=registry[identifier]
        if identifier == "document_text" and any(
            source.get("kind") == "DOCUMENT" and source.get("properties", {}).get("ocr_status") == "REQUIRED"
            for source in sources
        ):
            add("ocr")
        for dependency in cap["dependencies"]: add(dependency)
        if identifier not in [item["id"] for item in stages]: stages.append({"id":identifier,"title":cap["title"],"technical":False})
    for identifier in selected: add(identifier)
    source_plans=[]
    for source in sources:
        applicable=[identifier for identifier in selected if source["source_type"] in registry[identifier]["source_types"] or not registry[identifier]["source_types"]]
        source_plans.append({"source_id":source["source_id"],"display_name":source["display_name"],"source_type":source["source_type"],"outputs":applicable})
    identity={"sources":[item["source_id"] for item in sources],"selected_outputs":selected,"stages":[item["id"] for item in stages]}
    return {"schema_version":"1.0","plan_id":f"urn:integra:plan:{content_sha256(identity)}","sources":sources,
            "selected_outputs":selected,"stages":stages,"source_plans":source_plans,"state":"READY_TO_EXECUTE"}
