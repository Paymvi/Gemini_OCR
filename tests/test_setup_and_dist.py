import json
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import prepare_distribution  # noqa: E402
import setup_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tnocr setup ")) / "Waiver OCR (copy)"
        self.venv = self.root / ".venv"

    def test_missing_environment_is_detected(self):
        self.assertEqual(setup_env.venv_problem(self.venv), "no environment yet")

    def test_environment_copied_from_another_computer_is_rebuilt(self):
        python = setup_env.venv_python(self.venv)
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        (self.venv / setup_env.MARKER_NAME).write_text(
            json.dumps({"computer": "SOMEONE-ELSES-PC", "venv": "c:\\other\\.venv"}))
        self.assertIn("copied from another computer", setup_env.venv_problem(self.venv))

    def test_environment_that_cannot_run_is_rebuilt(self):
        python = setup_env.venv_python(self.venv)
        python.parent.mkdir(parents=True)
        python.write_bytes(b"not a program")
        self.assertIn("does not run", setup_env.venv_problem(self.venv))

    def test_real_project_environment_is_usable(self):
        # The developer's own .venv (if set up) is found and runs, even from a path with spaces.
        if not setup_env.venv_python(ROOT / ".venv").exists():
            self.skipTest("no .venv in this checkout")
        problem = setup_env.venv_problem(ROOT / ".venv")
        self.assertNotIn("does not run", problem)

    def test_folder_path_too_long_for_windows_is_reported(self):
        long_root = Path("C:/") / ("x" * 120)
        with mock.patch.object(setup_env, "long_paths_enabled", return_value=False):
            self.assertTrue(setup_env.path_too_long(long_root))
            self.assertFalse(setup_env.path_too_long(Path("C:/Users/someone/Documents/Waiver Contacts")))
        with mock.patch.object(setup_env, "long_paths_enabled", return_value=True):
            self.assertFalse(setup_env.path_too_long(long_root))

    def test_key_detection_ignores_placeholder(self):
        self.root.mkdir(parents=True)
        env = self.root / ".env"
        self.assertFalse(setup_env.key_configured(env))
        env.write_text("GEMINI_API_KEY=PASTE_YOUR_KEY_HERE\n")
        self.assertFalse(setup_env.key_configured(env))
        env.write_text("GEMINI_MODEL=x\nGEMINI_API_KEY=abc123\n")
        self.assertTrue(setup_env.key_configured(env))

    def test_batch_files_use_crlf_and_their_own_folder(self):
        for name in ("Setup.bat", "Open OCR App.bat", "Prepare Distribution.bat"):
            data = (ROOT / name).read_bytes()
            self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), name)
            self.assertIn(b'cd /d "%~dp0"', data, name)


class DistributionTests(unittest.TestCase):
    def test_clean_copy_excludes_private_and_machine_files(self):
        src = Path(tempfile.mkdtemp(prefix="tnocr dist ")) / "project with spaces"
        for relative in prepare_distribution.APP_FILES:
            (src / relative).parent.mkdir(parents=True, exist_ok=True)
            (src / relative).write_text("x")
        private = [".env", "source_links.json", "input/guest waiver.pdf", "output/master_contacts.xlsx",
                   "extracted/guest waiver.json", "logs/app.log", ".venv/pyvenv.cfg",
                   "__pycache__/gui.cpython-312.pyc", "GEMINI_OCR_COST_ANALYSIS.md"]
        for relative in private:
            (src / relative).parent.mkdir(parents=True, exist_ok=True)
            (src / relative).write_text("private")

        folder, archive = prepare_distribution.prepare(src, now=datetime(2026, 11, 18, 9, 0, 0))

        copied = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        expected = set(prepare_distribution.APP_FILES) | {"input/README.txt", "output/README.txt"}
        self.assertEqual(copied, expected)
        self.assertEqual(folder.name, "Waiver Contacts")
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        self.assertTrue(all(n.startswith("Waiver Contacts/") for n in names))
        self.assertFalse([n for n in names if n.endswith((".env", ".pdf", ".xlsx", ".log", ".json"))
                          and not n.endswith("source_links.example.json")])
        for relative in private:  # working folder untouched
            self.assertTrue((src / relative).exists(), relative)
        with self.assertRaises(FileExistsError):
            prepare_distribution.prepare(src, now=datetime(2026, 11, 18, 9, 0, 0))

    def test_all_listed_app_files_exist_in_this_project(self):
        missing = [f for f in prepare_distribution.APP_FILES if not (ROOT / f).exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
