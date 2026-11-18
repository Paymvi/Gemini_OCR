"""Turn exceptions into plain-language messages for the desktop app.

Technical details are kept separately (for the Details panel and log) with API keys
removed and without waiver contents.
"""
from __future__ import annotations

import importlib
import os
import re
import socket
import traceback
from dataclasses import dataclass
from pathlib import Path

from google.genai import errors as genai_errors
from pydantic import ValidationError

from extractor import PDFFileError

_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


@dataclass
class FriendlyError:
    kind: str  # api_key | quota | network | model | pdf | response | service | save | unknown
    title: str
    message: str
    detail: str
    stops_run: bool = False  # True when every remaining file would fail the same way


def scrub(text: str) -> str:
    """Remove anything that looks like a Google API key, including the configured one."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if len(key) >= 8:
        text = text.replace(key, "[API key hidden]")
    return _KEY_PATTERN.sub("[API key hidden]", text)


def technical_detail(exc: BaseException) -> str:
    """Traceback plus a safe one-line message. Pydantic errors are listed without their input
    values, because those values are the waiver contents."""
    if isinstance(exc, ValidationError):
        problems = exc.errors(include_input=False, include_url=False)
        summary = "; ".join(
            f"{'.'.join(str(p) for p in item['loc'])}: {item['msg']}" for item in problems[:10]
        )
        message = f"ValidationError: {len(problems)} problem(s): {summary}"
    else:
        message = f"{type(exc).__name__}: {exc}"
    stack = "".join(traceback.format_tb(exc.__traceback__)) if exc.__traceback__ else ""
    return scrub((stack + message).strip())


def _looks_encrypted(pdf_path: Path | None) -> bool:
    try:
        return pdf_path is not None and b"/Encrypt" in pdf_path.read_bytes()
    except OSError:
        return False


def _network_error_types() -> tuple[type, ...]:
    """Connection-error classes of whichever HTTP library google-genai uses (httpx or httpx2)."""
    found: list[type] = [ConnectionError, socket.gaierror, TimeoutError]
    for module_name in ("httpx", "httpx2"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        cls = getattr(module, "TransportError", None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            found.append(cls)
    return tuple(found)


_NETWORK_TYPES = _network_error_types()


def _is_network_error(exc: BaseException) -> bool:
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, _NETWORK_TYPES):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def describe_error(exc: BaseException, pdf_path: Path | None = None) -> FriendlyError:
    detail = technical_detail(exc)
    name = pdf_path.name if pdf_path else "this file"

    def make(kind, title, message, stops_run=False):
        return FriendlyError(kind, title, message, detail, stops_run)

    if isinstance(exc, PDFFileError):
        return make("pdf", "File can't be used", str(exc))

    if isinstance(exc, FileNotFoundError) and pdf_path is not None and not pdf_path.exists():
        return make("pdf", "File not found",
                    f"{name} could not be found. It may have been moved, renamed or deleted.")

    if isinstance(exc, PermissionError) and pdf_path is not None:
        return make("pdf", "File can't be opened",
                    f"{name} could not be opened. Close it in any other program and try again.")

    if isinstance(exc, genai_errors.APIError):
        code = exc.code or 0
        text = f"{exc.message or ''} {exc.status or ''} {exc.details or ''}".lower()

        if code == 429 or "resource_exhausted" in text:
            return make("quota", "Gemini limit reached",
                        "Gemini's usage limit or quota has been reached. Wait a few minutes and "
                        "process again; files that already finished are not charged twice. If it "
                        "keeps happening, the person who manages the API key should check its "
                        "quota and billing.", stops_run=True)

        if code in (401, 403) or "api key" in text or "api_key" in text:
            return make("api_key", "API key not accepted",
                        "Gemini did not accept the API key. Open Settings and check the key, or "
                        "ask the person who manages it for a new one.", stops_run=True)

        if code == 404 or ("model" in text and code == 400):
            return make("model", "Gemini model not available",
                        "The Gemini model in the settings is not available for this key. "
                        "Check GEMINI_MODEL in the .env file.", stops_run=True)

        if code == 400:
            if _looks_encrypted(pdf_path):
                return make("pdf", "PDF is protected",
                            f"{name} appears to be password-protected or encrypted, and Gemini "
                            "could not read it. Save an unprotected copy and add that instead.")
            return make("pdf", "Gemini couldn't read this PDF",
                        f"Gemini could not read {name}. The file may be damaged or in an "
                        "unusual format. Try re-scanning or re-saving it as a PDF.")

        if code >= 500:
            return make("service", "Gemini service problem",
                        f"Gemini had a temporary problem while reading {name}. Try this file "
                        "again later.")

    if _is_network_error(exc):
        return make("network", "No connection to Gemini",
                    "The app could not reach Google Gemini. Check the internet connection and "
                    "try again.", stops_run=True)

    if isinstance(exc, ValidationError):  # includes invalid JSON from the model
        return make("response", "Gemini's answer couldn't be read",
                    f"Gemini returned an answer for {name} that the app could not understand. "
                    "Try this file again later.")

    return make("unknown", "Something went wrong",
                f"An unexpected problem stopped {name} from being processed. "
                "Click Show details (top right) for technical information.")


def describe_save_error(exc: BaseException, path: Path) -> FriendlyError:
    detail = technical_detail(exc)
    if isinstance(exc, PermissionError):
        return FriendlyError("save", "Spreadsheet is open or locked",
                             f"{path.name} could not be saved. If it is open in Excel, close it "
                             "and click Save again. Your results are still here.", detail)
    return FriendlyError("save", "Spreadsheet could not be saved",
                         f"{path.name} could not be saved in {path.parent}. Check that the "
                         "drive has free space and is not read-only. Your results are still "
                         "here.", detail)
