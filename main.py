import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from extractor import extract_pdf
from models import PDFExtraction
from spreadsheet import write_workbook

load_dotenv()

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
EXTRACTED_DIR = ROOT / "extracted"
OUTPUT_DIR = ROOT / "output"
PROMPT_PATH = ROOT / "prompt.md"
SOURCE_LINKS_PATH = ROOT / "source_links.json"

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low")


def load_source_links() -> dict[str, str]:
    if not SOURCE_LINKS_PATH.exists():
        return {}
    return json.loads(SOURCE_LINKS_PATH.read_text(encoding="utf-8"))


def cached_extraction(cache_path: Path, model: str, prompt_hash: str):
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("model") != model:
            return None
        if payload.get("prompt_hash") != prompt_hash:
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
) -> None:
    payload = {
        "source_pdf": pdf_name,
        "model": model,
        "prompt_hash": prompt_hash,
        "extraction": extraction.model_dump(),
    }
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Put it in your .env file before running this program."
        )

    INPUT_DIR.mkdir(exist_ok=True)
    EXTRACTED_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not PROMPT_PATH.exists():
        raise FileNotFoundError("prompt.md does not exist.")

    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
    source_links = load_source_links()

    pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {INPUT_DIR}")
        return

    client = genai.Client()
    all_records = []

    for pdf_path in pdf_paths:
        cache_path = EXTRACTED_DIR / f"{pdf_path.stem}.json"
        extraction = cached_extraction(cache_path, MODEL, prompt_hash)

        if extraction is None:
            print(f"Extracting: {pdf_path.name}")
            extraction = extract_pdf(
                client=client,
                pdf_path=pdf_path,
                prompt_text=prompt_text,
                model=MODEL,
                thinking_level=THINKING_LEVEL,
            )
            save_cache(
                cache_path=cache_path,
                pdf_name=pdf_path.name,
                model=MODEL,
                prompt_hash=prompt_hash,
                extraction=extraction,
            )
        else:
            print(f"Using cached JSON: {pdf_path.name}")

        mapped_link = source_links.get(pdf_path.name)

        for record in extraction.records:
            if mapped_link:
                source_link = mapped_link
            else:
                source_link = (
                    pdf_path.resolve().as_uri()
                    + f"#page={record.individual_page}"
                )

            all_records.append(
                {
                    "source_file": pdf_path.name,
                    "source_link": source_link,
                    "record": record,
                }
            )

    output_path = OUTPUT_DIR / "master_contacts.xlsx"
    write_workbook(all_records, output_path)

    print()
    print(f"Processed PDFs: {len(pdf_paths)}")
    print(f"Extracted waiver records: {len(all_records)}")
    print(f"Spreadsheet: {output_path}")


if __name__ == "__main__":
    main()
