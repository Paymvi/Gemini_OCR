from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str = Field(
        description=(
            "Transcribed field value. Use an empty string when the field is visibly blank "
            "or cannot be reasonably transcribed."
        )
    )
    needs_review: bool = Field(
        description=(
            "True only when a human should verify this field because handwriting, field "
            "association, or interpretation is genuinely uncertain. A clearly blank field is false."
        )
    )


class WaiverRecord(BaseModel):
    individual_page: int = Field(
        description="1-based PDF page containing the individual's main handwritten information."
    )
    supporting_pages: list[int] = Field(
        description="Other 1-based PDF pages used for this record, such as a cover page."
    )
    organization: ExtractedField
    first_name: ExtractedField
    last_name: ExtractedField
    address: ExtractedField
    city: ExtractedField
    state: ExtractedField
    zip: ExtractedField
    email: ExtractedField
    phone_number: ExtractedField
    visit_date: ExtractedField
    guest_group: ExtractedField
    notes: ExtractedField


class PDFExtraction(BaseModel):
    records: list[WaiverRecord] = Field(
        description=(
            "One record per actual individual guest waiver. Do not emit records for blank/template "
            "pages or cover-only pages."
        )
    )
