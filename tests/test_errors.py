import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import httpx
except ImportError:  # newer google-genai releases use httpx2
    import httpx2 as httpx
from google.genai import errors as genai_errors
from pydantic import ValidationError

from extractor import PDFFileError
from friendly_errors import describe_error, describe_save_error, scrub, technical_detail
from models import PDFExtraction


def api_error(cls, code, message, status):
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


class FriendlyErrorTests(unittest.TestCase):
    def kind(self, exc, path=None):
        return describe_error(exc, path).kind

    def test_classification(self):
        CE, SE = genai_errors.ClientError, genai_errors.ServerError
        self.assertEqual(self.kind(api_error(CE, 400, "API key not valid. Please pass a valid API key.",
                                             "INVALID_ARGUMENT")), "api_key")
        self.assertEqual(self.kind(api_error(CE, 403, "Permission denied", "PERMISSION_DENIED")), "api_key")
        self.assertEqual(self.kind(api_error(CE, 429, "Quota exceeded", "RESOURCE_EXHAUSTED")), "quota")
        self.assertEqual(self.kind(api_error(CE, 404, "models/x is not found", "NOT_FOUND")), "model")
        self.assertEqual(self.kind(api_error(SE, 503, "overloaded", "UNAVAILABLE")), "service")
        self.assertEqual(self.kind(httpx.ConnectError("getaddrinfo failed")), "network")
        self.assertEqual(self.kind(PDFFileError("x.pdf is empty (0 bytes).")), "pdf")
        self.assertEqual(self.kind(RuntimeError("??")), "unknown")

    def test_fatal_errors_stop_the_run_but_file_errors_do_not(self):
        quota = api_error(genai_errors.ClientError, 429, "Quota", "RESOURCE_EXHAUSTED")
        self.assertTrue(describe_error(quota).stops_run)
        self.assertTrue(describe_error(httpx.ConnectError("offline")).stops_run)
        self.assertFalse(describe_error(PDFFileError("bad")).stops_run)

    def test_encrypted_pdf_is_named(self):
        pdf = Path(tempfile.mkdtemp()) / "locked.pdf"
        pdf.write_bytes(b"%PDF-1.7\ntrailer<</Encrypt 5 0 R>>")
        err = api_error(genai_errors.ClientError, 400, "The document has no pages.", "INVALID_ARGUMENT")
        friendly = describe_error(err, pdf)
        self.assertEqual(friendly.kind, "pdf")
        self.assertIn("password-protected", friendly.message)

    def test_validation_error_detail_hides_waiver_contents(self):
        # Built at runtime so the name is not in this file's source (tracebacks show source lines).
        model_output = '{"records": [{"first_name": "%s"}]}' % ("Secret" + " Person")
        try:
            PDFExtraction.model_validate_json(model_output)
        except ValidationError as exc:
            friendly = describe_error(exc)
        self.assertEqual(friendly.kind, "response")
        self.assertNotIn("Secret Person", friendly.detail)
        self.assertNotIn("Secret Person", friendly.message)

    def test_api_keys_are_removed_from_details(self):
        fake_key = "AIza" + "x" * 35
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "my-configured-secret"}):
            text = scrub(f"url?key={fake_key} and my-configured-secret")
            detail = technical_detail(RuntimeError("failed with my-configured-secret"))
        self.assertNotIn(fake_key, text)
        self.assertNotIn("my-configured-secret", text)
        self.assertNotIn("my-configured-secret", detail)

    def test_locked_spreadsheet_message(self):
        friendly = describe_save_error(PermissionError(13, "denied"), Path("C:/out/master_contacts.xlsx"))
        self.assertIn("close it", friendly.message)
        self.assertIn("master_contacts.xlsx", friendly.message)


if __name__ == "__main__":
    unittest.main()
