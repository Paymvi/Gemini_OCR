"""OCR pipeline shared by the command line (main.py) and the desktop app (gui.py).

Settings, the extraction cache, source links and the per-file batch loop live here,
so both front ends extract, cache and link records the same way.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types

from extractor import extract_pdf
from models import PDFExtraction

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
EXTRACTED_DIR = ROOT / "extracted"
OUTPUT_DIR = ROOT / "output"
PROMPT_PATH = ROOT / "prompt.md"
SOURCE_LINKS_PATH = ROOT / "source_links.json"
ENV_PATH = ROOT / ".env"

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_THINKING_LEVEL = "low"
PLACEHOLDER_KEY = "PASTE_YOUR_KEY_HERE"


# ---------------------------------------------------------------- settings

def get_api_key() -> str:
    """The configured key, or "" when it is missing or still the .env.example placeholder."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if key == PLACEHOLDER_KEY else key


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def get_thinking_level() -> str:
    return os.getenv("GEMINI_THINKING_LEVEL", DEFAULT_THINKING_LEVEL)


# Without a limit a stalled connection waits forever and "Stop after this file" never takes effect.
# 10 minutes leaves room for large scans. A time-out is reported as "No connection to Gemini".
REQUEST_TIMEOUT_MS = 10 * 60 * 1000


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


def load_prompt(prompt_path: Path = PROMPT_PATH) -> tuple[str, str]:
    if not prompt_path.exists():
        raise FileNotFoundError("prompt.md does not exist.")
    prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
    return prompt_text, prompt_hash


def load_source_links(path: Path = SOURCE_LINKS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- cache

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_extraction(
    cache_path: Path,
    model: str,
    prompt_hash: str,
    pdf_sha256: str | None = None,
):
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("model") != model:
            return None
        if payload.get("prompt_hash") != prompt_hash:
            return None
        # Older cache files have no hash; they keep working as before.
        cached_sha = payload.get("pdf_sha256")
        if pdf_sha256 and cached_sha and cached_sha != pdf_sha256:
            return None
        return PDFExtraction.model_validate(payload["extraction"])
    except Exception:
        return None


def save_cache(
    cache_path: Path,
    pdf_name: str,
    model: str,
    prompt_hash: str,
    extraction: PDFExtraction,
    pdf_sha256: str | None = None,
    usage: dict[str, int] | None = None,
) -> None:
    payload = {
        "source_pdf": pdf_name,
        "model": model,
        "prompt_hash": prompt_hash,
        "extraction": extraction.model_dump(),
    }
    if pdf_sha256:
        payload["pdf_sha256"] = pdf_sha256
    if usage:
        payload["usage"] = usage
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def extract_or_load(
    client: genai.Client,
    pdf_path: Path,
    prompt_text: str,
    prompt_hash: str,
    model: str,
    thinking_level: str,
    cache_dir: Path = EXTRACTED_DIR,
    on_extract: Callable[[Path], None] | None = None,
) -> tuple[PDFExtraction, bool]:
    """Return (extraction, came_from_cache). Calls Gemini only on a cache miss."""
    sha = file_sha256(pdf_path)
    # The hash in the name keeps same-named PDFs from different folders from overwriting each other.
    cache_path = cache_dir / f"{pdf_path.stem}-{sha[:12]}.json"
    for candidate in (cache_path, cache_dir / f"{pdf_path.stem}.json"):  # second: older cache name
        extraction = cached_extraction(candidate, model, prompt_hash, sha)
        if extraction is not None:
            return extraction, True

    if on_extract:
        on_extract(pdf_path)
    extraction, usage = extract_pdf(
        client=client,
        pdf_path=pdf_path,
        prompt_text=prompt_text,
        model=model,
        thinking_level=thinking_level,
    )
    save_cache(cache_path, pdf_path.name, model, prompt_hash, extraction, sha, usage)
    return extraction, False


def records_for(
    pdf_path: Path,
    extraction: PDFExtraction,
    source_links: dict[str, str],
) -> list[dict[str, Any]]:
    """Wrap each waiver record with where it came from, as spreadsheet.py expects."""
    mapped_link = source_links.get(pdf_path.name)
    metas = []
    for record in extraction.records:
        if mapped_link:
            source_link = mapped_link
        else:
            source_link = pdf_path.resolve().as_uri() + f"#page={record.individual_page}"
        metas.append(
            {
                "source_file": pdf_path.name,
                "source_path": str(pdf_path.resolve()),
                "source_link": source_link,
                "record": record,
            }
        )
    return metas


# ---------------------------------------------------------------- batch run (desktop app)

@dataclass
class FileResult:
    path: Path
    status: str = "waiting"  # waiting | done | failed | skipped
    waivers: int = 0
    from_cache: bool = False
    message: str = ""


@dataclass
class BatchResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    files: list[FileResult] = field(default_factory=list)
    stopped_reason: str = ""


def run_batch(
    pdf_paths: list[Path],
    api_key: str,
    on_event: Callable[..., None] = lambda *args: None,
    stop_event: threading.Event | None = None,
    cache_dir: Path = EXTRACTED_DIR,
    client: genai.Client | None = None,
    source_links: dict[str, str] | None = None,
    on_extract: Callable[[Path], None] | None = None,
) -> BatchResult:
    """Process each PDF in turn. One failed file does not stop the others.

    Errors that would make every remaining file fail too (bad key, quota, no network)
    stop the run, so the app does not keep sending requests that cannot succeed.

    Events: ("start", i), ("done", i, FileResult), ("failed", i, FileResult, FriendlyError),
    ("skipped", i, FileResult).
    """
    from friendly_errors import describe_error

    prompt_text, prompt_hash = load_prompt()
    source_links = load_source_links() if source_links is None else source_links
    client = client or make_client(api_key)
    model, thinking = get_model(), get_thinking_level()

    result = BatchResult(files=[FileResult(Path(p)) for p in pdf_paths])

    for index, item in enumerate(result.files):
        if result.stopped_reason or (stop_event and stop_event.is_set()):
            item.status = "skipped"
            item.message = result.stopped_reason or "Stopped before this file."
            on_event("skipped", index, item)
            continue

        on_event("start", index)
        try:
            extraction, item.from_cache = extract_or_load(
                client, item.path, prompt_text, prompt_hash, model, thinking, cache_dir, on_extract
            )
            metas = records_for(item.path, extraction, source_links)
        except Exception as exc:
            friendly = describe_error(exc, item.path)
            item.status = "failed"
            item.message = friendly.message
            if friendly.stops_run:
                result.stopped_reason = f"Not processed: {friendly.title}"
            on_event("failed", index, item, friendly)
            continue

        result.records.extend(metas)
        item.status = "done"
        item.waivers = len(metas)
        on_event("done", index, item)

    return result
