"""What the "?" helper teaches, step by step. Data only: helper.py draws it.

Adding a tutorial:
1. If it points at a new control, add the widget to App.targets in gui.py and its plain name to
   TARGETS below. Ids are stable names, never screen positions or visible text.
2. Add a tutorial to TUTORIALS. A short one has "steps"; a longer one has "topics", each with
   its own steps, so a person can replay one topic without the rest.

Each step:
    target   id from TARGETS to highlight, or None for a step that only explains
    text     what to click, what it does, what happens next. "{label}" becomes the control's
             current text in quotes, so it matches the simple and classic views.
    missing  shown instead of a highlight when the control is not on screen (hidden by the
             current view, or not there yet): say how to make it appear.
    when     optional: only shown when this app flag is true ("dnd" = drag-and-drop works).

Tutorials only explain. They never click, process, save or change settings: every real
action is left to the person. Example file names and dates are made up.
"""

CLASSIC_ONLY = "It is only shown in the classic view. Click “Classic view” at the top to see it."

TARGETS = {
    "helper": "the ? helper",
    "settings": "Settings…",
    "btn_simple": "Simple view / Classic view",
    "btn_night": "Night mode / Day mode",
    "btn_details": "Show details",
    "details": "the Details box",
    "add_section": "Add PDFs",
    "btn_choose": "Choose PDFs…",
    "btn_input": "Load from input folder",
    "btn_remove": "Remove selected",
    "btn_clear": "Clear list",
    "file_list": "the list of PDFs",
    "process_section": "Process",
    "btn_process": "Process PDFs",
    "btn_stop": "Stop after this file",
    "progress": "the progress bar",
    "progress_label": "the progress message",
    "failure_label": "the “Not read” note",
    "review_section": "Review contacts",
    "summary": "the contact count",
    "only_review": "Only show contacts that need review",
    "review_list": "the contact list",
    "btn_edit": "Edit / correct…",
    "btn_check": "Mark as checked",
    "btn_source": "Open source PDF",
    "save_section": "Save spreadsheet",
    "radio_new": "New spreadsheet for this run",
    "radio_master": "Replace master list",
    "btn_save": "Save spreadsheet",
    "save_status": "the save message",
    "btn_open": "Open spreadsheet",
    "btn_folder": "Open output folder",
}


def step(target, text, missing="", when=""):
    return {"target": target, "text": text, "missing": missing, "when": when}


TUTORIALS = [
    {
        "id": "start",
        "title": "Getting started",
        "steps": [
            step(None, "Hi! I'm the ? helper. This app reads scanned waiver PDFs and turns them into an "
                       "Excel contact list. You work through four numbered sections, top to bottom."),
            step("add_section", "First, {label}: choose the waiver PDFs you want to read."),
            step("process_section", "Second, {label}: the app sends the PDFs over the internet to Google "
                                    "Gemini, which reads the handwriting. Nothing is sent until you click "
                                    "“Process PDFs” yourself."),
            step("review_section", "Third, {label}: check what was read and correct mistakes. An AI reads "
                                   "the handwriting, so the results always need a look."),
            step("save_section", "Fourth, {label}: save the contacts as an Excel file."),
            step("settings", "Before the first run, a Gemini API key must be saved under {label}. The app "
                             "manager usually does this once per computer. If the app says the key is "
                             "missing, ask them."),
        ],
    },
    {
        "id": "add",
        "title": "Adding PDFs",
        "steps": [
            step("btn_choose", "Click {label} to pick waiver PDFs from anywhere on this computer. You can "
                               "pick several at once."),
            step("file_list", "You can also drag PDF files, or a folder of PDFs, onto this list. From a "
                              "folder, only the PDFs directly inside it are added.", when="dnd"),
            step("btn_input", "{label} adds every PDF in the app's input folder. PDFs in folders inside it "
                              "are not included. If the folder is empty, the app offers to open it."),
            step("file_list", "Each PDF appears here with the status “Ready”. The same file can't be added "
                              "twice, even under a different name."),
            step("btn_remove", "{label} takes the highlighted files off the list. Click a file first to "
                               "highlight it."),
            step("btn_clear", "{label} empties the whole list. Neither button moves, changes or deletes "
                              "your PDF files."),
        ],
    },
    {
        "id": "files",
        "title": "File types and clear scans",
        "steps": [
            step("file_list", "The app reads PDF files only. Photos, Word files and other types are skipped "
                              "with the note “not a PDF”. Scan or save them as PDF first."),
            step(None, "Each PDF must be 50 MB or smaller. Bigger files are turned away before anything is "
                       "uploaded, so split or compress them first."),
            step(None, "Password-protected PDFs can't be read. Open the file and save a copy without a "
                       "password, then add that copy."),
            step(None, "One PDF can hold many waivers. A group's cover page can come first: its details are "
                       "copied onto the waivers that follow it."),
            step(None, "For the best results, scan pages flat and straight, with the whole page in view and "
                       "the handwriting sharp. Even then, handwriting can be misread, so review the results."),
        ],
    },
    {
        "id": "process",
        "title": "Processing and progress",
        "steps": [
            step("btn_process", "When your PDFs are listed, click {label}. Each file is uploaded to Google "
                                "Gemini to be read, so you need the internet. I won't click it for you."),
            step("file_list", "Each file's status changes from “Waiting” to “Reading…”, then “Done” or "
                              "“Failed”. The Waivers column shows how many waivers were found."),
            step("progress", "The bar fills up as files finish."),
            step("progress_label", "This message says which file is being read, for example “file 2 of 3”. "
                                   "A large scan can take a few minutes. At the end it says how many files "
                                   "were read and how many waivers were found."),
            step("btn_stop", "{label} lets the current file finish, then stops. Files it didn't reach show "
                             "“Not processed”. It can only be clicked while processing."),
            step("btn_process", "A file that was read before is reused at no extra cost. Processing again "
                                "replaces the contacts below, so the app asks first if you have unsaved "
                                "corrections."),
        ],
    },
    {
        "id": "review",
        "title": "Reviewing and correcting",
        "topics": [
            {
                "id": "results",
                "title": "Understanding the results",
                "steps": [
                    step("review_list", "After processing, each guest appears here as one contact. The "
                                        "contacts from all the PDFs in the list are combined into one list."),
                    step("review_list", "A guest found on several waivers becomes one contact only when the "
                                        "name matches and the email, phone, street address or city, state "
                                        "and ZIP match too. Their earlier visits are kept with them."),
                    step("summary", "This line counts the contacts and how many need review."),
                    step("review_list", "These results come from an AI reading handwriting. They can be "
                                        "wrong even when a row isn't yellow, so spot-check them against "
                                        "the PDF."),
                ],
            },
            {
                "id": "flags",
                "title": "What “Needs review” means",
                "steps": [
                    step("review_list", "Yellow rows need review (“⚠ Check” in the simple view). Gemini was "
                                        "unsure about some handwriting, or a name is blank. Yellow means "
                                        "“please look”, not “wrong”."),
                    step("only_review", "Tick {label} to work through just the flagged contacts."),
                ],
            },
            {
                "id": "check",
                "title": "Checking against the PDF",
                "steps": [
                    step("btn_source", "Click a contact, then {label} to open the PDF it came from. The app "
                                       "tells you which page to look at."),
                    step("btn_check", "When a contact matches the PDF, select it and click {label}. That "
                                      "clears all its review flags. You can select several contacts at once."),
                ],
            },
            {
                "id": "edit",
                "title": "Correcting a contact",
                "steps": [
                    step("btn_edit", "Click a contact, then {label}, or just double-click the contact. A "
                                     "correction window opens."),
                    step("btn_edit", "In that window, yellow boxes are the fields flagged for review. Change "
                                     "a value to match the PDF, then untick “Needs review” next to it."),
                    step("btn_edit", "Click “Save changes” to keep your corrections, or “Cancel” to leave "
                                     "the contact as it was. Corrections go into the spreadsheet when you "
                                     "save it."),
                ],
            },
        ],
    },
    {
        "id": "save",
        "title": "Saving the spreadsheet",
        "topics": [
            {
                "id": "how",
                "title": "Saving",
                "steps": [
                    step("radio_new", "Leave {label} selected. Every save makes a new file, for example "
                                      "contacts_2026-11-18_14-30-05.xlsx, so older spreadsheets are never "
                                      "replaced.",
                         missing="The simple view always saves a new spreadsheet, so this choice isn't "
                                 "shown there."),
                    step("btn_save", "Click {label}. The app then asks whether to open the new file."),
                    step("save_status", "After saving, this shows the new file's name. If some PDFs failed, "
                                        "you can still save the contacts from the others."),
                ],
            },
            {
                "id": "find",
                "title": "Finding your spreadsheets",
                "steps": [
                    step("btn_open", "{label} opens the file you just saved, usually in Excel."),
                    step("btn_folder", "{label} shows every saved spreadsheet. They are in the output folder "
                                       "inside the app folder."),
                    step("save_section", "In the file, the first sheet has one row per contact, with cells "
                                         "to check in yellow and a link to each source PDF. The “Files” "
                                         "sheet lists every PDF and whether it was read."),
                ],
            },
            {
                "id": "master",
                "title": "Replace master list (advanced)",
                "steps": [
                    step("radio_master", "{label} overwrites the one master file that the command-line tool "
                                         "also writes. The app asks first and keeps a backup copy in "
                                         "output\\backups. Contacts only in the old master list are not "
                                         "carried over.", missing=CLASSIC_ONLY),
                ],
            },
        ],
    },
    {
        "id": "errors",
        "title": "When something goes wrong",
        "topics": [
            {
                "id": "failed",
                "title": "A file failed",
                "steps": [
                    step("file_list", "A file that failed shows “Failed” in red with the reason. Double-click "
                                      "it to read the whole message. The other files still finish."),
                    step("failure_label", "This note lists the files that weren't read.",
                         missing="It only appears after a run in which a file wasn't read."),
                    step("btn_process", "Common fixes: re-scan the waiver, save it again as a normal PDF "
                                        "without a password, or split a file over 50 MB. Then add it and "
                                        "click {label} again. Finished files aren't charged again."),
                ],
            },
            {
                "id": "stops",
                "title": "Key, internet and limit problems",
                "steps": [
                    step("settings", "“API key not accepted”: open {label}, paste the key again and click "
                                     "“Test key”. Testing checks the key without reading any PDF."),
                    step("btn_process", "“No connection to Gemini”: check the internet connection, then "
                                        "click {label} again."),
                    step("btn_process", "“Gemini limit reached”: wait a few minutes and process again. If it "
                                        "keeps happening, ask the app manager to check the key's quota and "
                                        "billing."),
                    step(None, "When one of these happens, the app stops sending the remaining files, "
                               "because they would fail the same way."),
                ],
            },
            {
                "id": "saving",
                "title": "Saving problems",
                "steps": [
                    step("btn_save", "“Spreadsheet is open or locked”: close the spreadsheet in Excel, then "
                                     "click {label} again. Your results stay in the app meanwhile."),
                    step("btn_folder", "Saved but didn't open? Excel may not be installed. Use {label} to "
                                       "find the file."),
                ],
            },
            {
                "id": "details",
                "title": "Technical details",
                "steps": [
                    step("btn_details", "{label} opens a box of technical messages, also saved in "
                                        "logs\\app.log. Neither holds the API key or what the waivers say."),
                    step("details", "If a problem keeps happening, send these messages to the app manager.",
                         missing="Click “Show details” (“⋯” in the simple view) at the top to open it."),
                ],
            },
        ],
    },
    {
        "id": "settings",
        "title": "Settings and views",
        "steps": [
            step("settings", "{label} holds the Gemini API key. It is saved only on this computer. “Test "
                             "key” checks it without reading any PDF."),
            step("btn_simple", "{label} switches between the simple view (bigger, fewer columns) and the "
                               "classic view (more detail). The app remembers your choice."),
            step("btn_night", "{label} switches between a dark and a light look."),
            step("helper", "That's me! Click me or press F1 whenever you need help. You can hide me from my "
                           "panel. F1 or “Settings…” brings me back.",
                 missing="The ? button is hidden. Tick “Show the ? help button” in Settings… to bring it "
                         "back."),
        ],
    },
]
