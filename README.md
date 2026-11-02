# TNOCR Gemini Starter

A command-line Python tool that reads scanned visitor waiver PDFs from the Toah Nipi Christian Retreat Center and turns them into one Excel contact list.

The scans are mostly handwritten forms. The tool reads them with OCR, meaning it turns the text in a scanned image into editable text. Here that work is done by Google's Gemini AI model through the Gemini API, not by a local OCR engine. Gemini returns structured fields for each guest. The tool merges repeat visitors cautiously and writes `output/master_contacts.xlsx`. Any field a person should double-check is flagged and highlighted.

**Example:** put a batch scan such as `Fall retreat 2025.pdf` in `input/` and run `python main.py`. You get a spreadsheet with one row per guest: name, address, email, phone, organization, guest group, visit date and notes. Each row links back to the source PDF page. If the same guest appears in an older batch, that visit is listed under their prior visit dates instead of becoming a second row.

> [!IMPORTANT]
> Each PDF is uploaded to Google's Gemini API for processing. The waivers contain personal data, so read [Privacy and data](#privacy-and-data) before you use this tool.

## Features

- **Batch PDF processing:** handles every `*.pdf` file in the `input/` folder in one run. Other input types (images, screenshots, clipboard) are not supported.
- **Handwriting-aware extraction:** gets Organization, First Name, Last Name, Address, City, State, Zip, Email, Phone Number, Visit Date, Guest Group and Notes for each guest waiver.
- **One-page and cover-page forms:** carries organization and group details from a cover page over to the individual waivers that follow it. Blank pages and cover-only pages do not create records.
- **Multilingual names:** the prompt tells Gemini to keep names exactly as written, including diacritics, CJK characters and Hangul. It also tells Gemini not to force Western name order.
- **Review flags instead of scores:** every field gets a `*_Confident` column (`TRUE`/`FALSE`). Uncertain values are highlighted in yellow, and their `FALSE` flag cells in red.
- **Notes column:** gathers other handwritten details into one compact Notes field, such as spouse, emergency contact, minors, health conditions and food restrictions.
- **Cautious repeat-visitor merging:** links visits to one contact only when exact identifiers match (see [How records are merged](#how-records-are-merged)).
- **Source links:** each row links to the source PDF page, or to a permanent URL you provide.
- **Local result cache:** keeps each PDF's extraction as JSON, so re-runs skip PDFs that were already processed and do not call the API for them again.

## Quick start

There is no packaged release or installer. You run the tool from source with Python. The commands below are for Windows PowerShell, which is where the project was set up. The code itself does not depend on Windows, but other systems have not been tested.

**Prerequisites**

- Python 3. The project has been run with Python 3.12, and the code needs 3.9 or newer.
- A Gemini API key from Google AI Studio.
- Internet access.

**1. Create a virtual environment and install dependencies**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**2. Configure your API key**

Copy the example settings file. Then open `.env` and replace `PASTE_YOUR_KEY_HERE` with your Gemini API key.

```powershell
Copy-Item .env.example .env
```

Never commit `.env`. It is already listed in [.gitignore](.gitignore).

**3. Check that the key works (optional)**

```powershell
python test_gemini.py
```

A working key prints a few numbered progress lines followed by `API WORKS`. This script always uses the `gemini-3.5-flash-lite` model, so it checks your key and connection, not the model set in `GEMINI_MODEL`.

**4. Process PDFs**

```powershell
python main.py
```

## Using the tool

1. Put the scanned waiver PDFs in `input/`. The first run of `main.py` creates this folder if it does not exist.
2. Optional: if each PDF has a permanent web or Google Drive URL, create `source_links.json` by copying [source_links.example.json](source_links.example.json). It maps each PDF file name to its URL:

   ```json
   {
     "example_batch.pdf": "https://example.com/path/to/example_batch.pdf"
   }
   ```

3. Run `python main.py`. Each PDF prints either `Extracting: <file>` or `Using cached JSON: <file>`. When the run finishes, it prints how many PDFs it processed, how many records it extracted, and where it saved the spreadsheet.
4. Open `output/master_contacts.xlsx` and check the highlighted cells.

### Settings

You set these in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | *(required)* | Your Gemini API key. `main.py` stops with an error if it is missing. |
| `GEMINI_MODEL` | `gemini-3.7-flash` | The Gemini model used to extract data. |
| `GEMINI_THINKING_LEVEL` | `low` | The thinking level setting sent to Gemini with each request. |

Extraction rules live in [prompt.md](prompt.md): which fields to extract, how to handle cover pages, the Notes format and when to flag a field. The response structure is defined in [models.py](models.py). You can edit the prompt to change how Gemini reads the forms.

### Spreadsheet output

`output/master_contacts.xlsx` has one sheet, **Master Contacts**. Rows are sorted by last name, then first name. The columns are:

- One value column and one `*_Confident` column for each extracted field, plus **All Prior Visit Dates** and **Visit Count**.
- **Source_PDF_Link:** a link to the most recent visit's PDF.
- **Prior_Visit_1_Link** through **Prior_Visit_11_Link:** links to older visits.

A `*_Confident` value of `FALSE` means Gemini flagged the field for review, or the merge could not be fully confirmed.

Each link is one of two things:

- The URL from `source_links.json`, if the PDF is listed there. This link points to the whole file, not a specific page.
- Otherwise, a local `file:///…/input/<file>.pdf#page=N` link.

Local links use absolute paths, so they break if the project folder moves or the workbook is opened on another computer.

Each run rebuilds the workbook from all PDFs currently in `input/` and overwrites the previous file.

### How records are merged

Two waivers become one contact only if both are true:

- They have the same normalized first and last name. Normalizing ignores case, spaces and punctuation.
- They share at least one exact secondary identifier: email, phone number (at least 7 digits), street address, or city + state + ZIP together.

Matches can chain. If A matches B and B matches C, all three are merged.

Within a merged contact:

- The record with the latest visit date that can be read as a date becomes the main row. It supplies **Visit Date** and **Source_PDF_Link**.
- Older records supply **All Prior Visit Dates** and the prior visit links.
- Contact fields (name, address, city, state, ZIP, email, phone) use the most recent value that is not blank. Organization, Guest Group, Notes and Visit Date always come from the main record.

## Privacy and data

**Where recognition happens:** the tool does no OCR on your computer. For each PDF that is not already cached, it:

1. Uploads the file to the Gemini Files API.
2. Sends it to the configured Gemini model together with the contents of `prompt.md`.
3. Deletes the uploaded file after extraction succeeds or fails. The deletion is best effort: if it fails, the error is ignored. To learn how Google stores and uses API data, read Google's terms for your Gemini API plan.

**Network activity:**

- Installing dependencies downloads packages from PyPI.
- Normal runs talk only to the Gemini API, and only for PDFs that need extraction. PDFs with a valid cache entry are not uploaded again.
- The code contains no telemetry or other external services. It downloads no OCR models or language data.

**Files kept on your computer:**

| Location | Contents | Retention |
| --- | --- | --- |
| `input/` | Your source PDFs | Never changed or deleted by the tool |
| `extracted/<pdf name>.json` | Extracted personal data for each PDF, plus the model name and a prompt hash | Kept until you delete it |
| `output/master_contacts.xlsx` | The merged contact list | Overwritten on each run |
| `source_links.json` | Optional URL mapping | Created and maintained by you |
| `.env` | Your API key and settings | Created and maintained by you |

[.gitignore](.gitignore) excludes `input/`, `extracted/`, `output/`, `source_links.json` and `.env`. They contain private visitor data or secrets, so do not commit them.

## Development

**Stack:**

- Python 3.
- [`google-genai`](https://pypi.org/project/google-genai/) for the Gemini Interactions and Files APIs.
- Pydantic v2 for the response schema.
- `python-dotenv` for settings.
- `openpyxl` to write the workbook.
- `python-dateutil` to parse dates.

The dependencies in [requirements.txt](requirements.txt) have no exact versions. The code uses `client.interactions`, which is present in `google-genai` 2.20.0.

| File | Role |
| --- | --- |
| [main.py](main.py) | Entry point: loads settings, finds PDFs, manages the cache, builds source links and writes the workbook |
| [extractor.py](extractor.py) | Uploads one PDF, asks Gemini for schema-constrained JSON (up to 3 attempts with backoff), and deletes the upload |
| [models.py](models.py) | Pydantic models (`ExtractedField`, `WaiverRecord`, `PDFExtraction`) used as the Gemini response schema |
| [spreadsheet.py](spreadsheet.py) | Merges records, chooses fields and writes the formatted Excel file |
| [prompt.md](prompt.md) | Extraction instructions sent to Gemini |
| [test_gemini.py](test_gemini.py), [test_gemini_simple.py](test_gemini_simple.py) | Manual scripts that test the API connection (not automated tests) |

**Cache behavior:** a cache entry in `extracted/` is reused only when three things are true:

- Its model matches `GEMINI_MODEL`.
- Its prompt hash matches the current `prompt.md`.
- It still validates against the models in `models.py`.

If any of these fail, the PDF is extracted again. Changing `GEMINI_THINKING_LEVEL`, or replacing a PDF with a different file of the same name, does **not** clear the cache. In those cases, delete the matching JSON file.

**Tests:** the project has no automated test suite. Both `test_gemini*.py` scripts make live API calls as soon as Python imports them. Do not run them with pytest. Run them directly with `python`, as shown in [Quick start](#quick-start).

There is no build step. Run `python main.py` from the project folder.

## Limitations and troubleshooting

- **The API key is missing:** `main.py` stops with `GEMINI_API_KEY is missing. Put it in your .env file before running this program.` Create `.env` from `.env.example`.
- **"No PDFs found in …":** PDFs must be directly inside `input/`. Subfolders are not searched.
- **PDFs over 50 MB** are rejected before upload. Split or compress them first.
- **An API error stops the run:** if a PDF still fails after 3 attempts, the whole run stops and no workbook is written. PDFs that finished before the failure keep their cache entries, so the next run picks up where this one stopped.
- **The connection test script does not report failure through its exit code:** `test_gemini.py` prints `GEMINI REQUEST FAILED:` and the error, but it still exits normally.
- **Visit dates without a year** (for example `Nov 24`) are kept exactly as written, but they cannot be sorted. A merged contact uses its latest visit with a readable date as the main row.
- **Merging is deliberately strict:**
  - A guest with no email, phone, address or full city/state/ZIP on any waiver is never merged.
  - Name normalization keeps only the characters a–z and 0–9. As a result, accented letters are dropped: `José` and `Jose` do not match.
  - Names written only in non-Latin scripts (CJK, Hangul, and others) are never merged, even if every other detail matches.
- **More than 11 prior visits:** only 11 prior-visit link columns exist. Extra prior visits still count toward **Visit Count** and **All Prior Visit Dates**, but get no link.
- **Extraction quality depends on the model and the scan:** handwriting is hard to read, and the results come from an AI model. Check every highlighted cell. Also spot-check unflagged values against the linked PDF page before you rely on them.

## License

This repository has no license file. Until the owner adds one, no license is granted to use, copy or redistribute the code.
