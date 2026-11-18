"""Command-line entry point: process every PDF in input/ into output/master_contacts.xlsx.

The desktop app (gui.py) uses the same pipeline; this workflow is unchanged.
"""
import os

from dotenv import load_dotenv

from pipeline import (  # noqa: F401  (names kept importable from main for compatibility)
    DEFAULT_MODEL,
    DEFAULT_THINKING_LEVEL,
    ENV_PATH,
    EXTRACTED_DIR,
    INPUT_DIR,
    OUTPUT_DIR,
    PROMPT_PATH,
    ROOT,
    SOURCE_LINKS_PATH,
    cached_extraction,
    extract_or_load,
    get_api_key,
    load_prompt,
    load_source_links,
    make_client,
    records_for,
    save_cache,
)
from spreadsheet import MASTER_FILENAME, write_workbook

load_dotenv(ENV_PATH)

MODEL = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", DEFAULT_THINKING_LEVEL)


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Put it in your .env file before running this program."
        )

    INPUT_DIR.mkdir(exist_ok=True)
    EXTRACTED_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    prompt_text, prompt_hash = load_prompt(PROMPT_PATH)
    source_links = load_source_links(SOURCE_LINKS_PATH)

    pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {INPUT_DIR}")
        return

    client = make_client(api_key)
    all_records = []

    for pdf_path in pdf_paths:
        extraction, from_cache = extract_or_load(
            client=client,
            pdf_path=pdf_path,
            prompt_text=prompt_text,
            prompt_hash=prompt_hash,
            model=MODEL,
            thinking_level=THINKING_LEVEL,
            cache_dir=EXTRACTED_DIR,
            on_extract=lambda path: print(f"Extracting: {path.name}"),
        )
        if from_cache:
            print(f"Using cached JSON: {pdf_path.name}")

        all_records.extend(records_for(pdf_path, extraction, source_links))

    output_path = OUTPUT_DIR / MASTER_FILENAME
    write_workbook(all_records, output_path)

    print()
    print(f"Processed PDFs: {len(pdf_paths)}")
    print(f"Extracted waiver records: {len(all_records)}")
    print(f"Spreadsheet: {output_path}")


if __name__ == "__main__":
    main()
