"""First-time setup and launch check for the Windows desktop app.

Standard library only, because it runs before anything is installed.

    python tools/setup_env.py           build or repair .venv and install requirements (Setup.bat)
    python tools/setup_env.py --check   exit 0 only if .venv is ready on this computer (Open OCR App.bat)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import traceback
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 9)
REQUIRED_IMPORTS = ["google.genai", "pydantic", "dotenv", "openpyxl", "dateutil", "tkinter", "tkinterdnd2"]
MARKER_NAME = "tnocr_setup.json"
PLACEHOLDER_KEY = "PASTE_YOUR_KEY_HERE"
# Installed packages need up to ~137 characters below the app folder (measured with
# google-genai 2.20), and Windows' default limit is 260, so leave a margin.
MAX_FOLDER_PATH = 100


def long_paths_enabled() -> bool:
    if os.name != "nt":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


def path_too_long(root: Path) -> bool:
    return len(str(root)) > MAX_FOLDER_PATH and not long_paths_enabled()


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def this_machine(venv_dir: Path) -> dict:
    return {"computer": platform.node(), "venv": os.path.normcase(os.path.abspath(str(venv_dir)))}


def read_marker(venv_dir: Path) -> dict | None:
    try:
        return json.loads((venv_dir / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def venv_problem(venv_dir: Path) -> str:
    """Why .venv must be rebuilt, or "" if it can be reused on this computer."""
    py = venv_python(venv_dir)
    if not venv_dir.exists():
        return "no environment yet"
    if not py.exists():
        return "the environment is incomplete"

    marker = read_marker(venv_dir)
    expected = this_machine(venv_dir)
    if marker is not None and (marker.get("computer") != expected["computer"]
                               or marker.get("venv") != expected["venv"]):
        return "the environment was copied from another computer or folder"

    try:
        probe = subprocess.run([str(py), "-c", "import sys; print(sys.prefix)"],
                               capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "the environment does not run on this computer"
    if probe.returncode != 0 or not same_path(probe.stdout.strip(), venv_dir):
        return "the environment does not run on this computer"
    return ""


def remove_tree(path: Path) -> None:
    def make_writable(func, failed_path, _exc):
        os.chmod(failed_path, stat.S_IWRITE)
        func(failed_path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable)
    else:
        shutil.rmtree(path, onerror=make_writable)


def key_configured(env_path: Path) -> bool:
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        name, _, value = line.partition("=")
        if name.strip() == "GEMINI_API_KEY":
            value = value.strip().strip("'\"")
            return bool(value) and value != PLACEHOLDER_KEY
    return False


def say(text: str = "") -> None:
    print(text, flush=True)


def fail(text: str) -> int:
    say()
    say("  PROBLEM: " + text)
    return 1


def setup(root: Path = ROOT) -> int:
    venv_dir = root / ".venv"
    py = venv_python(venv_dir)
    say(f"  Using Python {platform.python_version()}")

    if sys.version_info < MIN_PYTHON:
        return fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is needed. "
                    "Install it from https://www.python.org/downloads/windows/ and run Setup again.")
    try:
        import tkinter
        tkinter.Tcl()
    except Exception:
        return fail("This Python was installed without its window toolkit (Tcl/Tk).\n"
                    "  Run the Python installer again, choose Modify, tick 'tcl/tk and IDLE', "
                    "then run Setup again.")

    if path_too_long(root):
        return fail(f"This folder's location is too long for Windows ({len(str(root))} characters):\n"
                    f"  {root}\n"
                    "  Move the whole app folder somewhere shorter, for example C:\\Waiver Contacts or\n"
                    "  your Documents folder, then run Setup again from there.")

    say()
    say("  Step 1 of 3: preparing the app's private Python environment (.venv)")
    problem = venv_problem(venv_dir)
    if problem:
        say(f"  Creating a fresh environment ({problem}).")
        if venv_dir.exists():
            try:
                remove_tree(venv_dir)
            except OSError as exc:
                return fail("The old environment could not be removed. Close the OCR app (and any "
                            f"window using this folder), then run Setup again.\n  ({exc})")
        try:
            venv.EnvBuilder(with_pip=True).create(venv_dir)
        except Exception as exc:
            return fail(f"Could not create the environment: {exc}")
    else:
        say("  Existing environment works on this computer; reusing it.")

    say()
    say("  Step 2 of 3: installing the app's components (needs internet; can take a few minutes)")
    install = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check",
                              "-r", str(root / "requirements.txt")], cwd=str(root))
    if install.returncode != 0:
        return fail("Installing components failed. Check the internet connection and run Setup again.\n"
                    "  If the messages above say a filename is too long, move the app folder somewhere\n"
                    "  shorter (for example C:\\Waiver Contacts) and run Setup there.")

    say()
    say("  Step 3 of 3: checking the installation")
    check = subprocess.run([str(py), str(Path(__file__).resolve()), "--check-imports"], cwd=str(root))
    if check.returncode != 0:
        return fail("Some components did not install correctly. Run Setup again.")

    (venv_dir / MARKER_NAME).write_text(json.dumps(this_machine(venv_dir), indent=2), encoding="utf-8")
    for folder in ("input", "output"):
        (root / folder).mkdir(exist_ok=True)

    say()
    say("  ============================================================")
    say("   Setup finished successfully.")
    say("  ============================================================")
    if key_configured(root / ".env"):
        say("   API key: already configured on this computer.")
    else:
        say("   API key: not configured yet. The app will ask for it the first")
        say("   time it opens (Settings). See QUICKSTART-WINDOWS.md.")
    say()
    say('   Next: double-click "Open OCR App.bat".')
    return 0


def check_imports() -> int:
    missing = []
    for name in REQUIRED_IMPORTS:
        try:
            __import__(name)
        except Exception as exc:
            missing.append(f"{name} ({type(exc).__name__})")
    if missing:
        say("  Missing or broken: " + ", ".join(missing))
        return 1
    return 0


def check_ready(root: Path = ROOT) -> int:
    """Run with the .venv Python by the launcher."""
    venv_dir = root / ".venv"
    marker = read_marker(venv_dir)
    if not same_path(sys.prefix, venv_dir):
        say("  The app's environment is not active.")
        return 1
    if marker is None:
        say("  Setup has not finished on this computer.")
        return 1
    if marker != this_machine(venv_dir):
        say("  The environment was copied from another computer or folder.")
        return 1
    if check_imports():
        return 1
    # Import the app itself, so a startup crash shows here instead of vanishing under pythonw.
    sys.path.insert(0, str(root))
    try:
        __import__("gui")
    except Exception as exc:
        error_file = root / "logs" / "startup-error.log"
        error_file.parent.mkdir(exist_ok=True)
        error_file.write_text(traceback.format_exc(), encoding="utf-8")
        say(f"  The app could not start: {type(exc).__name__}: {exc}")
        say(f"  Details were saved in {error_file}")
        return 1
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check_ready())
    if "--check-imports" in sys.argv:
        sys.exit(check_imports())
    sys.exit(setup())
