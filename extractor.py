from pathlib import Path
import time

from google import genai

from models import PDFExtraction

MAX_PDF_BYTES = 50 * 1024 * 1024


def extract_pdf(
    client: genai.Client,
    pdf_path: Path,
    prompt_text: str,
    model: str,
    thinking_level: str,
) -> PDFExtraction:
    if pdf_path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(
            f"{pdf_path.name} is larger than Gemini's 50 MB PDF limit. "
            "Split or compress this PDF before processing it."
        )

    uploaded = client.files.upload(file=str(pdf_path))

    try:
        full_prompt = (
            prompt_text.rstrip()
            + "\n\nSource PDF filename: "
            + pdf_path.name
            + "\nUse the PDF's 1-based page numbers for individual_page/supporting_pages."
        )

        last_error = None

        for attempt in range(3):
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
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))

        raise last_error  # pragma: no cover

    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
