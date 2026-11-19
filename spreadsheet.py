from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


HEADERS = [
    "Organization",
    "Organization_Confident",
    "First Name",
    "First_Name_Confident",
    "Last Name",
    "Last_Name_Confident",
    "Address",
    "Address_Confident",
    "City",
    "City_Confident",
    "State",
    "State_Confident",
    "Zip",
    "Zip_Confident",
    "Email",
    "Email_Confident",
    "Phone Number",
    "Phone_Number_Confident",
    "Visit Date",
    "Visit_Date_Confident",
    "Guest Group",
    "Guest_Group_Confident",
    "All Prior Visit Dates",
    "All_Prior_Visit_Dates_Confident",
    "Notes",
    "Notes_Confident",
    "Visit Count",
    "Visit_Count_Confident",
    "Source_PDF_Link",
    *[f"Prior_Visit_{i}_Link" for i in range(1, 12)],
]

FIELD_COLUMNS = [
    ("Organization", "Organization_Confident", "organization"),
    ("First Name", "First_Name_Confident", "first_name"),
    ("Last Name", "Last_Name_Confident", "last_name"),
    ("Address", "Address_Confident", "address"),
    ("City", "City_Confident", "city"),
    ("State", "State_Confident", "state"),
    ("Zip", "Zip_Confident", "zip"),
    ("Email", "Email_Confident", "email"),
    ("Phone Number", "Phone_Number_Confident", "phone_number"),
    ("Visit Date", "Visit_Date_Confident", "visit_date"),
    ("Guest Group", "Guest_Group_Confident", "guest_group"),
    ("Notes", "Notes_Confident", "notes"),
]

CONTACT_BACKFILL_FIELDS = {
    "first_name",
    "last_name",
    "address",
    "city",
    "state",
    "zip",
    "email",
    "phone_number",
}


def _norm_text(value: str) -> str:
    # NFKD splits "é" into "e" + accent mark, so the regex keeps the "e": José matches Jose.
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", value.casefold()))


def _norm_email(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def _norm_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _full_name(record) -> str:
    first = _norm_text(record.first_name.value)
    last = _norm_text(record.last_name.value)
    if not first or not last:
        return ""
    return f"{first}|{last}"


def _identity_keys(meta: dict[str, Any]) -> list[str]:
    record = meta["record"]
    name = _full_name(record)
    if not name:
        return []

    keys: list[str] = []

    email = _norm_email(record.email.value)
    if email:
        keys.append(f"name_email:{name}|{email}")

    phone = _norm_phone(record.phone_number.value)
    if len(phone) >= 7:
        keys.append(f"name_phone:{name}|{phone}")

    address = _norm_text(record.address.value)
    if address:
        keys.append(f"name_address:{name}|{address}")

    city = _norm_text(record.city.value)
    state = _norm_text(record.state.value)
    zipcode = _norm_text(record.zip.value)
    if city and state and zipcode:
        keys.append(f"name_location:{name}|{city}|{state}|{zipcode}")

    return keys


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return

        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _parse_visit_date(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None

    has_four_digit_year = re.search(r"\b(?:19|20)\d{2}\b", value)
    has_two_digit_year = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2}\b", value)
    if not (has_four_digit_year or has_two_digit_year):
        return None

    try:
        return date_parser.parse(value, fuzzy=False)
    except (ValueError, OverflowError):
        return None


def _sort_key(meta: dict[str, Any]):
    record = meta["record"]
    parsed = _parse_visit_date(record.visit_date.value)
    return (
        parsed is not None,
        parsed or datetime.min,
        meta["source_file"].casefold(),
        record.individual_page,
    )


def _choose_field(sorted_members: list[dict[str, Any]], field_name: str):
    latest_record = sorted_members[0]["record"]

    if field_name not in CONTACT_BACKFILL_FIELDS:
        return getattr(latest_record, field_name)

    for meta in sorted_members:
        field = getattr(meta["record"], field_name)
        if field.value.strip():
            return field

    return getattr(latest_record, field_name)


def _make_clusters(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    uf = UnionFind(len(records))
    key_owner: dict[str, int] = {}

    for index, meta in enumerate(records):
        for key in _identity_keys(meta):
            if key in key_owner:
                uf.union(index, key_owner[key])
            else:
                key_owner[key] = index

    grouped: dict[int, list[dict[str, Any]]] = {}
    for index, meta in enumerate(records):
        root = uf.find(index)
        grouped.setdefault(root, []).append(meta)

    return list(grouped.values())


def build_master_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for cluster in _make_clusters(records):
        sorted_members = sorted(cluster, key=_sort_key, reverse=True)
        latest = sorted_members[0]
        prior = sorted_members[1:]

        row: dict[str, Any] = {}

        for value_col, confident_col, field_name in FIELD_COLUMNS:
            field = _choose_field(sorted_members, field_name)
            row[value_col] = field.value
            row[confident_col] = not field.needs_review

        identity_confident = all(bool(_identity_keys(meta)) for meta in cluster)

        latest_date = _parse_visit_date(latest["record"].visit_date.value)
        prior_dates_valid = all(
            _parse_visit_date(meta["record"].visit_date.value) is not None
            and not meta["record"].visit_date.needs_review
            for meta in prior
        )

        prior_dates = [
            meta["record"].visit_date.value
            for meta in prior
            if meta["record"].visit_date.value.strip()
        ]

        row["All Prior Visit Dates"] = "; ".join(prior_dates)
        row["All_Prior_Visit_Dates_Confident"] = (
            identity_confident
            and latest_date is not None
            and not latest["record"].visit_date.needs_review
            and prior_dates_valid
        )

        row["Visit Count"] = len(cluster)
        row["Visit_Count_Confident"] = identity_confident
        row["Source_PDF_Link"] = latest["source_link"]

        for i in range(1, 12):
            row[f"Prior_Visit_{i}_Link"] = (
                prior[i - 1]["source_link"] if i <= len(prior) else ""
            )

        # Underscore keys are for the desktop app's review table; they are not in HEADERS,
        # so the workbook never contains them.
        row["_source_file"] = latest["source_file"]
        row["_source_path"] = latest.get("source_path", "")
        row["_source_page"] = latest["record"].individual_page
        row["_other_sources"] = [
            f"{meta['source_file']} (page {meta['record'].individual_page})" for meta in prior
        ]

        rows.append(row)

    rows.sort(
        key=lambda row: (
            _norm_text(str(row.get("Last Name", ""))),
            _norm_text(str(row.get("First Name", ""))),
        )
    )
    return rows


MERGE_FLAG_COLUMNS = [
    ("All Prior Visit Dates", "All_Prior_Visit_Dates_Confident"),
    ("Visit Count", "Visit_Count_Confident"),
]
REQUIRED_FIELDS = ["First Name", "Last Name"]


def review_reasons(row: dict[str, Any]) -> list[str]:
    """Why a row needs a human look, using only the existing flags and required fields."""
    reasons = [
        f"{value_col} flagged"
        for value_col, confident_col, _ in FIELD_COLUMNS
        if not row.get(confident_col, False)
    ]
    if any(not row.get(confident_col, False) for _, confident_col in MERGE_FLAG_COLUMNS):
        reasons.append("Repeat-visit match not confirmed")
    reasons += [
        f"{name} is blank" for name in REQUIRED_FIELDS if not str(row.get(name, "")).strip()
    ]
    return reasons


def _build_workbook(
    rows: list[dict[str, Any]],
    files_summary: list[tuple[str, str, int, str]] | None = None,
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Master Contacts"
    ws.append(HEADERS)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    review_fill = PatternFill("solid", fgColor="FFF2CC")
    false_fill = PatternFill("solid", fgColor="F4CCCC")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    header_index = {name: i + 1 for i, name in enumerate(HEADERS)}

    for row_data in rows:
        ws.append([row_data.get(header, "") for header in HEADERS])
        row_number = ws.max_row
        for cell in ws[row_number]:
            if cell.data_type == "f":  # openpyxl turns text starting with "=" into a formula
                cell.data_type = "s"

        for value_col, confident_col, _ in FIELD_COLUMNS:
            confident = bool(row_data.get(confident_col, False))
            if not confident:
                ws.cell(row=row_number, column=header_index[value_col]).fill = review_fill
                ws.cell(row=row_number, column=header_index[confident_col]).fill = false_fill

        for value_col, confident_col in MERGE_FLAG_COLUMNS:
            if not bool(row_data.get(confident_col, False)):
                ws.cell(row=row_number, column=header_index[value_col]).fill = review_fill
                ws.cell(row=row_number, column=header_index[confident_col]).fill = false_fill

        for link_col in ["Source_PDF_Link", *[f"Prior_Visit_{i}_Link" for i in range(1, 12)]]:
            cell = ws.cell(row=row_number, column=header_index[link_col])
            if isinstance(cell.value, str) and cell.value:
                cell.hyperlink = cell.value
                cell.style = "Hyperlink"

    ws.freeze_panes = "A2"

    # A table has its own filter buttons; a sheet filter over the same cells makes Excel repair the file.
    if ws.max_row < 2:
        ws.auto_filter.ref = ws.dimensions
    else:
        table = Table(displayName="MasterContactsTable", ref=ws.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)

    widths = {
        "Organization": 24,
        "First Name": 18,
        "Last Name": 18,
        "Address": 30,
        "City": 20,
        "State": 10,
        "Zip": 12,
        "Email": 32,
        "Phone Number": 20,
        "Visit Date": 18,
        "Guest Group": 24,
        "All Prior Visit Dates": 35,
        "Notes": 45,
        "Visit Count": 12,
        "Source_PDF_Link": 40,
    }

    for index, header in enumerate(HEADERS, start=1):
        letter = get_column_letter(index)
        if header in widths:
            ws.column_dimensions[letter].width = widths[header]
        elif header.endswith("_Confident"):
            ws.column_dimensions[letter].width = 15
        elif header.startswith("Prior_Visit_"):
            ws.column_dimensions[letter].width = 32
        else:
            ws.column_dimensions[letter].width = 18

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    if files_summary is not None:
        # Second sheet so failed PDFs are recorded in the file, not silently dropped.
        files_ws = wb.create_sheet("Files")
        files_ws.append(["File", "Result", "Waivers found", "Message"])
        for cell in files_ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for name, result, waivers, message in files_summary:
            files_ws.append([name, result, waivers, message])
            if result != "Done":
                files_ws.cell(row=files_ws.max_row, column=2).fill = false_fill
        for letter, width in zip("ABCD", (45, 14, 15, 80)):
            files_ws.column_dimensions[letter].width = width

    return wb


# ---------------------------------------------------------------- saving without overwriting

MASTER_FILENAME = "master_contacts.xlsx"
RUN_FILE_PREFIX = "contacts"


def _workbook_bytes(rows, files_summary) -> bytes:
    buffer = io.BytesIO()
    _build_workbook(rows, files_summary).save(buffer)
    return buffer.getvalue()


def _write_new_file(directory: Path, stem: str, data: bytes) -> Path:
    """Create stem.xlsx, or stem_2.xlsx, stem_3.xlsx ... Never replaces an existing file."""
    directory.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        candidate = directory / (f"{stem}.xlsx" if n == 1 else f"{stem}_{n}.xlsx")
        try:
            handle = candidate.open("xb")  # "x" = fail if the file exists
        except FileExistsError:
            continue
        try:
            with handle:
                handle.write(data)
        except BaseException:
            candidate.unlink(missing_ok=True)
            raise
        return candidate
    raise FileExistsError(f"Too many files named {stem}*.xlsx in {directory}")


def save_rows_as_new(
    rows: list[dict[str, Any]],
    output_dir: Path,
    files_summary: list[tuple[str, str, int, str]] | None = None,
    now: datetime | None = None,
) -> Path:
    """Default export: a new timestamped spreadsheet, e.g. contacts_2026-11-18_14-30-05.xlsx."""
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    return _write_new_file(output_dir, f"{RUN_FILE_PREFIX}_{stamp}", _workbook_bytes(rows, files_summary))


def replace_master(
    rows: list[dict[str, Any]],
    master_path: Path,
    files_summary: list[tuple[str, str, int, str]] | None = None,
    now: datetime | None = None,
) -> tuple[Path, Path | None]:
    """Advanced export: replace master_contacts.xlsx, first copying the old one to backups/."""
    data = _workbook_bytes(rows, files_summary)
    master_path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if master_path.exists():
        stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        backup = _write_new_file(
            master_path.parent / "backups",
            f"{master_path.stem}_before_{stamp}",
            master_path.read_bytes(),
        )
    temp_path = master_path.with_name(f".{master_path.stem}.saving.tmp")
    temp_path.write_bytes(data)
    try:
        os.replace(temp_path, master_path)  # fails while Excel has the file open
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return master_path, backup


def count_contact_rows(path: Path) -> int | None:
    """Number of contact rows in an existing workbook, or None if it cannot be read."""
    try:
        wb = load_workbook(path, read_only=True)
        try:
            return max(wb.worksheets[0].max_row - 1, 0)
        finally:
            wb.close()
    except Exception:
        return None
