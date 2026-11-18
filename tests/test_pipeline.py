import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from google.genai import errors as genai_errors

import extractor
import pipeline
from tests.helpers import FakeClient, extraction_json, record_dict, write_pdf


def client_error(code, message, status):
    return genai_errors.ClientError(code, {"error": {"code": code, "message": message, "status": status}})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tnocr test "))
        self.cache = self.tmp / "extracted"
        self.prompt_text, self.prompt_hash = pipeline.load_prompt()
        patcher = mock.patch.object(extractor.time, "sleep")  # no real back-off waits
        patcher.start()
        self.addCleanup(patcher.stop)

    def extract(self, client, pdf):
        return pipeline.extract_or_load(client, pdf, self.prompt_text, self.prompt_hash,
                                        "fake-model", "low", self.cache)

    def test_second_run_uses_cache_without_calling_gemini(self):
        pdf = write_pdf(self.tmp / "batch one.pdf")
        client = FakeClient({"batch one.pdf": extraction_json(record_dict())})
        first, cached1 = self.extract(client, pdf)
        second, cached2 = self.extract(client, pdf)
        self.assertEqual((cached1, cached2), (False, True))
        self.assertEqual(len(client.uploads), 1)
        self.assertEqual(first, second)
        self.assertEqual(client.deletes, 1)

    def test_different_pdf_with_same_name_is_extracted_again(self):
        pdf = write_pdf(self.tmp / "a" / "scan.pdf", "first")
        client = FakeClient({"scan.pdf": extraction_json(record_dict())})
        self.extract(client, pdf)
        other = write_pdf(self.tmp / "b" / "scan.pdf", "second")
        _, cached = self.extract(client, other)
        self.assertFalse(cached)
        self.assertEqual(len(client.uploads), 2)

    def test_old_cache_without_hash_is_still_used(self):
        pdf = write_pdf(self.tmp / "old.pdf")
        pipeline.save_cache(self.cache / "old.json", "old.pdf", "fake-model", self.prompt_hash,
                            pipeline.PDFExtraction.model_validate_json(extraction_json(record_dict())))
        client = FakeClient({})
        _, cached = self.extract(client, pdf)
        self.assertTrue(cached)
        self.assertEqual(client.uploads, [])

    def test_not_a_pdf_is_rejected_before_upload(self):
        bad = self.tmp / "notes.pdf"
        bad.write_text("this is plain text")
        client = FakeClient({})
        with self.assertRaises(extractor.PDFFileError):
            self.extract(client, bad)
        self.assertEqual(client.uploads, [])

    def test_rejected_key_is_not_retried(self):
        pdf = write_pdf(self.tmp / "x.pdf")
        client = FakeClient({"x.pdf": client_error(400, "API key not valid.", "INVALID_ARGUMENT")})
        with self.assertRaises(genai_errors.ClientError):
            self.extract(client, pdf)
        self.assertEqual(len(client.creates), 1)

    def test_temporary_error_retries_at_most_three_times(self):
        pdf = write_pdf(self.tmp / "x.pdf")
        server = genai_errors.ServerError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}})
        client = FakeClient({"x.pdf": server})
        with self.assertRaises(genai_errors.ServerError):
            self.extract(client, pdf)
        self.assertEqual(len(client.creates), extractor.MAX_ATTEMPTS)
        self.assertEqual(client.deletes, 1)

    def test_partial_failure_keeps_other_files(self):
        good1 = write_pdf(self.tmp / "good one.pdf", "1")
        broken = self.tmp / "broken.pdf"
        broken.write_bytes(b"not a pdf")
        good2 = write_pdf(self.tmp / "good two.pdf", "2")
        client = FakeClient({
            "good one.pdf": extraction_json(record_dict("Ada", "One"), record_dict("Bo", "One", page=2)),
            "good two.pdf": extraction_json(record_dict("Cy", "Two")),
        })
        events = []
        result = pipeline.run_batch([good1, broken, good2], "fake-key", lambda *e: events.append(e[0]),
                                    cache_dir=self.cache, client=client)
        self.assertEqual([f.status for f in result.files], ["done", "failed", "done"])
        self.assertEqual([f.waivers for f in result.files], [2, 0, 1])
        self.assertIn("not a PDF", result.files[1].message)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.stopped_reason, "")
        self.assertEqual(events, ["start", "done", "start", "failed", "start", "done"])

    def test_quota_error_stops_remaining_files_without_sending_them(self):
        first = write_pdf(self.tmp / "first.pdf", "1")
        second = write_pdf(self.tmp / "second.pdf", "2")
        quota = client_error(429, "Quota exceeded", "RESOURCE_EXHAUSTED")
        client = FakeClient({"first.pdf": quota, "second.pdf": extraction_json(record_dict())})
        result = pipeline.run_batch([first, second], "fake-key", cache_dir=self.cache, client=client)
        self.assertEqual([f.status for f in result.files], ["failed", "skipped"])
        self.assertNotIn("second.pdf", client.uploads)
        self.assertLessEqual(len(client.creates), extractor.MAX_ATTEMPTS)
        self.assertIn("limit", result.files[1].message)

    def test_stop_request_skips_remaining_files(self):
        pdfs = [write_pdf(self.tmp / f"f{i}.pdf", str(i)) for i in range(3)]
        client = FakeClient({p.name: extraction_json(record_dict()) for p in pdfs})
        stop = threading.Event()

        def on_event(kind, *args):
            if kind == "done":
                stop.set()

        result = pipeline.run_batch(pdfs, "k", on_event, stop, cache_dir=self.cache, client=client)
        self.assertEqual([f.status for f in result.files], ["done", "skipped", "skipped"])
        self.assertEqual(client.uploads, ["f0.pdf"])

    def test_placeholder_key_counts_as_missing(self):
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": pipeline.PLACEHOLDER_KEY}):
            self.assertEqual(pipeline.get_api_key(), "")
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "  real-key  "}):
            self.assertEqual(pipeline.get_api_key(), "real-key")


if __name__ == "__main__":
    unittest.main()
