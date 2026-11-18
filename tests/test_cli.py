import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

import main
from spreadsheet import HEADERS
from tests.helpers import FakeClient, extraction_json, record_dict, write_pdf


class CommandLineTests(unittest.TestCase):
    """`python main.py` keeps its behavior: input/*.pdf -> output/master_contacts.xlsx."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tnocr cli "))
        for name in ("INPUT_DIR", "EXTRACTED_DIR", "OUTPUT_DIR"):
            patcher = mock.patch.object(main, name, self.tmp / name.split("_")[0].lower())
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(main, "SOURCE_LINKS_PATH", self.tmp / "source_links.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"})
        env.start()
        self.addCleanup(env.stop)

    def run_main(self, client):
        out = io.StringIO()
        with mock.patch.object(main, "make_client", return_value=client), contextlib.redirect_stdout(out):
            main.main()
        return out.getvalue()

    def test_processes_input_folder_and_reuses_cache(self):
        write_pdf(self.tmp / "input" / "Fall retreat.pdf")
        client = FakeClient({"Fall retreat.pdf": extraction_json(
            record_dict("Ada", "Lovelace"), record_dict("Ada", "Lovelace", page=2, visit_date="01/11/2020"))})

        first = self.run_main(client)
        self.assertIn("Extracting: Fall retreat.pdf", first)
        self.assertIn("Extracted waiver records: 2", first)
        master = self.tmp / "output" / "master_contacts.xlsx"
        ws = load_workbook(master).worksheets[0]
        self.assertEqual([c.value for c in ws[1]], HEADERS)
        self.assertEqual(ws.max_row, 2)  # the two visits merged into one contact
        self.assertEqual(ws.cell(row=2, column=HEADERS.index("Visit Count") + 1).value, 2)

        second = self.run_main(client)
        self.assertIn("Using cached JSON: Fall retreat.pdf", second)
        self.assertEqual(len(client.uploads), 1)

    def test_no_pdfs_message(self):
        out = self.run_main(FakeClient({}))
        self.assertIn("No PDFs found in", out)

    def test_missing_key_message_unchanged(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY is missing"):
                main.main()


if __name__ == "__main__":
    unittest.main()
