"""Command-line entry point: process every PDF in input/ into output/master_contacts.xlsx.

Uses the same batch loop as the desktop app (gui.py): a PDF that fails is reported and
skipped, and the previous master file is copied to output/backups/ before it is replaced.
"""
import sys

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
    run_batch,
    save_cache,
)
from friendly_errors import describe_save_error
from spreadsheet import MASTER_FILENAME, build_master_rows, replace_master

load_dotenv(ENV_PATH)


def main() -> int:
    """Returns 0 when every PDF was read and the spreadsheet saved, otherwise 1."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Put it in your .env file before running this program."
        )

    INPUT_DIR.mkdir(exist_ok=True)
    EXTRACTED_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {INPUT_DIR}")
        return 0

    def report(kind, index, *args):
        if kind == "done" and args[0].from_cache:
            print(f"Using cached JSON: {args[0].path.name}")
        elif kind == "failed":
            item, friendly = args
            print(f"FAILED: {item.path.name}: {friendly.title}. {friendly.message}")
        elif kind == "skipped":
            print(f"Skipped {args[0].path.name}: {args[0].message}")

    # One bad PDF is reported and skipped; the others still reach the spreadsheet.
    result = run_batch(
        pdf_paths,
        api_key,
        on_event=report,
        cache_dir=EXTRACTED_DIR,
        client=make_client(api_key),
        source_links=load_source_links(SOURCE_LINKS_PATH),
        on_extract=lambda path: print(f"Extracting: {path.name}"),
    )
    not_read = [f for f in result.files if f.status != "done"]

    print()
    print(f"Processed PDFs: {len(pdf_paths) - len(not_read)} of {len(pdf_paths)}")
    print(f"Extracted waiver records: {len(result.records)}")

    if not result.records:
        print("No waivers were read, so the spreadsheet was not changed.")
        return 1

    output_path = OUTPUT_DIR / MASTER_FILENAME
    try:
        _, backup = replace_master(build_master_rows(result.records), output_path)
    except Exception as exc:
        print(describe_save_error(exc, output_path).message)
        return 1

    print(f"Spreadsheet: {output_path}")
    if backup:
        print(f"Previous version backed up to: {backup}")
    if not_read:
        print(f"Not read: {', '.join(f.path.name for f in not_read)}. Fix or remove them and run again.")
    return 1 if not_read else 0


if __name__ == "__main__":
    sys.exit(main())
