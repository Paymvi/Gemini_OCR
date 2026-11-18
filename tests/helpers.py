"""Synthetic data and a fake Gemini client. Nothing here touches the network or real waivers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from models import PDFExtraction

# Smallest file that passes the local PDF header check. Its content is never read by Gemini here.
FAKE_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def field(value: str, needs_review: bool = False) -> dict:
    return {"value": value, "needs_review": needs_review}


def record_dict(first="Ada", last="Example", email="ada@example.com", page=1, flagged=(), **extra) -> dict:
    values = {
        "organization": "Test Church", "first_name": first, "last_name": last,
        "address": "1 Test St", "city": "Testville", "state": "MA", "zip": "01000",
        "email": email, "phone_number": "555-0100", "visit_date": "01/11/2019",
        "guest_group": "Youth", "notes": "",
    }
    values.update(extra)
    data = {name: field(value, name in flagged) for name, value in values.items()}
    data.update(individual_page=page, supporting_pages=[])
    return data


def extraction_json(*records: dict) -> str:
    return json.dumps({"records": list(records)})


def extraction(*records: dict) -> PDFExtraction:
    return PDFExtraction.model_validate_json(extraction_json(*records))


def write_pdf(path: Path, salt: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(FAKE_PDF + f"%{salt}\n".encode())
    return path


class FakeClient:
    """Stands in for genai.Client. `responses` maps a PDF file name to a JSON string,
    an exception, or a list of those (one per attempt)."""

    def __init__(self, responses: dict):
        self.responses = {k: (v if isinstance(v, list) else [v]) for k, v in responses.items()}
        self.uploads: list[str] = []
        self.creates: list[str] = []
        self.deletes = 0
        self.files = SimpleNamespace(upload=self._upload, delete=self._delete)
        self.interactions = SimpleNamespace(create=self._create)

    def _upload(self, file):
        name = Path(file).name
        self.uploads.append(name)
        return SimpleNamespace(uri=f"fake://{name}", mime_type="application/pdf", name=name)

    def _delete(self, name):
        self.deletes += 1

    def _create(self, model, input, **kwargs):
        name = re.search(r"Source PDF filename: (.+)", input[1]["text"]).group(1).strip()
        self.creates.append(name)
        queue = self.responses[name]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, BaseException):
            raise answer
        return SimpleNamespace(output_text=answer)
