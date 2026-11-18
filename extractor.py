from pathlib import Path
import time

from google import genai
from google.genai import errors as genai_errors

from models import PDFExtraction

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_ATTEMPTS = 3

# Errors that will fail the same way every time (bad key, bad request, unknown model).
# Retrying them only wastes time, so they are raised on the first attempt.
PERMANENT_ERROR_CODES = {400, 401, 403, 404}


class PDFFileError(ValueError):
    """The file itself cannot be sent: missing, empty, too large, or not a PDF."""


def check_pdf_file(pdf_path: Path) -> None:
    """Cheap local checks so a bad file fails before anything is uploaded."""
    size = pdf_path.stat().st_size
    if size > MAX_PDF_BYTES:
        raise PDFFileError(
            f"{pdf_path.name} is larger than Gemini's 50 MB PDF limit. "
            "Split or compress this PDF before processing it."
        )
    if size == 0:
        raise PDFFileError(f"{pdf_path.name} is empty (0 bytes).")
    with pdf_path.open("rb") as handle:
        head = handle.read(1024)
    if b"%PDF-" not in head:
        raise PDFFileError(f"{pdf_path.name} is not a PDF file, or it is damaged.")


def _is_permanent(exc: Exception) -> bool:
    return isinstance(exc, genai_errors.ClientError) and exc.code in PERMANENT_ERROR_CODES


def extract_pdf(
    client: genai.Client,
    pdf_path: Path,
    prompt_text: str,
    model: str,
    thinking_level: str,
) -> PDFExtraction:
    check_pdf_file(pdf_path)

    uploaded = client.files.upload(file=str(pdf_path))

    try:
        full_prompt = (
            prompt_text.rstrip()
            + "\n\nSource PDF filename: "
            + pdf_path.name
            + "\nUse the PDF's 1-based page numbers for individual_page/supporting_pages."
        )

        last_error = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                interaction = client.interactions.create(
                    model=model,
                    input=[
                        {
                            "type": "document",
                            "uri": uploaded.uri,
                            "mime_type": uploaded.mime_type,
                        },
                        {"type": "text", "text": full_prompt},
                    ],
                    generation_config={"thinking_level": thinking_level},
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": PDFExtraction.model_json_schema(),
                    },
                )

                return PDFExtraction.model_validate_json(interaction.output_text)

            except Exception as exc:
                last_error = exc
                if attempt == MAX_ATTEMPTS - 1 or _is_permanent(exc):
                    raise
                time.sleep(2 ** (attempt + 1))

        raise last_error  # pragma: no cover

    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
