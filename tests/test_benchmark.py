import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from integra_core.benchmark import (
    BenchmarkValidationError,
    CAPABILITY_IDS,
    canonical_bytes,
    sha256_file,
    validate_benchmark_record,
)


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(
            (ROOT / "state/capability_benchmark_v1.json").read_text(encoding="utf-8")
        )

    def test_accepted_record_is_valid(self):
        validate_benchmark_record(self.record)

    def test_capability_inventory_is_exact_and_ordered(self):
        self.assertEqual(
            tuple(item["id"] for item in self.record["capabilities"]), CAPABILITY_IDS
        )

    def test_selected_candidate_must_have_passing_evidence(self):
        record = copy.deepcopy(self.record)
        capability = record["capabilities"][0]
        capability["selection"]["primary"] = ["seminartext"]
        capability["selection"]["fallback"] = []
        with self.assertRaises(BenchmarkValidationError):
            validate_benchmark_record(record)

    def test_semantic_superiority_cannot_be_claimed(self):
        record = copy.deepcopy(self.record)
        record["capabilities"][4]["selection"]["semantic_superiority_claimed"] = True
        with self.assertRaises(BenchmarkValidationError):
            validate_benchmark_record(record)

    def test_source_mutation_and_protected_data_fail_closed(self):
        for field in ("source_repositories_changed", "protected_data_accessed", "gold_accessed"):
            record = copy.deepcopy(self.record)
            record[field] = True
            with self.assertRaises(BenchmarkValidationError):
                validate_benchmark_record(record)

    def test_canonical_bytes_and_file_hash_are_deterministic(self):
        value = {"z": 2, "a": [1, "тест"]}
        payload = canonical_bytes(value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.json"
            path.write_bytes(payload)
            self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    unittest.main()
