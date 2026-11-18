import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from spreadsheet import (
    HEADERS,
    MASTER_FILENAME,
    build_master_rows,
    count_contact_rows,
    replace_master,
    review_reasons,
    save_rows_as_new,
    write_workbook,
)
from tests.helpers import extraction, record_dict

NOW = datetime(2026, 11, 18, 14, 30, 5)


def metas(*records, source="batch.pdf"):
    return [{"source_file": source, "source_path": f"C:/x/{source}", "source_link": f"file:///x#{i}",
             "record": r} for i, r in enumerate(extraction(*records).records)]


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="tnocr export "))
        self.rows = build_master_rows(metas(record_dict("Ada", "Lovelace", flagged=("email",)),
                                            record_dict("Bo", "Brown", email="bo@example.com", page=2)))

    def sheet(self, path):
        return load_workbook(path).worksheets[0]

    def test_each_save_creates_a_new_timestamped_file(self):
        first = save_rows_as_new(self.rows, self.out, now=NOW)
        second = save_rows_as_new(self.rows, self.out, now=NOW)
        self.assertEqual(first.name, "contacts_2026-11-18_14-30-05.xlsx")
        self.assertEqual(second.name, "contacts_2026-11-18_14-30-05_2.xlsx")
        self.assertEqual(len(list(self.out.glob("*.xlsx"))), 2)

    def test_existing_file_is_never_overwritten(self):
        taken = self.out / "contacts_2026-11-18_14-30-05.xlsx"
        taken.write_bytes(b"someone else's file")
        saved = save_rows_as_new(self.rows, self.out, now=NOW)
        self.assertNotEqual(saved, taken)
        self.assertEqual(taken.read_bytes(), b"someone else's file")

    def test_corrections_and_review_flags_are_exported(self):
        ada = next(r for r in self.rows if r["First Name"] == "Ada")
        ada["Email"] = "ada.corrected@example.com"
        ada["Email_Confident"] = True  # person ticked off the review flag
        bo = next(r for r in self.rows if r["First Name"] == "Bo")
        bo["City"] = "Fixed City"
        bo["City_Confident"] = False  # person flagged a field
        ws = self.sheet(save_rows_as_new(self.rows, self.out, now=NOW))
        headers = [c.value for c in ws[1]]
        self.assertEqual(headers, HEADERS)  # same columns as before; no internal "_" keys
        by_first = {row[headers.index("First Name")].value: row for row in ws.iter_rows(min_row=2)}
        ada_cells, bo_cells = by_first["Ada"], by_first["Bo"]
        self.assertEqual(ada_cells[headers.index("Email")].value, "ada.corrected@example.com")
        self.assertIs(ada_cells[headers.index("Email_Confident")].value, True)
        self.assertNotEqual(ada_cells[headers.index("Email")].fill.fgColor.rgb, "00FFF2CC")
        self.assertEqual(bo_cells[headers.index("City")].value, "Fixed City")
        self.assertEqual(bo_cells[headers.index("City")].fill.fgColor.rgb, "00FFF2CC")

    def test_files_sheet_lists_failed_files(self):
        summary = [("good.pdf", "Done", 2, ""), ("bad.pdf", "Failed", 0, "bad.pdf is not a PDF file")]
        wb = load_workbook(save_rows_as_new(self.rows, self.out, summary, now=NOW))
        self.assertEqual(wb.sheetnames, ["Master Contacts", "Files"])
        rows = list(wb["Files"].iter_rows(min_row=2, values_only=True))
        self.assertIn(("bad.pdf", "Failed", 0, "bad.pdf is not a PDF file"), rows)

    def test_replace_master_backs_up_previous_file(self):
        master = self.out / MASTER_FILENAME
        write_workbook(metas(record_dict("Old", "Contact")), master)
        old_bytes = master.read_bytes()
        path, backup = replace_master(self.rows, master, now=NOW)
        self.assertEqual(path, master)
        self.assertEqual(backup.read_bytes(), old_bytes)
        self.assertEqual(backup.parent.name, "backups")
        self.assertEqual(count_contact_rows(master), 2)
        self.assertEqual(count_contact_rows(backup), 1)
        self.assertEqual([p.name for p in self.out.glob(".*tmp")], [])

    def test_cli_writer_unchanged(self):
        path = self.out / MASTER_FILENAME
        write_workbook(metas(record_dict()), path)
        ws = self.sheet(path)
        self.assertEqual([c.value for c in ws[1]], HEADERS)
        self.assertEqual(load_workbook(path).sheetnames, ["Master Contacts"])

    def test_review_reasons_use_existing_flags_and_blank_names(self):
        ada = next(r for r in self.rows if r["First Name"] == "Ada")
        bo = next(r for r in self.rows if r["First Name"] == "Bo")
        self.assertEqual(review_reasons(ada), ["Email flagged"])
        self.assertEqual(review_reasons(bo), [])
        bo["Last Name"] = " "
        self.assertEqual(review_reasons(bo), ["Last Name is blank"])

    def test_rows_carry_source_page_for_review(self):
        bo = next(r for r in self.rows if r["First Name"] == "Bo")
        self.assertEqual((bo["_source_file"], bo["_source_page"]), ("batch.pdf", 2))


if __name__ == "__main__":
    unittest.main()
