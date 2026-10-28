"""Explicit, read-only, rebuildable Seminar Library preview over native manifests.

The projection has no semantic authority and never persists a catalog. Local
paths are locators only; native IDs and manifest hashes remain distinguishable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from .projects_sources import RegistryError, validate_registry


SCHEMA = Path(__file__).resolve().parents[1] / "schemas/seminar_library_preview_v1.schema.json"
OWNERS = {"seminartext", "videotext", "booktext", "integra"}
HEX = re.compile(r"^[a-f0-9]{64}$")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _hash(value):
    return value if isinstance(value, str) and HEX.fullmatch(value) else None


def _load(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"manifest must be a regular file: {path}")
    first = path.read_bytes()
    try:
        data = json.loads(first)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed manifest: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be an object: {path}")
    return path, data, digest(first), first


def _availability(root, locator, *, remote=False):
    if remote:
        return "UNVERIFIED_REMOTE"
    if not isinstance(locator, str) or not locator:
        return "UNKNOWN"
    candidate = Path(locator)
    if ".." in candidate.parts:
        return "UNSAFE_LOCATION"
    if not candidate.is_absolute():
        candidate = root / candidate
    # Inspect every path component without following a symlink into another tree.
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except (FileNotFoundError, PermissionError):
            return "MISSING"
        if stat.S_ISLNK(mode):
            return "SYMLINK"
    return "AVAILABLE" if candidate.is_file() else "MISSING"


def _key(owner, kind, native, input_hash, ordinal):
    # A preview record key, deliberately not a cross-product identity claim.
    return f"{owner}:{kind}:{digest(canonical([native, input_hash, ordinal]))[:24]}"


def _source(project, owner, native, kind, revision, locator, sha, root, provenance, ordinal, remote=False):
    availability = _availability(root, locator, remote=remote)
    return {"key": _key(owner, "source", [project["key"],native], project["input_sha256"], ordinal),
            "project_key": project["key"], "owner": owner, "native_id": native,
            "source_type": kind, "revision": revision, "revisions": [{"native_id":revision,"content_sha256":_hash(sha),"availability":availability,"provenance":provenance}] if revision else [],
            "locator": locator, "location_identity_sha256": digest(canonical(locator)) if isinstance(locator,str) else None,
            "semantic_identity": None, "availability": availability,
            "content_sha256": _hash(sha),
            "content_verification": "NOT_APPLICABLE" if remote else "NOT_CHECKED",
            "identity_kind": "CONTENT_IDENTITY" if _hash(sha) else "REMOTE_IDENTITY" if remote and native else "NATIVE_IDENTITY" if native else "UNRESOLVED",
            "provenance": provenance}


def _artifact(project, owner, native, kind, revision, source_ids, locator, sha, root, version, config, provenance, ordinal):
    availability = _availability(root, locator)
    return {"key": _key(owner, "artifact", [project["key"],native], project["input_sha256"], ordinal),
            "project_key": project["key"], "owner": owner, "native_id": native,
            "artifact_type": kind, "revision": revision, "revisions": [{"native_id":revision,"content_sha256":_hash(sha),"availability":availability,"provenance":provenance}] if revision else [],
            "source_ids": sorted(set(source_ids)), "locator": locator, "availability": availability,
            "content_sha256": _hash(sha), "producer_version": version,
            "content_verification": "NOT_CHECKED",
            "configuration_identity": config, "provenance": provenance}


def _project(owner, path, sha, native, title, classification, excluded):
    return {"key": _key(owner, "project", native, sha, 0), "owner": owner,
            "native_id": native, "seminar_id": native if classification == "SEMINAR" else None,
            "title": title, "classification": classification,
            "inclusion": "EXCLUDED_BY_USER" if excluded else "INCLUDED", "input_sha256": sha}


def _seminartext(path, data, sha, excluded):
    if data.get("schema_version") != 1 or not isinstance(data.get("videos"), list) or not isinstance(data.get("documents"), list):
        raise ValueError("unsupported SeminarText sources.json version or shape")
    meta = path.parent / "seminar.yaml"
    if meta.is_symlink() or not meta.is_file():
        raise ValueError("SeminarText project metadata missing or unsafe")
    raw = meta.read_bytes()
    title_match = re.search(r'^title:\s*["\']?([^\n"\']+)', raw.decode(), re.M)
    id_match = re.search(r'^id:\s*([a-zA-Z0-9_.:-]+)', raw.decode(), re.M)
    project = _project("seminartext", path, digest(canonical([sha, digest(raw)])), id_match.group(1) if id_match else None,
                       title_match.group(1).strip() if title_match else None, "SEMINAR", excluded)
    sources = []
    seen_native = set()
    for i, (item, family) in enumerate([(item, "VIDEO") for item in data["videos"]] + [(item, "DOCUMENT") for item in data["documents"]]):
        if not isinstance(item, dict):
            raise ValueError("malformed SeminarText source")
        allowed = {"local", "youtube"} if family == "VIDEO" else {"presentation", "handout", "other"}
        if item.get("type") not in allowed:
            raise ValueError("unsupported SeminarText source type")
        native = item.get("source_id")
        if not isinstance(native,str) or not native or native in seen_native:
            raise ValueError("SeminarText source ID missing or duplicated")
        seen_native.add(native)
        remote = item.get("type") == "youtube"
        locator = item.get("url") if remote else item.get("file")
        video_id = None
        if remote and isinstance(locator, str):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(locator)
            if parsed.hostname in {"youtu.be", "www.youtu.be"}:
                video_id = parsed.path.strip("/")
            elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
                video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            if not video_id or not VIDEO_ID.fullmatch(video_id):
                video_id = None
        record = _source(project, "seminartext", native, "YOUTUBE_VIDEO" if remote else "LOCAL_" + family,
                         None, locator, None, path.parent, {"manifest_sha256": sha, "youtube_video_id": video_id, "original_title": item.get("title")}, i, remote)
        if remote and video_id is None:record["identity_kind"]="UNRESOLVED"
        sources.append(record)
    artifacts = []
    evidence_path = path.parent / "evidence/manifest.json"
    if evidence_path.is_symlink():
        raise ValueError("unsafe SeminarText evidence manifest link")
    if evidence_path.is_file():
        _, evidence, evidence_sha, _ = _load(evidence_path)
        if evidence.get("schema_version") != 2 or evidence.get("artifact_type") != "seminartext.project_evidence_manifest":
            raise ValueError("unsupported SeminarText evidence manifest")
        if not _hash(evidence.get("bundle_sha256")) or not isinstance(evidence.get("registry_coverage"),list):
            raise ValueError("malformed SeminarText evidence manifest")
        bundle_locator = evidence.get("bundle_path")
        if not isinstance(bundle_locator,str) or Path(bundle_locator).is_absolute() or ".." in Path(bundle_locator).parts:
            raise ValueError("unsafe SeminarText evidence bundle locator")
        coverage_rows = evidence["registry_coverage"]
        if evidence.get("registered_source_count") != len(sources) or len(coverage_rows) != len(sources):
            raise ValueError("SeminarText evidence coverage count mismatch")
        source_keys = {source["native_id"]:source["key"] for source in sources}
        refs = []
        covered = set()
        for coverage in coverage_rows:
            if not isinstance(coverage,dict) or coverage.get("source_registry_id") not in source_keys:
                raise ValueError("SeminarText evidence references unknown source")
            if coverage["source_registry_id"] in covered or coverage.get("evidence_status") not in {"COMPOSED","EVIDENCE_UNAVAILABLE"}:
                raise ValueError("SeminarText evidence coverage duplicate or invalid")
            covered.add(coverage["source_registry_id"])
            if coverage.get("evidence_status") == "COMPOSED":
                refs.append(source_keys[coverage["source_registry_id"]])
        if evidence.get("source_count") != len(refs) or evidence.get("all_registered_sources_composed") != (len(refs)==len(sources)):
            raise ValueError("SeminarText evidence composition count mismatch")
        bundle = path.parent / bundle_locator
        if _availability(path.parent,bundle_locator) == "AVAILABLE":
            payload = bundle.read_bytes()
            if digest(payload) != evidence["bundle_sha256"]:
                raise ValueError("SeminarText evidence bundle hash mismatch")
            try:bundle_data=json.loads(payload)
            except json.JSONDecodeError:raise ValueError("malformed SeminarText evidence bundle")
            if not isinstance(bundle_data,dict) or bundle_data.get("schema_version")!="1.0.0" or bundle_data.get("artifact_type")!="seminartext.canonical_evidence":
                raise ValueError("unsupported SeminarText evidence bundle")
        artifact = _artifact(project,"seminartext",None,"seminartext.canonical_evidence",None,refs,
                             bundle_locator,evidence["bundle_sha256"],path.parent,None,None,
                             {"manifest_sha256":evidence_sha,"registered_source_count":evidence.get("registered_source_count")},0)
        if artifact["availability"] == "AVAILABLE":artifact["content_verification"]="VERIFIED"
        artifacts.append(artifact)
    return [project], sources, artifacts


def _videotext(path, data, sha, excluded, classified):
    if data.get("schemaVersion") != 8 or not isinstance(data.get("sourceMediaPath"), str):
        raise ValueError("unsupported VideoText manifest version or shape (expected v8)")
    native_artifacts = data.get("artifacts")
    if native_artifacts is None:native_artifacts=[]
    if not isinstance(native_artifacts,list):
        raise ValueError("malformed VideoText artifacts")
    root = path.parent.parent
    fingerprint = data.get("sourceFingerprint")
    if isinstance(fingerprint,dict) and fingerprint.get("standardizedPath") != data["sourceMediaPath"]:
        raise ValueError("stale VideoText source fingerprint path")
    project = _project("videotext", path, sha, None, root.name, "SEMINAR" if classified else "REVIEW_REQUIRED", excluded)
    src = _source(project, "videotext", None, "LOCAL_VIDEO", None, data["sourceMediaPath"], None, root,
                  {"manifest_sha256": sha, "source_fingerprint": data.get("sourceFingerprint"), "content_verification": "UNKNOWN"}, 0)
    artifacts = []
    transcript_revisions = data.get("transcriptRevisions")
    if transcript_revisions is None:transcript_revisions=[]
    if not isinstance(transcript_revisions,list) or any(not isinstance(r,dict) for r in transcript_revisions):
        raise ValueError("malformed VideoText transcript revisions")
    for i, item in enumerate(native_artifacts):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("kind"), str):
            raise ValueError("malformed VideoText artifact")
        known = [r for r in transcript_revisions if item["id"] in {r.get("transcriptArtifactID"),r.get("subtitleArtifactID")}]
        revision_id = known[-1].get("id") if known else None
        artifact = _artifact(project, "videotext", item["id"], item["kind"], revision_id,
                                   [src["key"]], item.get("path"), item.get("contentHash"), root,
                                   item.get("generatorVersion"), None, {"manifest_sha256": sha, "generator": item.get("generator"), "model": item.get("model"), "source_revision": item.get("sourceRevision"), "dependency_ids": item.get("dependencyIDs", [])}, i)
        artifact["revisions"] = [{"native_id":r.get("id"),"content_sha256":_hash(r.get("contentHash")),"availability":artifact["availability"],"provenance":{"parent_revision_id":r.get("parentRevisionID")}} for r in known]
        artifacts.append(artifact)
    return [project], [src], artifacts


def _booktext(path, data, sha, excluded, classified):
    if data.get("schema_version") != "0.1" or data.get("artifact_type") != "booktext.package_manifest":
        raise ValueError("unsupported BookText package manifest version or type")
    doc_path = path.parent / "document.json"
    doc, doc_sha = None, None
    if doc_path.is_file() and not doc_path.is_symlink():
        raw = doc_path.read_bytes();doc_sha = digest(raw)
        try:doc = json.loads(raw)
        except json.JSONDecodeError:raise ValueError("malformed BookText document")
    files = data.get("files")
    if not isinstance(files,list) or any(not isinstance(f,dict) for f in files):
        raise ValueError("malformed BookText package files")
    expected = next((f.get("sha256") for f in files if f.get("filename") == "document.json"), None)
    if doc is None or doc_sha != expected or doc.get("document_id") != data.get("document_id") or doc.get("revision_id") != data.get("revision_id"):
        raise ValueError("stale BookText package/document identity")
    if doc.get("schema_version") != "0.1" or doc.get("artifact_type") != "booktext.document" or not isinstance(doc.get("sources"), list):
        raise ValueError("unsupported BookText document")
    if any(not isinstance(item,dict) or not isinstance(item.get("source_id"),str) for item in doc["sources"]):
        raise ValueError("malformed BookText document source")
    # document_id is an artifact identity, not evidence of a BookText project ID.
    project = _project("booktext", path, digest(canonical([sha, doc_sha])), None, path.parent.name,
                       "SEMINAR" if classified else "REVIEW_REQUIRED", excluded)
    # A portable BookText source filename is display metadata, not a locator.
    sources = [_source(project, "booktext", item.get("source_id"), "DOCUMENT", None, None, item.get("sha256"), path.parent,
                       {"manifest_sha256": sha, "document_sha256": doc_sha, "source_index": item.get("source_index"), "original_filename": item.get("filename")}, i)
               for i, item in enumerate(doc["sources"])]
    artifact = _artifact(project, "booktext", doc["document_id"], "booktext.document", doc["revision_id"],
                         [s["key"] for s in sources], "document.json", doc_sha, path.parent, None, None,
                         {"manifest_sha256": sha, "package_status": data.get("package_status")}, 0)
    artifact["content_verification"]="VERIFIED"
    return [project], sources, [artifact]


def _integra(path, data, sha, excluded):
    if data.get("schema_version") != "1.0" or not isinstance(data.get("projects"), list) or not isinstance(data.get("sources"), list):
        raise ValueError("unsupported Integra Projects & Sources registry version or shape")
    validate_registry(data)
    projects = []
    for i, item in enumerate(data["projects"]):
        if not isinstance(item, dict) or not item.get("project_id"):
            raise ValueError("malformed Integra project")
        projects.append(_project("integra", path, sha, item["project_id"], item.get("title"),
                                 "SEMINAR" if item.get("kind") == "SEMINAR" else "OTHER", excluded))
    by_id = {p["native_id"]: p for p in projects}
    sources = []
    for i, item in enumerate(data["sources"]):
        if not isinstance(item, dict) or not item.get("source_id"):
            raise ValueError("malformed Integra source")
        revision = next((x for x in item.get("revisions", []) if x.get("revision_id") == item.get("current_revision_id")), None)
        if revision is None:
            raise ValueError("stale Integra source revision identity")
        provenance = revision.get("provenance", {})
        for project_id in item.get("project_ids", []):
            if project_id not in by_id:
                raise ValueError("Integra source refers to unknown project")
            locator = provenance.get("locator") or provenance.get("canonical_url")
            remote = item.get("source_type", "").startswith("YOUTUBE")
            content_hash = item.get("origin", {}).get("native_id") if not remote else None
            record = _source(by_id[project_id], "integra", item["source_id"], item.get("source_type", "UNKNOWN"),
                             revision["revision_id"], locator, content_hash, path.parent,
                             {"manifest_sha256": sha, "revision_sha256": revision.get("revision_sha256"), "native_provenance": provenance}, i, remote)
            if remote and revision.get("availability") == "INACCESSIBLE":record["availability"]="REMOTE_UNAVAILABLE"
            record["revisions"]=[{"native_id":r.get("revision_id"),"content_sha256":content_hash if not remote else None,
                                  "availability":"REMOTE_UNAVAILABLE" if remote and r.get("availability")=="INACCESSIBLE" else "UNVERIFIED_REMOTE" if remote else record["availability"],
                                  "provenance":{"revision_sha256":r.get("revision_sha256"),"previous_revision_id":r.get("previous_revision_id"),"native_provenance":r.get("provenance")}} for r in item["revisions"]]
            sources.append(record)
    return projects, sources, []


ADAPTERS = {"seminartext": _seminartext, "videotext": _videotext, "booktext": _booktext, "integra": _integra}


def build(specs, *, excluded=(), excluded_projects=(), classified=()):
    excluded = {str(Path(p).expanduser().absolute()) for p in excluded}
    classified = {str(Path(p).expanduser().absolute()) for p in classified}
    supplied_paths = {str(Path(p).expanduser().absolute()) for _, p in specs}
    if not excluded.issubset(supplied_paths) or not classified.issubset(supplied_paths):
        raise ValueError("exclusion/classification references a manifest not supplied for preview")
    inputs, projects, sources, artifacts, diagnostics, snapshots = [], [], [], [], [], []
    for owner, supplied in sorted(specs, key=lambda x: (x[0], str(Path(x[1]).absolute()))):
        if owner not in OWNERS:
            raise ValueError(f"unknown owner: {owner}")
        path, data, sha, raw = _load(supplied)
        inputs.append({"owner": owner, "manifest": str(path), "sha256": sha})
        snapshots.append((path, raw))
        companions = [path.parent / "seminar.yaml",path.parent / "evidence/manifest.json"] if owner == "seminartext" else [path.parent / "document.json"] if owner == "booktext" else []
        for companion in companions:
            if companion.is_file() and not companion.is_symlink():
                companion_raw = companion.read_bytes()
                inputs.append({"owner": owner, "manifest": str(companion), "sha256": digest(companion_raw)})
                snapshots.append((companion, companion_raw))
        try:
            args = (path, data, sha, str(path) in excluded)
            result = ADAPTERS[owner](*args, str(path) in classified) if owner in {"videotext", "booktext"} else ADAPTERS[owner](*args)
            p, s, a = result;projects.extend(p);sources.extend(s);artifacts.extend(a)
            if owner == "seminartext":
                for artifact in a:
                    bundle = path.parent / artifact["locator"]
                    if artifact["availability"] == "AVAILABLE":
                        bundle_raw = bundle.read_bytes()
                        if digest(bundle_raw) != artifact["content_sha256"]:
                            raise ValueError("SeminarText evidence bundle changed during preview")
                        inputs.append({"owner":owner,"manifest":str(bundle),"sha256":digest(bundle_raw)})
                        snapshots.append((bundle,bundle_raw))
        except (ValueError, TypeError, KeyError, UnicodeError, RegistryError) as exc:
            diagnostics.append(f"UNSUPPORTED_OR_INVALID:{owner}:{path}:{exc}")
    for path, raw in snapshots:
        if path.read_bytes() != raw:
            raise ValueError(f"stale input changed during preview: {path}")
    selectors = set(excluded_projects)
    matched = set()
    for project in projects:
        selector = f'{project["owner"]}:{project["native_id"]}' if project["native_id"] else None
        if selector in selectors:
            project["inclusion"] = "EXCLUDED_BY_USER"
            matched.add(selector)
    if selectors != matched:
        raise ValueError("exclusion references an unknown native project identity")
    included_keys={p["key"] for p in projects if p["inclusion"]=="INCLUDED"}
    sources=[s for s in sources if s["project_key"] in included_keys]
    artifacts=[a for a in artifacts if a["project_key"] in included_keys]
    inputs.sort(key=lambda x:(x["owner"],x["manifest"]));projects.sort(key=lambda x:x["key"]);sources.sort(key=lambda x:x["key"]);artifacts.sort(key=lambda x:x["key"]);diagnostics.sort()
    candidates = {}
    for source in sources:
        h=source["content_sha256"]
        if h:candidates.setdefault(h, []).append(source["key"])
    for h, keys in sorted(candidates.items()):
        if len(keys)>1:diagnostics.append("DUPLICATE_CANDIDATE:"+h+":"+",".join(sorted(keys)))
    for p in projects:
        if p["classification"] == "REVIEW_REQUIRED":diagnostics.append("CLASSIFICATION_REVIEW:"+p["key"])
        if p["native_id"] is None:diagnostics.append("UNRESOLVED_PROJECT_ID:"+p["key"])
    for s in sources:
        if s["native_id"] is None:diagnostics.append("UNRESOLVED_SOURCE_ID:"+s["key"])
        if s["source_type"] == "YOUTUBE_VIDEO" and s["owner"] == "seminartext" and not s["provenance"].get("youtube_video_id"):
            diagnostics.append("UNRESOLVED_YOUTUBE_VIDEO_ID:"+s["key"])
        if s["content_sha256"] is None and s["identity_kind"] != "REMOTE_IDENTITY":diagnostics.append("INCOMPLETE_CONTENT_HASH:"+s["key"])
        if s["availability"] in {"MISSING", "SYMLINK", "UNSAFE_LOCATION"}:diagnostics.append("SOURCE_"+s["availability"]+":"+s["key"])
    for artifact in artifacts:
        if artifact["native_id"] is None:diagnostics.append("UNRESOLVED_ARTIFACT_ID:"+artifact["key"])
        for field in ("content_sha256","producer_version","configuration_identity"):
            if artifact[field] is None:diagnostics.append("INCOMPLETE_ARTIFACT_"+field.upper()+":"+artifact["key"])
    diagnostics.sort()
    for name, records in (("projects",projects),("sources",sources),("artifacts",artifacts)):
        if len({record["key"] for record in records}) != len(records):
            raise ValueError(f"duplicate preview {name} keys")
    summary={"project_count":len(projects),"source_count":len(sources),"artifact_count":len(artifacts),
             "owner_products":sorted({x["owner"] for x in projects}),"missing_sources":sum(x["availability"] in {"MISSING","SYMLINK"} for x in sources),
             "unsupported_manifests":sum(x.startswith("UNSUPPORTED_OR_INVALID:") for x in diagnostics),
             "unresolved_identities":sum(x.startswith("UNRESOLVED_") for x in diagnostics),
             "excluded_projects":sum(x["inclusion"]=="EXCLUDED_BY_USER" for x in projects),
             "duplicate_candidate_references":sum(x.startswith("DUPLICATE_CANDIDATE:") for x in diagnostics),
             "incomplete_metadata":sum(x.startswith("INCOMPLETE_") for x in diagnostics)}
    result={"schema_version":"1.0","artifact_type":"integra.seminar_library_preview","inputs":inputs,"projects":projects,
            "sources":sources,"artifacts":artifacts,"diagnostics":diagnostics,"summary":summary}
    result["catalog_sha256"]=digest(canonical(result))
    validate(result)
    return result


def validate(value):
    """Dependency-free validation of the JSON Schema keywords used by v1."""
    schema=json.loads(SCHEMA.read_text())
    def check(item, rule, path):
        if "$ref" in rule:
            return check(item,schema["$defs"][rule["$ref"].split("/")[-1]],path)
        types=rule.get("type")
        if types is not None:
            types=types if isinstance(types,list) else [types]
            matching={"object":lambda x:isinstance(x,dict),"array":lambda x:isinstance(x,list),"string":lambda x:isinstance(x,str),
                      "integer":lambda x:isinstance(x,int) and not isinstance(x,bool),"null":lambda x:x is None}
            if not any(matching[t](item) for t in types):raise ValueError(f"{path}: invalid type")
        if "const" in rule and item!=rule["const"]:raise ValueError(f"{path}: invalid constant")
        if "enum" in rule and item not in rule["enum"]:raise ValueError(f"{path}: invalid enum")
        if "pattern" in rule and not re.fullmatch(rule["pattern"],item):raise ValueError(f"{path}: invalid pattern")
        if isinstance(item,dict):
            required=set(rule.get("required",[]))
            if not required.issubset(item):raise ValueError(f"{path}: missing fields")
            props=rule.get("properties",{})
            if rule.get("additionalProperties") is False and set(item)-set(props):raise ValueError(f"{path}: extra fields")
            for k,v in item.items():
                if k in props:check(v,props[k],path+"."+k)
        if isinstance(item,list) and "items" in rule:
            for i,v in enumerate(item):check(v,rule["items"],f"{path}[{i}]")
    check(value,schema,"$")
    for name in ("projects","sources","artifacts"):
        keys=[record["key"] for record in value[name]]
        if len(keys)!=len(set(keys)):raise ValueError(f"duplicate {name} key")
    project_keys={p["key"] for p in value["projects"] if p["inclusion"]=="INCLUDED"}
    source_keys={s["key"] for s in value["sources"]}
    if any(s["project_key"] not in project_keys for s in value["sources"]):raise ValueError("orphan source project")
    if any(a["project_key"] not in project_keys or not set(a["source_ids"]).issubset(source_keys) for a in value["artifacts"]):
        raise ValueError("orphan artifact reference")
    expected={"project_count":len(value["projects"]),"source_count":len(value["sources"]),"artifact_count":len(value["artifacts"])}
    if any(value["summary"].get(k)!=v for k,v in expected.items()):raise ValueError("preview summary count mismatch")
    if digest(canonical({k:v for k,v in value.items() if k!="catalog_sha256"}))!=value["catalog_sha256"]:raise ValueError("preview hash mismatch")


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for owner in sorted(OWNERS):parser.add_argument("--"+owner,action="append",default=[],metavar="MANIFEST")
    parser.add_argument("--exclude",action="append",default=[],metavar="MANIFEST")
    parser.add_argument("--exclude-project",action="append",default=[],metavar="OWNER:NATIVE_ID")
    parser.add_argument("--classify-seminar",action="append",default=[],metavar="MANIFEST")
    args=parser.parse_args(argv)
    specs=[(owner,p) for owner in sorted(OWNERS) for p in getattr(args,owner)]
    if not specs:parser.error("at least one product manifest is required")
    try:print(canonical(build(specs,excluded=args.exclude,excluded_projects=args.exclude_project,classified=args.classify_seminar)).decode(),end="")
    except (ValueError,OSError) as exc:parser.error(str(exc))


if __name__=="__main__":main()
