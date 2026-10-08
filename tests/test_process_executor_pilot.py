"""PR191 executor contract QA with a simulated adapter, not real-provider proof.

All sources, canonical-state sentinels, and runtime evidence are synthetic.
Packaged-provider parity and subprocess cleanup are separate integration gates.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core import _timed_transcript_provider as provider
from integra_core import candidate_identity
from integra_core import process_executor_pilot as pilot


CAPABILITY = "process.timed_transcript.normalize.v1"
DEFAULT_REQUEST = object()
SOURCE = (
    b"7\r\n00:00:00,125 --> 00:00:01,250\r\n  Hello  \r\n\r\n"
    b"19\r\n00:00:01,250 --> 00:00:02,005\r\nSecond line\r\nkept intact\r\n"
)
NORMALIZED = (
    b"1\n00:00:00,125 --> 00:00:01,250\nHello\n\n"
    b"2\n00:00:01,250 --> 00:00:02,005\nSecond line\nkept intact\n"
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class ProcessExecutorPilotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="integra-pilot-qa-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.canonical = self.root / "canonical"
        self.canonical.mkdir()
        (self.canonical / "project.json").write_bytes(b'{"state":"ACCEPTED"}\n')
        (self.canonical / "transcript.srt").write_bytes(SOURCE)
        self.source = self.canonical / "transcript.srt"
        self.resources = self.root / "resources"
        self.resources.mkdir()
        (self.resources / "sentinel").write_bytes(b"synthetic runtime only")
        self.request = {
            "schema_version": "1.0",
            "capability_id": CAPABILITY,
            "project_id": "project-synthetic",
            "run_id": "run-synthetic",
            "source": {"source_id": "source-synthetic", "revision": "revision-1"},
            "input": {"artifact_id": "artifact-synthetic", "sha256": sha256(SOURCE), "format": "srt"},
            "options": {"media_duration_ms": 2005},
        }
        self.runtime = {
            "executor_id": "integra.timed-transcript-normalizer.v1",
            "provider": "videotext",
            "provider_commit": "a" * 40,
            "service_sha256": "b" * 64,
            "worker_sha256": "c" * 64,
            "worker": str(self.resources / "synthetic-worker"),
            "runtime_manifest_sha256": "d" * 64,
            "candidate_id": "synthetic-candidate",
            "bundle_digest": "e" * 64,
            "qa_evidence_kind": "SIMULATED_PROVIDER_NOT_PACKAGED_PROOF",
        }
        self.output = NORMALIZED
        self.cue_count = 2
        self.real_preflight = provider.preflight
        self.preflight = self.enterContext(patch.object(provider, "preflight", return_value=self.runtime))
        self.run_provider = self.enterContext(patch.object(provider, "run", side_effect=self.fake_run))

    def fake_run(self, runtime, source, target, *, cancelled, timeout_seconds, max_output_bytes):
        self.assertEqual(runtime, self.runtime)
        self.assertNotEqual(Path(source).resolve(), self.source.resolve())
        self.assertEqual(Path(source).read_bytes(), self.source.read_bytes())
        Path(target).write_bytes(self.output)
        return self.payload(target)

    def payload(self, target):
        return {
            "schema_version": "1.0", "component": "videotext",
            "capability": "subtitles", "operation": "normalize",
            "cue_count": self.cue_count, "output_srt": str(Path(target).resolve()),
            "skipped_zero_duration_count": 0, "warnings": [],
        }

    def snapshot(self, root):
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()
        }

    def cleanup_attempt(self, directory):
        directory = Path(directory)
        for path in directory.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o700)
        shutil.rmtree(directory)

    def execute(self, request=DEFAULT_REQUEST, input_path=None, **kwargs):
        before = self.snapshot(self.canonical)
        resources_before = self.snapshot(self.resources)
        actual_request = self.request if request is DEFAULT_REQUEST else request
        request_before = copy.deepcopy(actual_request)
        real_mkdtemp = tempfile.mkdtemp
        allocated = []

        def owned_directory(*args, **options):
            directory = real_mkdtemp(*args, **options)
            allocated.append(Path(directory).resolve())
            self.addCleanup(self.cleanup_attempt, directory)
            return directory

        with patch.object(tempfile, "mkdtemp", side_effect=owned_directory):
            envelope = pilot.execute(
                actual_request, self.source if input_path is None else input_path,
                resources=self.resources, **kwargs,
            )
        self.assertEqual(actual_request, request_before, "execution mutated caller request")
        self.assertEqual(self.snapshot(self.canonical), before, "canonical state changed")
        self.assertEqual(self.snapshot(self.resources), resources_before, "runtime resources changed")
        self.assertEqual(set(envelope), {"result", "evidence", "attempt_path"})
        attempt = Path(envelope["attempt_path"]).resolve()
        self.assertIn(attempt, allocated, "attempt must be a freshly owned OS temporary directory")
        self.assertFalse(attempt.is_relative_to(self.canonical))
        self.assertFalse(attempt.is_relative_to(self.resources))
        published = attempt / "published"
        self.assertEqual(json.loads((published / "result.json").read_text()), envelope["result"])
        self.assertEqual(json.loads((published / "evidence.json").read_text()), envelope["evidence"])
        result = envelope["result"]
        self.assertEqual(result["semantic_authority"], "MACHINE_UNVERIFIED")
        self.assertEqual(result["capability_id"], CAPABILITY)
        self.assertTrue(result["attempt_id"])
        self.assertFalse((attempt / "private").exists(), "private input/output residue")
        self.assertFalse((attempt / "pending").exists(), "uncommitted publication residue")
        self.assertEqual(stat.S_IMODE(published.stat().st_mode), 0o500)
        for artifact in published.iterdir():
            self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o400)
        result_bytes = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(envelope["evidence"]["result_sha256"], sha256(result_bytes))
        self.assertFalse(envelope["evidence"]["canonical_routing_changed"])
        public_json = json.dumps(result).lower()
        for private_value in ("videotext", "seminartext", "output_srt", "worker_sha256", "qa_evidence_kind"):
            self.assertNotIn(private_value, public_json)
        if result["status"] != "COMPLETED":
            self.assertEqual(result["artifacts"], [])
            self.assertEqual(set(result["error"]), {"code", "message"})
            self.assertTrue(result["error"]["code"])
            self.assertTrue(result["error"]["message"])
            self.assertFalse((published / "transcript.srt").exists())
        return envelope

    def assert_failed(self, **kwargs):
        envelope = self.execute(**kwargs)
        self.assertEqual(envelope["result"]["status"], "FAILED")
        return envelope

    def set_source(self, data):
        self.source.write_bytes(data)
        self.request["input"]["sha256"] = sha256(data)

    def test_simulated_success_preserves_cues_and_binds_publication(self):
        envelope = self.execute()
        result = envelope["result"]
        self.assertEqual(result["status"], "COMPLETED")
        self.assertIsNone(result["error"])
        for field in ("project_id", "run_id", "source"):
            self.assertEqual(result[field], self.request[field])
        self.assertRegex(result["request_sha256"], r"^[0-9a-f]{64}$")
        output = Path(envelope["attempt_path"]) / "published" / "transcript.srt"
        self.assertEqual(output.read_bytes(), NORMALIZED)
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(result["artifacts"][0]["sha256"], sha256(NORMALIZED))
        self.assertIn("videotext", json.dumps(envelope["evidence"]).lower())
        self.assertEqual(envelope["evidence"]["runtime"], self.runtime)
        self.assertEqual(envelope["evidence"]["input_sha256"], sha256(SOURCE))
        self.assertEqual(envelope["evidence"]["output_sha256"], sha256(NORMALIZED))
        request_bytes = json.dumps(self.request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(result["request_sha256"], sha256(request_bytes))
        self.preflight.assert_called_once()
        self.run_provider.assert_called_once()

    def test_replay_has_fresh_attempt_equal_request_hash_and_immutable_first_result(self):
        first = self.execute()
        first_published = Path(first["attempt_path"]) / "published"
        original = self.snapshot(first_published)
        second = self.execute()
        self.assertEqual(second["result"]["status"], "COMPLETED")
        self.assertNotEqual(first["attempt_path"], second["attempt_path"])
        self.assertNotEqual(first["result"]["attempt_id"], second["result"]["attempt_id"])
        self.assertEqual(first["result"]["request_sha256"], second["result"]["request_sha256"])
        self.assertEqual(self.snapshot(first_published), original)
        self.assertEqual((Path(second["attempt_path"]) / "published/transcript.srt").read_bytes(), NORMALIZED)

    def test_empty_options_and_explicit_null_have_same_request_identity(self):
        self.request["options"] = {}
        first = self.execute()
        self.request["options"] = {"media_duration_ms": None}
        second = self.execute()
        self.assertEqual(first["result"]["status"], "COMPLETED")
        self.assertEqual(second["result"]["status"], "COMPLETED")
        self.assertEqual(first["result"]["request_sha256"], second["result"]["request_sha256"])

    def test_request_identity_is_key_order_independent_and_binds_source_revision(self):
        first = self.execute()
        reordered = {key: self.request[key] for key in reversed(self.request)}
        reordered["source"] = {"revision": "revision-1", "source_id": "source-synthetic"}
        second = self.execute(request=reordered)
        self.assertEqual(first["result"]["request_sha256"], second["result"]["request_sha256"])
        changed = copy.deepcopy(self.request)
        changed["source"]["revision"] = "revision-2"
        third = self.execute(request=changed)
        self.assertNotEqual(first["result"]["request_sha256"], third["result"]["request_sha256"])

    def test_all_unnumbered_input_is_accepted_without_reordering(self):
        self.set_source(SOURCE.replace(b"7\r\n", b"", 1).replace(b"19\r\n", b"", 1))
        self.assertEqual(self.execute()["result"]["status"], "COMPLETED")

    def test_text_outer_whitespace_is_trimmed_but_internal_spacing_is_preserved(self):
        self.set_source(b"9\n00:00:00,001 --> 00:00:00,002\n  alpha  beta\n second line  \n")
        self.output = b"1\n00:00:00,001 --> 00:00:00,002\nalpha  beta\n second line\n"
        self.cue_count = 1
        self.assertEqual(self.execute()["result"]["status"], "COMPLETED")

    def test_closed_request_contract_rejects_missing_fields(self):
        for field in self.request:
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                del request[field]
                self.run_provider.reset_mock()
                self.assert_failed(request=request)
                self.run_provider.assert_not_called()

    def test_non_object_request_is_rejected_without_execution(self):
        for request in (None, [], "request", 1, True):
            with self.subTest(request=request):
                self.assert_failed(request=request)
                self.run_provider.assert_not_called()

    def test_missing_nested_identity_fields_are_rejected(self):
        for parent in ("source", "input"):
            for field in self.request[parent]:
                with self.subTest(parent=parent, field=field):
                    request = copy.deepcopy(self.request)
                    del request[parent][field]
                    self.assert_failed(request=request)
                    self.run_provider.assert_not_called()

    def test_closed_request_contract_rejects_unknown_fields_and_provider_controls(self):
        cases = [
            ((), "provider", "videotext"), ((), "runtime", "/tmp/runtime"),
            ((), "attempt_path", "../canonical"), ((), "extra", True),
            (("source",), "path", "../source.srt"),
            (("input",), "path", "../source.srt"),
            (("options",), "worker", "/tmp/worker"),
            (("options",), "output_srt", "../canonical/transcript.srt"),
            (("options",), "skip_zero_duration", True),
        ]
        for parents, key, value in cases:
            with self.subTest(parents=parents, key=key):
                request = copy.deepcopy(self.request)
                target = request
                for parent in parents:
                    target = target[parent]
                target[key] = value
                self.run_provider.reset_mock()
                self.assert_failed(request=request)
                self.run_provider.assert_not_called()

    def test_request_rejects_wrong_types_versions_hashes_and_durations(self):
        cases = [
            (("schema_version",), 1), (("schema_version",), "2.0"),
            (("capability_id",), "subtitles"), (("project_id",), ""),
            (("run_id",), 1), (("source",), []), (("input",), []),
            (("project_id",), "../canonical"), (("run_id",), "/canonical"),
            (("source", "revision"), "../revision"),
            (("input", "artifact_id"), "../transcript.srt"),
            (("options",), None), (("source", "source_id"), False),
            (("source", "revision"), 1), (("input", "artifact_id"), ""),
            (("input", "format"), "vtt"), (("input", "sha256"), "g" * 64),
            (("input", "sha256"), "a" * 63), (("input", "sha256"), 1),
        ]
        cases.extend((("options", "media_duration_ms"), value) for value in (True, False, 0, -1, 2005.0, "2005", [], {}))
        for path, value in cases:
            with self.subTest(path=path, value=value):
                request = copy.deepcopy(self.request)
                target = request
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.run_provider.reset_mock()
                self.assert_failed(request=request)
                self.run_provider.assert_not_called()

    def test_input_hash_mismatch_never_calls_provider(self):
        self.request["input"]["sha256"] = "0" * 64
        self.assert_failed()
        self.run_provider.assert_not_called()

    def test_execution_limits_reject_wrong_types_and_unbounded_values(self):
        cases = [
            ("timeout_seconds", value)
            for value in (True, None, 0, -1, float("inf"), float("nan"), 31, "5")
        ]
        cases.extend(("max_output_bytes", value) for value in (True, None, 0, -1, 1.5, "100", 2097153))
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.assert_failed(**{key: value})
                self.run_provider.assert_not_called()

    def test_provider_cannot_change_owned_input_then_publish_success(self):
        def run(runtime, source, target, **kwargs):
            payload = self.fake_run(runtime, source, target, **kwargs)
            Path(source).chmod(0o600)
            Path(source).write_bytes(b"modified owned input")
            return payload

        self.run_provider.side_effect = run
        envelope = self.assert_failed()
        self.assertEqual(envelope["result"]["error"]["code"], "INPUT_CHANGED")

    def test_noncanonical_input_is_rejected_before_provider(self):
        cases = {
            "empty": b"", "invalid_utf8": b"\xff", "garbage": b"not SRT",
            "zero_duration": b"1\n00:00:00,125 --> 00:00:00,125\nHello\n",
            "reversed_interval": b"1\n00:00:01,000 --> 00:00:00,000\nHello\n",
            "minute_overflow": b"1\n00:60:00,000 --> 01:00:01,000\nHello\n",
            "second_overflow": b"1\n00:00:60,000 --> 00:01:01,000\nHello\n",
            "end_minute_overflow": b"1\n00:00:00,000 --> 00:60:01,000\nHello\n",
            "end_second_overflow": b"1\n00:00:00,000 --> 00:00:60,000\nHello\n",
            "short_millis": b"1\n00:00:00,12 --> 00:00:01,000\nHello\n",
            "long_millis": b"1\n00:00:00,0000 --> 00:00:01,000\nHello\n",
            "decimal_separator": b"1\n00:00:00.125 --> 00:00:01.250\nHello\n",
            "blank_text": b"1\n00:00:00,000 --> 00:00:01,000\n  \n",
            "zero_id": NORMALIZED.replace(b"1\n", b"0\n", 1),
            "negative_id": NORMALIZED.replace(b"1\n", b"-1\n", 1),
            "duplicate_id": NORMALIZED.replace(b"\n2\n", b"\n1\n"),
            "decreasing_id": NORMALIZED.replace(b"1\n", b"3\n", 1),
            "mixed_numbering": NORMALIZED.replace(b"\n2\n", b"\n"),
            "overlap_one_millisecond": NORMALIZED.replace(b"01,250 -->", b"01,249 -->"),
            "exceeds_duration_one_millisecond": NORMALIZED.replace(b"02,005", b"02,006"),
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                self.set_source(data)
                self.run_provider.reset_mock()
                self.assert_failed()
                self.run_provider.assert_not_called()

    def test_provider_output_must_preserve_exact_input_semantics(self):
        cases = {
            "text_changed": NORMALIZED.replace(b"Hello", b"hello"),
            "start_changed_one_millisecond": NORMALIZED.replace(b"00,125", b"00,126"),
            "end_changed_one_millisecond": NORMALIZED.replace(b"02,005", b"02,004"),
            "skipped_ordinal": NORMALIZED.replace(b"\n2\n", b"\n3\n"),
            "missing_cue": NORMALIZED.split(b"\n\n")[0] + b"\n",
            "duplicate_cue": NORMALIZED + b"\n" + NORMALIZED,
            "mixed_numbering": NORMALIZED.replace(b"\n2\n", b"\n"),
            "minute_overflow": NORMALIZED.replace(b"00:00:00,125", b"00:60:00,125"),
            "invalid_utf8": b"\xff", "empty": b"", "garbage": b"garbage",
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                self.output = data
                self.assert_failed()

    def test_provider_cue_count_must_match_independently_inspected_output(self):
        self.cue_count = 3
        self.assert_failed()

    def test_preflight_failure_is_bounded_and_does_not_echo_provider_exception(self):
        self.preflight.side_effect = provider.PilotFailure("RUNTIME_IDENTITY_MISMATCH")
        envelope = self.assert_failed()
        self.assertEqual(envelope["result"]["error"]["code"], "RUNTIME_IDENTITY_MISMATCH")
        self.run_provider.assert_not_called()

    def test_malformed_nested_candidate_metadata_fails_preflight_without_launch(self):
        app = self.root / "Integra.app"
        self.resources = app / "Contents" / "Resources"
        seminar = self.resources / "runtime" / "seminartext"
        seminar.mkdir(parents=True)
        (seminar / "runtime.json").write_text("{}", encoding="utf-8")
        manifest_path = self.resources / "candidate-manifest.json"
        self.preflight.side_effect = self.real_preflight

        for components in (None, [], {"seminartext": []}):
            with self.subTest(components=components):
                identity = {"components": components}
                identity_sha256 = sha256(candidate_identity.canonical_bytes(identity))
                manifest = {
                    "schema_version": "1.0", "identity": identity,
                    "candidate_id": "candidate-v1-" + identity_sha256,
                    "identity_sha256": identity_sha256,
                    "bundle": {
                        "digest_algorithm": "sha256-tree-excluding-candidate-manifest",
                        "digest": candidate_identity.tree_sha256(
                            app, exclude={"Contents/Resources/candidate-manifest.json"}),
                    },
                }
                manifest_path.write_bytes(candidate_identity.canonical_bytes(manifest))
                # The malformed fixture reaches the nested-metadata regression.
                with self.assertRaises((AttributeError, ValueError)):
                    candidate_identity.validate_bundle(app)
                with patch.object(provider.subprocess, "Popen") as launch:
                    envelope = self.assert_failed()
                    launch.assert_not_called()
                self.assertEqual(envelope["result"]["error"]["code"], "RUNTIME_IDENTITY_MISMATCH")
                self.run_provider.assert_not_called()

    def test_provider_failure_is_bounded(self):
        self.run_provider.side_effect = provider.PilotFailure("PROVIDER_FAILED")
        self.assert_failed()

    def test_private_provider_failures_map_to_neutral_terminal_results(self):
        for code, status in (("TIMED_OUT", "TIMED_OUT"), ("CANCELLED", "CANCELLED"),
                             ("OUTPUT_LIMIT", "FAILED"), ("INVALID_PROVIDER_RESULT", "FAILED")):
            with self.subTest(code=code):
                self.run_provider.side_effect = provider.PilotFailure(code)
                envelope = self.execute()
                self.assertEqual(envelope["result"]["status"], status)
                self.assertEqual(envelope["result"]["error"]["code"], code)

    def test_unexpected_provider_exception_does_not_expose_private_details(self):
        self.run_provider.side_effect = OSError("videotext /private/provider-secret/worker failed")
        envelope = self.assert_failed()
        self.assertEqual(envelope["result"]["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("provider-secret", json.dumps(envelope["result"]))

    def test_cancelled_before_execution_never_calls_provider(self):
        envelope = self.execute(cancelled=lambda: True)
        self.assertEqual(envelope["result"]["status"], "CANCELLED")
        self.run_provider.assert_not_called()

    def test_cancellation_after_provider_output_prevents_success_publication(self):
        cancellation = {"requested": False}

        def run(runtime, source, target, **kwargs):
            payload = self.fake_run(runtime, source, target, **kwargs)
            cancellation["requested"] = True
            return payload

        self.run_provider.side_effect = run
        envelope = self.execute(cancelled=lambda: cancellation["requested"])
        self.assertEqual(envelope["result"]["status"], "CANCELLED")

    def test_cancellation_after_commit_does_not_rewrite_immutable_result(self):
        cancellation = {"requested": False}
        envelope = self.execute(cancelled=lambda: cancellation["requested"])
        published = Path(envelope["attempt_path"]) / "published"
        before = self.snapshot(published)
        cancellation["requested"] = True
        second = self.execute(cancelled=lambda: cancellation["requested"])
        self.assertEqual(second["result"]["status"], "CANCELLED")
        self.assertEqual(envelope["result"]["status"], "COMPLETED")
        self.assertEqual(self.snapshot(published), before)

    def test_publication_atomically_exposes_matching_records_and_ignores_late_cancel(self):
        cancellation = {"requested": False}
        real_rename = os.rename
        commits = []

        def commit(source, target, *args, **kwargs):
            staged = Path(source)
            destination = Path(target)
            if destination.name == "published":
                self.assertFalse(destination.exists())
                self.assertEqual(set(self.snapshot(staged)), {"result.json", "evidence.json", "transcript.srt"})
                result = json.loads((staged / "result.json").read_bytes())
                evidence = json.loads((staged / "evidence.json").read_bytes())
                self.assertEqual(result["status"], "COMPLETED")
                self.assertEqual(result["attempt_id"], evidence["attempt_id"])
                self.assertEqual(evidence["output_sha256"], sha256((staged / "transcript.srt").read_bytes()))
                cancellation["requested"] = True
                commits.append(destination)
            return real_rename(source, target, *args, **kwargs)

        with patch.object(os, "rename", side_effect=commit):
            envelope = self.execute(cancelled=lambda: cancellation["requested"])
        self.assertEqual(len(commits), 1)
        self.assertEqual(envelope["result"]["status"], "COMPLETED")

    def test_partial_publication_write_failure_publishes_only_neutral_failure(self):
        real_write = Path.write_bytes
        for filename in ("transcript.srt", "result.json", "evidence.json"):
            with self.subTest(filename=filename):
                failures = []

                def write(path, data):
                    if path.parent.name == "pending" and path.name == filename and not failures:
                        real_write(path, data[:7])
                        failures.append(path)
                        raise OSError("videotext /private/publication-secret partial write")
                    return real_write(path, data)

                with patch.object(Path, "write_bytes", new=write):
                    envelope = self.assert_failed()
                self.assertEqual(len(failures), 1)
                self.assertEqual(envelope["result"]["error"]["code"], "INTERNAL_ERROR")
                self.assertNotIn("publication-secret", json.dumps(envelope["result"]))
                self.assertNotIn("output_sha256", envelope["evidence"])
                published = Path(envelope["attempt_path"]) / "published"
                self.assertEqual(set(self.snapshot(published)), {"result.json", "evidence.json"})

    def test_publication_rename_failure_replaces_pending_success_with_failure(self):
        real_rename = os.rename
        attempted_statuses = []

        def rename(source, target, *args, **kwargs):
            if Path(target).name == "published":
                self.assertFalse(Path(target).exists())
                result = json.loads((Path(source) / "result.json").read_bytes())
                attempted_statuses.append(result["status"])
                if len(attempted_statuses) == 1:
                    raise OSError("videotext /private/publication-secret rename failed")
            return real_rename(source, target, *args, **kwargs)

        with patch.object(os, "rename", side_effect=rename):
            envelope = self.assert_failed()
        self.assertEqual(attempted_statuses, ["COMPLETED", "FAILED"])
        self.assertEqual(envelope["result"]["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("publication-secret", json.dumps(envelope["result"]))
        self.assertNotIn("output_sha256", envelope["evidence"])
        published = Path(envelope["attempt_path"]) / "published"
        self.assertEqual(set(self.snapshot(published)), {"result.json", "evidence.json"})

    def test_persistent_publication_failure_returns_truthful_memory_result_without_residue(self):
        real_write = Path.write_bytes
        real_rename = os.rename
        real_mkdtemp = tempfile.mkdtemp
        canonical_before = self.snapshot(self.canonical)
        resources_before = self.snapshot(self.resources)
        request_before = copy.deepcopy(self.request)

        for failure_point in ("result.json", "evidence.json", "rename"):
            with self.subTest(failure_point=failure_point):
                allocated = []
                failures = []

                def allocate(*args, **kwargs):
                    directory = real_mkdtemp(*args, **kwargs)
                    allocated.append(Path(directory).resolve())
                    self.addCleanup(self.cleanup_attempt, directory)
                    return directory

                def write(path, data):
                    if path.parent.name == "pending" and path.name == failure_point:
                        real_write(path, data[:7])
                        failures.append("write")
                        raise OSError("videotext /private/publication-secret disk failure")
                    return real_write(path, data)

                def rename(source, target, *args, **kwargs):
                    if Path(target).name == "published" and failure_point == "rename":
                        failures.append("rename")
                        raise OSError("videotext /private/publication-secret disk failure")
                    return real_rename(source, target, *args, **kwargs)

                with patch.object(tempfile, "mkdtemp", side_effect=allocate), \
                        patch.object(Path, "write_bytes", new=write), \
                        patch.object(os, "rename", side_effect=rename):
                    envelope = pilot.execute(self.request, self.source, resources=self.resources)

                self.assertEqual(len(failures), 2, "both success and failure publication must fail")
                attempt = Path(envelope["attempt_path"]).resolve()
                self.assertIn(attempt, allocated)
                self.assertEqual(list(attempt.iterdir()), [], "pending success or private bytes survived")
                result, evidence = envelope["result"], envelope["evidence"]
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["artifacts"], [])
                self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")
                self.assertTrue(result["error"]["message"])
                self.assertEqual(result["semantic_authority"], "MACHINE_UNVERIFIED")
                for field in ("project_id", "run_id", "source"):
                    self.assertEqual(result[field], self.request[field])
                self.assertIs(evidence["publication_persisted"], False)
                self.assertNotIn("output_sha256", evidence)
                self.assertNotIn("unpublished_cleanup_failed", evidence)
                self.assertEqual(evidence["result_sha256"], sha256(candidate_identity.canonical_bytes(result)))
                for private_value in ("videotext", "publication-secret", "worker_sha256"):
                    self.assertNotIn(private_value, json.dumps(result))
                self.assertEqual(self.snapshot(self.canonical), canonical_before)
                self.assertEqual(self.snapshot(self.resources), resources_before)
                self.assertEqual(self.request, request_before)

    def test_missing_input_directory_and_symlink_are_rejected(self):
        link = self.root / "link.srt"
        link.symlink_to(self.source)
        for path in (self.root / "missing.srt", self.canonical, link):
            with self.subTest(path=path):
                self.run_provider.reset_mock()
                self.assert_failed(input_path=path)
                self.run_provider.assert_not_called()

    def test_symlinked_input_parent_is_rejected(self):
        link = self.root / "linked-parent"
        link.symlink_to(self.canonical, target_is_directory=True)
        self.assert_failed(input_path=link / "transcript.srt")
        self.run_provider.assert_not_called()

    def test_symlinked_provider_output_is_not_published(self):
        outside = self.root / "outside.srt"
        outside.write_bytes(NORMALIZED)

        def run(runtime, source, target, **kwargs):
            Path(target).symlink_to(outside)
            payload = self.payload(target)
            payload["output_srt"] = str(target)
            return payload

        self.run_provider.side_effect = run
        self.assert_failed()
        self.assertEqual(outside.read_bytes(), NORMALIZED)

    def test_output_byte_limit_rejects_oversized_provider_artifact(self):
        self.assert_failed(max_output_bytes=len(NORMALIZED) - 1)

    def test_provider_receives_bounded_execution_controls(self):
        cancelled = lambda: False
        envelope = self.execute(cancelled=cancelled, timeout_seconds=0.75, max_output_bytes=8192)
        self.assertEqual(envelope["result"]["status"], "COMPLETED")
        self.assertEqual(self.run_provider.call_args.kwargs["timeout_seconds"], 0.75)
        self.assertEqual(self.run_provider.call_args.kwargs["max_output_bytes"], 8192)
        self.assertIs(self.run_provider.call_args.kwargs["cancelled"], cancelled)


if __name__ == "__main__":
    unittest.main()
