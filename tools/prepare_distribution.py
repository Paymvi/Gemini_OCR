"""Make a clean copy of the app to give to another Windows computer.

Copies only an explicit list of app files into dist/<name>/ and a .zip next to it.
Never copied: .venv, .env (API key), input/ PDFs, extracted/ data, output/ spreadsheets,
logs/, source_links.json, caches and git history. Nothing in the working folder is changed
or deleted.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

APP_FILES = [
    "gui.py",
    "main.py",
    "pipeline.py",
    "extractor.py",
    "models.py",
    "spreadsheet.py",
    "friendly_errors.py",
    "prompt.md",
    "requirements.txt",
    ".env.example",
    "source_links.example.json",
    ".gitignore",
    "README.md",
    "QUICKSTART-WINDOWS.md",
    "Setup.bat",
    "Open OCR App.bat",
    "tools/setup_env.py",
    # Pictures used by QUICKSTART-WINDOWS.md (made-up example data only).
    "docs/screenshots/setup-finished.png",
    "docs/screenshots/settings-api-key.png",
    "docs/screenshots/app-overview.png",
    "docs/screenshots/1-add-pdfs.png",
    "docs/screenshots/2-processing.png",
    "docs/screenshots/2-finished-with-a-failed-file.png",
    "docs/screenshots/3-review.png",
    "docs/screenshots/3-edit-contact.png",
    "docs/screenshots/4-save.png",
]
EMPTY_FOLDERS = ["input", "output"]
FORBIDDEN_NAMES = {".env", "source_links.json", ".venv", "extracted", "logs", "__pycache__", ".git"}
FORBIDDEN_SUFFIXES = {".pdf", ".xlsx", ".log", ".pyc"}


def unsafe_entries(folder: Path) -> list[str]:
    """Anything private or machine-specific that ended up in the copy."""
    bad = []
    for path in folder.rglob("*"):
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            bad.append(str(path.relative_to(folder)))
    return bad


APP_FOLDER_NAME = "Waiver Contacts"  # short on purpose: Windows path-length limits during Setup


def prepare(root: Path = ROOT, dist_dir: Path | None = None, now: datetime | None = None) -> tuple[Path, Path]:
    """Creates dist/<timestamp>/Waiver Contacts/ and dist/Waiver-Contacts_<timestamp>.zip."""
    dist_dir = dist_dir or root / "dist"
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = dist_dir / stamp
    target = run_dir / APP_FOLDER_NAME
    archive_base = dist_dir / f"Waiver-Contacts_{stamp}"
    if run_dir.exists() or archive_base.with_suffix(".zip").exists():
        raise FileExistsError(f"{run_dir} already exists; not overwriting it.")

    missing = [f for f in APP_FILES if not (root / f).exists()]
    if missing:
        raise FileNotFoundError("These app files are missing: " + ", ".join(missing))

    for relative in APP_FILES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
    for folder in EMPTY_FOLDERS:
        (target / folder).mkdir(parents=True, exist_ok=True)
        (target / folder / "README.txt").write_text(
            f"This {folder} folder starts empty.\n", encoding="utf-8")

    bad = unsafe_entries(target)
    if bad:
        shutil.rmtree(run_dir)  # only the copy we just made
        raise RuntimeError("Stopped: private files ended up in the copy: " + ", ".join(bad))

    archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=run_dir, base_dir=APP_FOLDER_NAME))
    return target, archive


def main() -> int:
    try:
        folder, archive = prepare()
    except Exception as exc:
        print(f"\n  PROBLEM: {exc}")
        return 1
    print("\n  Clean copy ready (no API key, PDFs, spreadsheets or logs):")
    print(f"    Folder: {folder}")
    print(f"    Zip:    {archive}")
    print("\n  Copy either one to the other computer, then run Setup.bat there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
