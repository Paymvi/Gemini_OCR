"""Drives the real Tk window with synthetic data. No Gemini calls."""
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

import gui
import pipeline
from tests.helpers import extraction, record_dict, write_pdf


class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = gui.TkinterDnD.Tk() if gui.TkinterDnD else tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.tmp = Path(tempfile.mkdtemp(prefix="tnocr gui "))
        env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key", "NIGHT_MODE": "0", "SIMPLE_VIEW": "0"})
        env.start()
        self.addCleanup(env.stop)
        boxes = mock.patch.multiple(gui.messagebox, askyesno=mock.DEFAULT, showinfo=mock.DEFAULT,
                                    showwarning=mock.DEFAULT, showerror=mock.DEFAULT)
        self.boxes = boxes.start()
        self.boxes["askyesno"].return_value = False  # "Open it now?" -> No
        self.addCleanup(boxes.stop)
        self.app = gui.App(self.root, output_dir=self.tmp / "output")

    def tearDown(self):
        self.root.destroy()

    def test_adding_the_same_pdf_twice_is_prevented(self):
        pdf = write_pdf(self.tmp / "folder with spaces" / "batch.pdf")
        copy = self.tmp / "elsewhere" / "batch copy.pdf"
        copy.parent.mkdir()
        shutil.copy(pdf, copy)
        before = pdf.read_bytes()
        self.app.add_paths([str(pdf)])
        self.app.add_paths([str(pdf), str(copy), str(self.tmp / "notes.txt")])
        self.assertEqual(len(self.app.items), 1)
        self.assertIn("Already in the list", self.app.files_note.cget("text"))
        self.assertIn("not a PDF", self.app.files_note.cget("text"))
        self.app.remove_selected()  # nothing selected: no-op
        self.app.file_tree.selection_set(self.app.file_tree.get_children())
        self.app.remove_selected()
        self.assertEqual(self.app.items, [])
        self.assertEqual(pdf.read_bytes(), before)  # source PDF untouched

    def test_night_mode_toggles_and_is_remembered(self):
        env_file = self.tmp / ".env"
        with mock.patch.object(pipeline, "ENV_PATH", env_file):
            self.app.toggle_night()
            self.assertEqual(gui.ttk.Style(self.root).theme_use(), "clam")
            self.assertEqual(self.app.btn_night.cget("text"), "Day mode")
            self.assertIn("NIGHT_MODE=1", env_file.read_text())
            self.app.toggle_night()
            self.assertEqual(gui.ttk.Style(self.root).theme_use(), self.app.day_theme)
            self.assertIn("NIGHT_MODE=0", env_file.read_text())

    def test_simple_view_toggles_and_is_remembered(self):
        env_file = self.tmp / ".env"
        with mock.patch.object(pipeline, "ENV_PATH", env_file):
            self.app.toggle_simple()
            self.assertEqual(gui.ttk.Style(self.root).theme_use(), "clam")
            self.assertEqual(self.app.btn_simple.cget("text"), "Classic view")
            self.assertEqual(self.app.review_tree.cget("displaycolumns"), gui.SIMPLE_COLUMNS)
            self.assertIn("SIMPLE_VIEW=1", env_file.read_text())
            self.assertEqual(self.app.btn_process.cget("text"), "▶  Process PDFs")
            self.assertFalse(self.app.save_hint.winfo_manager())  # help sentences hidden...
            self.assertEqual(self.app.help_labels[0][0].cget("text"), "?")  # ...behind a "?"
            self.app.output_mode.set("master")
            self.app.toggle_simple()
            self.assertEqual(gui.ttk.Style(self.root).theme_use(), self.app.day_theme)
            self.assertEqual(self.app.review_tree.cget("displaycolumns"), ("#all",))
            self.assertEqual(self.app.btn_process.cget("text"), "Process PDFs")
            self.assertEqual(self.app.save_hint.winfo_manager(), "grid")
            self.assertEqual(self.app.help_labels[0][0].cget("text"), "")
            self.assertIn("SIMPLE_VIEW=0", env_file.read_text())
            self.app.output_mode.set("master")
            self.app.toggle_simple()  # simple view never keeps the advanced "replace master" choice
            self.assertEqual(self.app.output_mode.get(), "new")

    def test_review_edit_and_save_with_a_failed_file(self):
        good = write_pdf(self.tmp / "good.pdf", "1")
        bad = write_pdf(self.tmp / "bad.pdf", "2")
        self.app.add_paths([str(good), str(bad)])
        metas = pipeline.records_for(good, extraction(record_dict("Ada", "Lovelace", flagged=("city",)),
                                                      record_dict("Bo", "Brown", email="bo@x.org")), {})
        result = pipeline.BatchResult(records=metas, files=[
            pipeline.FileResult(good, "done", 2),
            pipeline.FileResult(bad, "failed", 0, message="bad.pdf is not a PDF file, or it is damaged."),
        ])
        self.app._handle_event("finished", result)

        self.assertEqual(len(self.app.review_tree.get_children()), 2)
        self.assertIn("1 need review", self.app.summary_label.cget("text"))
        self.assertIn("bad.pdf", self.app.failure_label.cget("text"))
        self.app.file_tree.selection_set(self.app._file_iid(self.app.items[1]))
        self.app.show_file_info()  # full failure message for the selected file
        self.assertIn("damaged", self.boxes["showinfo"].call_args.args[1])
        self.app.only_review.set(True)
        self.app.refresh_review()
        self.assertEqual(len(self.app.review_tree.get_children()), 1)

        ada_iid = next(i for i, r in enumerate(self.app.rows) if r["First Name"] == "Ada")
        self.app.only_review.set(False)
        self.app.refresh_review()
        self.app.review_tree.selection_set(str(ada_iid))
        self.app.mark_checked()
        self.assertEqual(gui.row_status(self.app.rows[ada_iid]), "Checked")
        self.app.rows[ada_iid]["Last Name"] = "Lovelace-King"  # as the edit dialog would

        self.app.save_spreadsheet()
        saved = self.app.last_saved
        self.assertTrue(saved.name.startswith("contacts_"))
        wb = load_workbook(saved)
        self.assertIn("Lovelace-King", [c.value for c in wb.worksheets[0]["E"]])
        self.assertIn(("bad.pdf", "Failed", 0, "bad.pdf is not a PDF file, or it is damaged."),
                      list(wb["Files"].iter_rows(min_row=2, values_only=True)))
        self.assertFalse(self.app.unsaved)
        self.assertFalse(self.app.draft_path.exists())  # saved, so no backup copy is left behind

        self.app.save_spreadsheet()  # second save -> second file, first untouched
        self.assertNotEqual(self.app.last_saved, saved)
        self.assertEqual(len(list((self.tmp / "output").glob("contacts_*.xlsx"))), 2)

    def test_unsaved_corrections_survive_a_crash(self):
        good = write_pdf(self.tmp / "good.pdf")
        metas = pipeline.records_for(good, extraction(record_dict("Ada", "Lovelace", flagged=("city",))), {})
        self.app._handle_event("finished", pipeline.BatchResult(metas, [pipeline.FileResult(good, "done", 1)]))
        self.app.review_tree.selection_set("0")
        self.app.mark_checked()
        self.assertTrue(self.app.draft_path.exists())
        self.assertNotIn(self.tmp / "output", self.app.draft_path.parents)  # not among the spreadsheets

        self.root.destroy()  # crash: no save, no close prompt
        self.root = gui.TkinterDnD.Tk() if gui.TkinterDnD else tk.Tk()
        self.root.withdraw()
        self.boxes["askyesno"].return_value = True  # "Restore them?" -> Yes
        app = gui.App(self.root, output_dir=self.tmp / "output")
        self.assertEqual(gui.row_status(app.rows[0]), "Checked")
        self.assertTrue(app.unsaved)
        self.assertIn("Restored 1", app.progress_label.cget("text"))

        self.boxes["askyesno"].return_value = False  # restart again, choose No: the copy is deleted
        self.root.destroy()
        self.root = gui.TkinterDnD.Tk() if gui.TkinterDnD else tk.Tk()
        self.root.withdraw()
        self.assertEqual(gui.App(self.root, output_dir=self.tmp / "output").rows, [])
        self.assertFalse(app.draft_path.exists())

    def test_master_mode_needs_confirmation(self):
        good = write_pdf(self.tmp / "good.pdf")
        metas = pipeline.records_for(good, extraction(record_dict()), {})
        self.app._handle_event("finished", pipeline.BatchResult(metas, [pipeline.FileResult(good, "done", 1)]))
        self.app.output_mode.set("master")
        self.app.save_spreadsheet()  # askyesno -> False: user declined
        self.assertFalse((self.tmp / "output" / "master_contacts.xlsx").exists())
        self.boxes["askyesno"].side_effect = [True, False]  # confirm replace, don't open
        self.app.save_spreadsheet()
        self.assertTrue((self.tmp / "output" / "master_contacts.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
