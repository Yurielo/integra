from pathlib import Path
from types import SimpleNamespace
import unittest

from integra_core.seminartext_topic_detail_adapter import run_topics


class SeminarTextTopicDetailAdapterTests(unittest.TestCase):
    def test_adapter_passes_only_the_selected_detail_to_the_pinned_functions(self):
        items = [
            {"id": 1, "start": "00:00:00,000", "end": "00:00:10,000", "text": "Первый блок"},
            {"id": 2, "start": "00:00:10,000", "end": "00:00:20,000", "text": "Второй блок"},
        ]
        received = []
        fake = SimpleNamespace(
            parse_srt=lambda _: items,
            make_windows=lambda values: [values],
            analyze_window_boundaries=lambda *_args, **kwargs: received.append(kwargs["detail"]) or [1],
            topic_range_prompt=lambda values: values,
            run_ollama_topic_label=lambda _model, _prompt, start, end: {
                "start_id": start, "evidence_start_id": start, "evidence_end_id": end,
                "title": "Учебный план", "summary": "Краткое описание",
            },
            make_topics=lambda _items, rows: [{"title": rows[0]["title"]}],
        )
        result = run_topics(fake, Path("unused.srt"), "local-model", "high")
        self.assertEqual(received, ["high"])
        self.assertEqual(result["detail"], "high")
        self.assertEqual(result["topics"][0]["semantic_status"], "REVIEW_REQUIRED")

    def test_adapter_rejects_an_invented_detail_before_engine_execution(self):
        with self.assertRaisesRegex(ValueError, "topic detail"):
            run_topics(SimpleNamespace(), Path("unused.srt"), "local-model", "invented")
