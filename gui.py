"""Desktop app for the waiver OCR tool (Windows, Tkinter).

UI only. Reading PDFs is done by pipeline.py and saving by spreadsheet.py, the same code
the command-line tool (main.py) uses. Start it with "Open OCR App.bat" or `python gui.py`.
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

from dotenv import load_dotenv, set_key

import pipeline
from friendly_errors import describe_error, describe_save_error, scrub
from spreadsheet import (
    FIELD_COLUMNS,
    MASTER_FILENAME,
    MERGE_FLAG_COLUMNS,
    RUN_FILE_PREFIX,
    build_master_rows,
    count_contact_rows,
    replace_master,
    review_reasons,
    save_rows_as_new,
)

try:  # Drag-and-drop is optional; "Choose PDFs" works without it.
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - depends on the installed packages
    TkinterDnD = None
    DND_FILES = None

APP_TITLE = "Waiver Contacts"
LOG_DIR = pipeline.ROOT / "logs"
log = logging.getLogger("waiver_app")

REVIEW_BG = "#fff2cc"  # same yellow the spreadsheet uses for cells to review
DAY = {"fg": "black", "field": "white", "error": "#a4262c", "ok": "#1b6e35", "active": "#0b5cad",
       "muted": "#5b6470", "warn": "#8a5a00"}
NIGHT = {"fg": "#e6e6e6", "bg": "#1f1f1f", "field": "#2b2b2b", "button": "#333333", "hover": "#3d3d3d",
         "select": "#2f5a8a", "border": "#454545", "error": "#ff8a8a", "ok": "#7ed69a",
         "active": "#79b8ff", "muted": "#a0a8b3", "warn": "#e0b45c"}

FILE_STATUS = {
    "ready": "Ready",
    "waiting": "Waiting",
    "reading": "Reading…",
    "done": "Done",
    "failed": "Failed",
    "skipped": "Not processed",
}
SUMMARY_STATUS = {"done": "Done", "failed": "Failed", "skipped": "Not processed"}


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def open_path(path: Path | str) -> None:
    """Open a file or folder with its default Windows program. Raises OSError on failure."""
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # noqa: S606 - opening the user's own file
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def pdfs_in(paths) -> list[Path]:
    """Expand dropped/selected paths: PDFs as-is, folders to the PDFs directly inside them."""
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found += sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
        else:
            found.append(path)
    return found


@dataclass
class PdfItem:
    path: Path
    sha: str
    status: str = "ready"
    waivers: str = ""
    message: str = ""


def row_status(row: dict) -> str:
    if row.get("_checked"):
        text = "Checked"
    elif review_reasons(row):
        text = "Needs review"
    else:
        text = "OK"
    return text + (" · edited" if row.get("_edited") else "")


class App:
    def __init__(self, root: tk.Tk, output_dir: Path = pipeline.OUTPUT_DIR):
        self.root = root
        self.output_dir = output_dir
        self.items: list[PdfItem] = []
        self.rows: list[dict] = []
        self.files_summary: list[tuple[str, str, int, str]] = []
        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.unsaved = False
        self.results_stale = False
        self.last_saved: Path | None = None
        self.run_problem = None  # FriendlyError that stopped the last run, if any
        self.output_mode = tk.StringVar(value="new")
        self.only_review = tk.BooleanVar(value=False)
        self.night = tk.BooleanVar(value=os.getenv("NIGHT_MODE", "") == "1")

        scale = root.winfo_fpixels("1i") / 96.0
        self.px = lambda n: int(n * scale)

        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self._on_callback_error
        root.after(100, self._poll_events)
        self.refresh_files()
        self.refresh_review()
        self.refresh_key_label()
        self._update_save_hint()
        if not pipeline.get_api_key():
            root.after(400, lambda: self.open_settings(first_time=True))

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        root, px = self.root, self.px
        root.title(APP_TITLE)
        height = min(px(740), root.winfo_screenheight() - px(80))
        root.geometry(f"{px(1000)}x{height}")
        root.minsize(px(820), min(px(600), height))

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        self.day_theme = style.theme_use()
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family="Segoe UI", size=10)

        outer = ttk.Frame(root, padding=(px(14), px(10)))
        outer.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1, minsize=px(170))
        gap = {"pady": (0, px(8))}

        # Header
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", **gap)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Turn scanned waiver PDFs into a contact spreadsheet.",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.key_label = ttk.Label(header)
        self.key_label.grid(row=0, column=1, rowspan=2, padx=px(10))
        self.btn_night = ttk.Button(header, command=self.toggle_night)
        self.btn_night.grid(row=0, column=2, rowspan=2, padx=(0, px(6)))
        self.btn_details = ttk.Button(header, text="Show details", command=self.toggle_details)
        self.btn_details.grid(row=0, column=3, rowspan=2, padx=(0, px(6)))
        ttk.Button(header, text="Settings…", command=self.open_settings).grid(row=0, column=4, rowspan=2)

        # 1 · Add PDFs
        files = ttk.LabelFrame(outer, text="1   Add PDFs", padding=px(8))
        files.grid(row=1, column=0, sticky="ew", **gap)
        files.columnconfigure(0, weight=1)
        bar = ttk.Frame(files)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(6)))
        self.btn_choose = ttk.Button(bar, text="Choose PDFs…", command=self.choose_pdfs)
        self.btn_input = ttk.Button(bar, text="Load from input folder", command=self.load_input_folder)
        self.btn_remove = ttk.Button(bar, text="Remove selected", command=self.remove_selected)
        self.btn_clear = ttk.Button(bar, text="Clear list", command=self.clear_files)
        for i, button in enumerate((self.btn_choose, self.btn_input, self.btn_remove, self.btn_clear)):
            button.pack(side="left", padx=(0 if i == 0 else px(6), 0))
        self.dnd = hasattr(root, "TkdndVersion")  # only a TkinterDnD.Tk root has tkdnd loaded
        self.files_note = ttk.Label(bar, style="Muted.TLabel")
        self.files_note.pack(side="left", padx=(px(12), 0))

        self.file_tree = ttk.Treeview(files, columns=("file", "status", "waivers", "message"),
                                      show="headings", height=4, selectmode="extended")
        for col, text, width, stretch in (("file", "File", 280, False), ("status", "Status", 110, False),
                                          ("waivers", "Waivers", 70, False), ("message", "Message", 300, True)):
            self.file_tree.heading(col, text=text, anchor="w")
            self.file_tree.column(col, width=px(width), stretch=stretch, anchor="w")
        self.file_tree.grid(row=1, column=0, sticky="ew")
        scroll = ttk.Scrollbar(files, orient="vertical", command=self.file_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.file_tree.configure(yscrollcommand=scroll.set)
        self.file_tree.bind("<Delete>", lambda e: self.remove_selected())
        self.file_tree.bind("<Double-1>", lambda e: self.show_file_info())
        empty_text = ("No PDFs yet. Click Choose PDFs or Load from input folder, or drag PDFs here."
                      if self.dnd else "No PDFs yet. Click Choose PDFs or Load from input folder.")
        self.files_empty = ttk.Label(self.file_tree, style="Placeholder.TLabel", text=empty_text)
        if self.dnd:
            for widget in (files, self.file_tree, self.files_empty):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)

        # 2 · Process
        proc = ttk.LabelFrame(outer, text="2   Process", padding=px(8))
        proc.grid(row=2, column=0, sticky="ew", **gap)
        proc.columnconfigure(4, weight=1)
        self.btn_process = ttk.Button(proc, text="Process PDFs", style="Primary.TButton",
                                      command=self.start_processing)
        self.btn_process.grid(row=0, column=0)
        self.btn_stop = ttk.Button(proc, text="Stop after this file", command=self.request_stop,
                                   state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=(px(6), px(12)))
        self.progress = ttk.Progressbar(proc, mode="determinate", length=px(170))
        self.progress.grid(row=0, column=2)
        self.busy = ttk.Progressbar(proc, mode="indeterminate", length=px(60))
        self.busy.grid(row=0, column=3, padx=(px(6), 0))
        self.busy.grid_remove()
        self.progress_label = ttk.Label(proc, text="Add PDFs, then click Process PDFs.")
        self.progress_label.grid(row=0, column=4, sticky="w", padx=(px(10), 0))
        ttk.Label(proc, style="Muted.TLabel",
                  text="PDFs are uploaded to Google Gemini to be read (needs internet; not offline). "
                       "Files read before are reused at no extra cost."
                  ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(px(6), 0))
        self.failure_label = ttk.Label(proc, style="Error.TLabel", wraplength=px(900), justify="left")
        self.failure_label.grid(row=2, column=0, columnspan=5, sticky="w", pady=(px(4), 0))
        self.failure_label.grid_remove()

        # 3 · Review
        review = ttk.LabelFrame(outer, text="3   Review contacts", padding=px(8))
        review.grid(row=3, column=0, sticky="nsew", **gap)
        review.columnconfigure(0, weight=1)
        review.rowconfigure(1, weight=1)
        top = ttk.Frame(review)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(6)))
        self.summary_label = ttk.Label(top)
        self.summary_label.pack(side="left")
        ttk.Checkbutton(top, text="Only show contacts that need review", variable=self.only_review,
                        command=self.refresh_review).pack(side="right")

        columns = (("status", "Status", 105), ("First Name", "First name", 100),
                   ("Last Name", "Last name", 100), ("Organization", "Organization", 140),
                   ("Visit Date", "Visit date", 85), ("Email", "Email", 170),
                   ("Phone Number", "Phone", 100), ("source", "Source PDF", 200))
        self.review_tree = ttk.Treeview(review, columns=[c[0] for c in columns], show="headings",
                                        selectmode="extended")
        for col, text, width in columns:
            self.review_tree.heading(col, text=text, anchor="w")
            self.review_tree.column(col, width=px(width), minwidth=px(60), anchor="w")
        self.review_tree.grid(row=1, column=0, sticky="nsew")
        rscroll = ttk.Scrollbar(review, orient="vertical", command=self.review_tree.yview)
        rscroll.grid(row=1, column=1, sticky="ns")
        self.review_tree.configure(yscrollcommand=rscroll.set)
        self.review_tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.review_tree.bind("<Return>", lambda e: self.edit_selected())
        self.review_empty = ttk.Label(self.review_tree, style="Placeholder.TLabel",
                                      text="Contacts appear here after processing.")

        actions = ttk.Frame(review)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(6), 0))
        self.btn_edit = ttk.Button(actions, text="Edit / correct…", command=self.edit_selected)
        self.btn_check = ttk.Button(actions, text="Mark as checked", command=self.mark_checked)
        self.btn_source = ttk.Button(actions, text="Open source PDF", command=self.open_selected_source)
        for i, button in enumerate((self.btn_edit, self.btn_check, self.btn_source)):
            button.pack(side="left", padx=(0 if i == 0 else px(6), 0))
        ttk.Label(actions, style="Muted.TLabel",
                  text="Yellow = needs review (Gemini was unsure or a name is blank), "
                       "not necessarily wrong.").pack(side="right")

        # 4 · Save
        save = ttk.LabelFrame(outer, text="4   Save spreadsheet", padding=px(8))
        save.grid(row=4, column=0, sticky="ew", **gap)
        save.columnconfigure(3, weight=1)
        ttk.Radiobutton(save, text="New spreadsheet for this run (recommended)", value="new",
                        variable=self.output_mode, command=self._update_save_hint
                        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(save, text=f"Replace master list, {MASTER_FILENAME} (advanced)", value="master",
                        variable=self.output_mode, command=self._update_save_hint
                        ).grid(row=0, column=2, columnspan=2, sticky="w", padx=(px(16), 0))
        self.save_hint = ttk.Label(save, style="Muted.TLabel", wraplength=px(900), justify="left")
        self.save_hint.grid(row=1, column=0, columnspan=4, sticky="w", pady=(px(2), px(6)))
        self.btn_save = ttk.Button(save, text="Save spreadsheet", style="Primary.TButton",
                                   command=self.save_spreadsheet)
        self.btn_save.grid(row=2, column=0, sticky="w")
        self.btn_open = ttk.Button(save, text="Open spreadsheet", command=self.open_spreadsheet)
        self.btn_open.grid(row=2, column=1, padx=(px(6), 0))
        ttk.Button(save, text="Open output folder", command=self.open_output_folder
                   ).grid(row=2, column=2, padx=(px(6), 0), sticky="w")
        self.save_status = ttk.Label(save, text="Not saved yet.")
        self.save_status.grid(row=2, column=3, sticky="w", padx=(px(12), 0))

        # Details (collapsed by default)
        self.details_frame = ttk.LabelFrame(outer, text="Details (also saved in logs\\app.log)",
                                            padding=px(6))
        self.details_frame.columnconfigure(0, weight=1)
        self.details = tk.Text(self.details_frame, height=6, wrap="word", font=("Consolas", 9),
                               state="disabled", relief="flat")
        self.details.grid(row=0, column=0, sticky="ew")
        self.details_open = False
        self.apply_theme()

    def apply_theme(self) -> None:
        """Day keeps the native Windows look; night uses "clam", the built-in theme that honours colours."""
        night = self.night.get()
        c = NIGHT if night else DAY
        px, style = self.px, ttk.Style(self.root)
        style.theme_use("clam" if night else self.day_theme)
        if night:
            bg, fg, field = c["bg"], c["fg"], c["field"]
            style.configure(".", background=bg, foreground=fg, fieldbackground=field, troughcolor=field,
                            bordercolor=c["border"], lightcolor=bg, darkcolor=bg, arrowcolor=fg,
                            selectbackground=c["select"], selectforeground=fg, insertcolor=fg)
            style.map(".", background=[("disabled", bg)], foreground=[("disabled", "#777777")])
            style.configure("TButton", background=c["button"])
            style.map("TButton", background=[("disabled", bg), ("pressed", c["border"]), ("active", c["hover"])])
            style.configure("Treeview", background=field, foreground=fg)
            style.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", fg)])
            style.configure("Treeview.Heading", background=c["button"])
            style.map("Treeview.Heading", background=[("active", c["hover"])])
            for name in ("TCheckbutton", "TRadiobutton"):
                style.configure(name, indicatorbackground=field, indicatorforeground=fg,
                                indicatorsize=px(13))
                style.map(name, background=[("active", bg)], indicatorbackground=[("pressed", bg)])
            style.configure("TScrollbar", background=c["button"])
            style.map("TScrollbar", background=[("active", c["hover"])])
        # Style settings belong to a theme, so the app's own styles are set again after each switch.
        style.configure("Treeview", rowheight=px(24))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 15))
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("Placeholder.TLabel", foreground=c["muted"], background=c["field"])
        style.configure("Warn.TLabel", foreground=c["warn"])
        style.configure("Error.TLabel", foreground=c["error"])
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(px(12), px(4)))
        style.configure("TLabelframe.Label", font=("Segoe UI Semibold", 10))
        for tag in ("failed", "skipped"):
            self.file_tree.tag_configure(tag, foreground=c["error"])
        self.file_tree.tag_configure("done", foreground=c["ok"])
        self.file_tree.tag_configure("reading", foreground=c["active"])
        self.review_tree.tag_configure("review", background=REVIEW_BG, foreground="black")
        self.details.configure(background=c["field"], foreground=c["fg"], insertbackground=c["fg"])
        self.btn_night.configure(text="Day mode" if night else "Night mode")

    def toggle_night(self) -> None:
        self.night.set(not self.night.get())
        self.apply_theme()
        try:
            set_key(pipeline.ENV_PATH, "NIGHT_MODE", "1" if self.night.get() else "0", quote_mode="never")
        except OSError as exc:  # the theme still changes for this session
            self.note("Could not remember night mode.", f"{type(exc).__name__}: {exc}", logging.WARNING)

    # ------------------------------------------------------------------ helpers

    def note(self, message: str, detail: str = "", level: int = logging.INFO) -> None:
        """Add a line to the Details panel and the log file (API keys removed)."""
        text = scrub(message + (f"\n{detail}" if detail else ""))
        log.log(level, text)
        self.details.configure(state="normal")
        self.details.insert("end", text + "\n")
        self.details.see("end")
        self.details.configure(state="disabled")

    def toggle_details(self) -> None:
        self.details_open = not self.details_open
        if self.details_open:
            self.details_frame.grid(row=5, column=0, sticky="ew")
            self.btn_details.configure(text="Hide details")
        else:
            self.details_frame.grid_remove()
            self.btn_details.configure(text="Show details")

    def refresh_key_label(self) -> None:
        if pipeline.get_api_key():
            self.key_label.configure(text="API key: set", style="Muted.TLabel")
        else:
            self.key_label.configure(text="API key: not set", style="Error.TLabel")

    def _set_running(self, running: bool) -> None:
        self.running = running
        idle = "disabled" if running else "normal"
        for button in (self.btn_choose, self.btn_input, self.btn_remove, self.btn_clear,
                       self.btn_process, self.btn_save, self.btn_edit, self.btn_check):
            button.configure(state=idle)
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running:
            self.busy.grid()
            self.busy.start(15)
        else:
            self.busy.stop()
            self.busy.grid_remove()

    def _on_callback_error(self, exc_type, exc, tb) -> None:
        self.note("Unexpected error in the app.", "".join(traceback.format_exception(exc_type, exc, tb)),
                  logging.ERROR)
        messagebox.showerror(APP_TITLE, "Something unexpected went wrong. Your list and results are "
                             "still here. Technical details are under Show details (top right).", parent=self.root)

    # ------------------------------------------------------------------ 1 · files

    def _on_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))
        return event.action

    def choose_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose waiver PDFs",
                                            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if paths:
            self.add_paths(paths)

    def load_input_folder(self) -> None:
        pipeline.INPUT_DIR.mkdir(exist_ok=True)
        pdfs = pdfs_in([pipeline.INPUT_DIR])
        if not pdfs:
            if messagebox.askyesno("Input folder is empty",
                                   f"There are no PDFs in the input folder:\n{pipeline.INPUT_DIR}\n\n"
                                   "Open the folder now so you can put PDFs in it?", parent=self.root):
                self._try_open(pipeline.INPUT_DIR)
            return
        self.add_paths(pdfs)

    def add_paths(self, paths) -> None:
        if self.running:
            return
        added, duplicates, skipped = 0, [], []
        known_paths = {os.path.normcase(str(item.path)): item for item in self.items}
        known_hashes = {item.sha: item for item in self.items}
        for path in pdfs_in(paths):
            if path.suffix.lower() != ".pdf":
                skipped.append(f"{path.name} (not a PDF)")
                continue
            path = path.resolve()
            if os.path.normcase(str(path)) in known_paths:
                duplicates.append(path.name)
                continue
            try:
                sha = pipeline.file_sha256(path)
            except OSError as exc:
                skipped.append(f"{path.name} (can't be opened)")
                self.note(f"Could not open {path.name}.", f"{type(exc).__name__}: {exc}")
                continue
            if sha in known_hashes:
                duplicates.append(f"{path.name} (same file as {known_hashes[sha].path.name})")
                continue
            item = PdfItem(path, sha)
            self.items.append(item)
            known_paths[os.path.normcase(str(path))] = item
            known_hashes[sha] = item
            added += 1

        if added and self.rows:
            self.results_stale = True
        parts = []
        if added:
            parts.append(f"Added {added} PDF{'s' if added != 1 else ''}.")
        if duplicates:
            parts.append("Already in the list, not added again: " + ", ".join(duplicates) + ".")
        if skipped:
            parts.append("Skipped: " + ", ".join(skipped) + ".")
        self.files_note.configure(text=" ".join(parts))
        self.refresh_files()

    def remove_selected(self) -> None:
        if self.running:
            return
        selected = set(self.file_tree.selection())
        if not selected:
            return
        self.items = [item for item in self.items if self._file_iid(item) not in selected]
        self.results_stale = bool(self.rows)
        self.files_note.configure(text=f"Removed {len(selected)} file(s) from the list. "
                                       "The PDFs themselves were not changed.")
        self.refresh_files()

    def clear_files(self) -> None:
        if self.running or not self.items:
            return
        self.items = []
        self.results_stale = bool(self.rows)
        self.files_note.configure(text="List cleared. The PDFs themselves were not changed.")
        self.refresh_files()

    def show_file_info(self) -> None:
        """Full status message for one file (the list column may cut it off)."""
        selected = self.file_tree.selection()
        item = next((i for i in self.items if self._file_iid(i) in selected), None)
        if item:
            text = f"{item.path}\n\nStatus: {FILE_STATUS[item.status]}"
            if item.message:
                text += f"\n\n{item.message}"
            messagebox.showinfo(item.path.name, text, parent=self.root)

    @staticmethod
    def _file_iid(item: PdfItem) -> str:
        return os.path.normcase(str(item.path))

    def refresh_files(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        for item in self.items:
            self.file_tree.insert("", "end", iid=self._file_iid(item), tags=(item.status,),
                                  values=(item.path.name, FILE_STATUS[item.status], item.waivers, item.message))
        if self.items:
            self.files_empty.place_forget()
        else:
            self.files_empty.place(relx=0.5, rely=0.55, anchor="center")

    # ------------------------------------------------------------------ 2 · process

    def start_processing(self) -> None:
        if self.running:
            return
        if not self.items:
            messagebox.showinfo("No PDFs", "Add PDFs first: click Choose PDFs, or Load from input folder.",
                                parent=self.root)
            return
        api_key = pipeline.get_api_key()
        if not api_key:
            messagebox.showinfo("API key needed", "Add the Gemini API key in Settings first.", parent=self.root)
            self.open_settings(first_time=True)
            return
        if self.unsaved and self.rows and not messagebox.askyesno(
                "Process again?", "Processing again replaces the contacts below, including any "
                "corrections you have not saved yet. Continue?", parent=self.root):
            return

        for item in self.items:
            item.status, item.waivers, item.message = "waiting", "", ""
        self.refresh_files()
        self.rows, self.files_summary = [], []
        self.unsaved, self.results_stale, self.last_saved, self.run_problem = False, False, None, None
        self.save_status.configure(text="Not saved yet.")
        self.failure_label.grid_remove()
        self.refresh_review()

        self.progress.configure(maximum=len(self.items), value=0)
        self.progress_label.configure(text="Starting…")
        self.stop_event.clear()
        self._set_running(True)
        paths = [item.path for item in self.items]
        self.note(f"Processing {len(paths)} PDF(s) with model {pipeline.get_model()}.")
        threading.Thread(target=self._work, args=(paths, api_key), daemon=True).start()

    def _work(self, paths: list[Path], api_key: str) -> None:
        """Runs in a background thread. Talks to the window only through self.events."""
        try:
            result = pipeline.run_batch(paths, api_key, on_event=lambda *e: self.events.put(e),
                                        stop_event=self.stop_event)
        except Exception as exc:
            self.events.put(("fatal", describe_error(exc)))
            return
        self.events.put(("finished", result))

    def request_stop(self) -> None:
        self.stop_event.set()
        self.btn_stop.configure(state="disabled")
        self.progress_label.configure(text="Stopping after the current file…")

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(*self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, kind: str, *args) -> None:
        if kind == "start":
            index = args[0]
            item = self.items[index]
            item.status = "reading"
            self.progress_label.configure(
                text=f"Reading {item.path.name} (file {index + 1} of {len(self.items)}). "
                     "Large scans can take a few minutes.")
        elif kind in ("done", "failed", "skipped"):
            index, result = args[0], args[1]
            item = self.items[index]
            item.status = kind
            if kind == "done":
                item.waivers = str(result.waivers)
                item.message = "Reused earlier result (no new charge)" if result.from_cache else ""
                self.note(f"{item.path.name}: {result.waivers} waiver(s)"
                          + (" (reused earlier result)" if result.from_cache else "") + ".")
            elif kind == "failed":
                friendly = args[2]
                item.message = friendly.message
                if friendly.stops_run:
                    self.run_problem = friendly
                self.note(f"{item.path.name}: FAILED: {friendly.title}.", friendly.detail, logging.WARNING)
            else:
                item.message = result.message
            self.progress.configure(value=sum(i.status in ("done", "failed", "skipped") for i in self.items))
        elif kind == "finished":
            self._finish(args[0])
        elif kind == "fatal":
            friendly = args[0]
            self._set_running(False)
            for item in self.items:
                if item.status in ("waiting", "reading"):
                    item.status = "ready"
            self.progress_label.configure(text="Processing could not start.")
            self.note(f"Processing could not start: {friendly.title}.", friendly.detail, logging.ERROR)
            message = (friendly.message if friendly.kind != "unknown" else
                       "Processing could not start. Technical details are under Show details (top right).")
            messagebox.showerror("Could not start processing", message, parent=self.root)
        self.refresh_files()

    def _finish(self, result: pipeline.BatchResult) -> None:
        self._set_running(False)
        for item, file_result in zip(self.items, result.files):  # final word on each file's status
            item.status = file_result.status
            item.message = file_result.message or item.message
            item.waivers = str(file_result.waivers) if file_result.status == "done" else ""
        self.rows = build_master_rows(result.records)
        self.files_summary = [(f.path.name, SUMMARY_STATUS[f.status], f.waivers, f.message)
                              for f in result.files]
        self.unsaved = bool(self.rows)
        not_read = [f for f in result.files if f.status != "done"]
        done = len(result.files) - len(not_read)
        stopped = " Stopped early." if self.stop_event.is_set() else ""
        self.progress_label.configure(
            text=f"Finished: {done} of {len(result.files)} file(s) read, "
                 f"{len(result.records)} waiver(s) found.{stopped}")
        self.note(f"Run finished: {done} of {len(result.files)} files read, "
                  f"{len(result.records)} waivers, {len(self.rows)} contacts after merging repeat visits.")

        if not_read:
            names = ", ".join(f.path.name for f in not_read[:5]) + (" …" if len(not_read) > 5 else "")
            self.failure_label.configure(
                text=f"Not read: {names} (reason shown above). You can still save the other contacts; "
                     "the spreadsheet's Files sheet records what failed.")
            self.failure_label.grid()
        if self.run_problem:
            messagebox.showwarning(self.run_problem.title, self.run_problem.message
                                   + "\n\nThe remaining files were not sent.", parent=self.root)
        self.refresh_review()

    # ------------------------------------------------------------------ 3 · review

    def refresh_review(self) -> None:
        tree = self.review_tree
        tree.delete(*tree.get_children())
        need = sum(1 for row in self.rows if row_status(row).startswith("Needs review"))
        checked = sum(1 for row in self.rows if row.get("_checked"))
        for index, row in enumerate(self.rows):
            status = row_status(row)
            if self.only_review.get() and not status.startswith("Needs review"):
                continue
            source = f"{row.get('_source_file', '')}, page {row.get('_source_page', '?')}"
            values = [status] + [row.get(col, "") for col in tree["columns"][1:-1]] + [source]
            tree.insert("", "end", iid=str(index), values=values,
                        tags=("review",) if status.startswith("Needs review") else ())

        if self.rows:
            self.review_empty.place_forget()
            text = f"{len(self.rows)} contact(s) · {need} need review"
            if checked:
                text += f" · {checked} checked by you"
            if self.results_stale:
                text += " · the PDF list changed; process again to update"
        else:
            self.review_empty.place(relx=0.5, rely=0.45, anchor="center")
            text = "No contacts yet."
        self.summary_label.configure(text=text)

    def _selected_rows(self) -> list[dict]:
        return [self.rows[int(iid)] for iid in self.review_tree.selection()]

    def edit_selected(self) -> None:
        if self.running:
            return
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo("Edit contact", "Select a contact in the list first.", parent=self.root)
            return
        if EditDialog(self, rows[0]).changed:
            self.unsaved = True
            self.refresh_review()

    def mark_checked(self) -> None:
        if self.running:
            return
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo("Mark as checked", "Select one or more contacts first.", parent=self.root)
            return
        for row in rows:
            for _, confident_col, _ in FIELD_COLUMNS:
                row[confident_col] = True
            for _, confident_col in MERGE_FLAG_COLUMNS:
                row[confident_col] = True
            row["_checked"] = True
        self.unsaved = True
        self.refresh_review()

    def open_selected_source(self) -> None:
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo("Open source PDF", "Select a contact in the list first.", parent=self.root)
            return
        self.open_source(rows[0])

    def open_source(self, row: dict, parent=None) -> None:
        parent = parent or self.root
        path = row.get("_source_path", "")
        link = str(row.get("Source_PDF_Link", ""))
        page = row.get("_source_page", "?")
        if path and Path(path).exists():
            if self._try_open(path, parent):
                self.progress_label.configure(text=f"Opened {Path(path).name}. Look at page {page}.")
        elif link.startswith(("http://", "https://")):
            webbrowser.open(link)
        else:
            messagebox.showwarning("PDF not found", f"The source PDF is no longer at:\n{path}", parent=parent)

    # ------------------------------------------------------------------ 4 · save

    def _update_save_hint(self) -> None:
        if self.output_mode.get() == "new":
            self.save_hint.configure(
                style="Muted.TLabel",
                text=f"Each save creates a new file in the output folder, for example "
                     f"{RUN_FILE_PREFIX}_2026-11-18_14-30-05.xlsx. Existing spreadsheets are never replaced.")
        else:
            self.save_hint.configure(
                style="Warn.TLabel",
                text=f"Replaces output\\{MASTER_FILENAME} (the file the command-line tool writes) with "
                     "the contacts shown here. The old version is copied to output\\backups first. "
                     "Contacts that are only in the old file are not carried over.")

    def save_spreadsheet(self) -> None:
        if self.running:
            return
        if not self.rows:
            messagebox.showinfo("Nothing to save", "Process PDFs first. There are no contacts to save yet.",
                                parent=self.root)
            return
        if self.results_stale and not messagebox.askyesno(
                "PDF list changed", "The PDF list changed after processing. Save the contacts from the "
                "last run anyway?", parent=self.root):
            return

        master = self.output_dir / MASTER_FILENAME
        target = master
        try:
            if self.output_mode.get() == "master":
                if not self._confirm_replace_master(master):
                    return
                path, backup = replace_master(self.rows, master, self.files_summary)
                if backup:
                    self.note(f"Backed up the previous master list to {backup}.")
            else:
                target = self.output_dir / f"{RUN_FILE_PREFIX}_….xlsx"
                path = save_rows_as_new(self.rows, self.output_dir, self.files_summary)
        except Exception as exc:
            friendly = describe_save_error(exc, target)
            self.note(f"Saving failed: {friendly.title}.", friendly.detail, logging.ERROR)
            messagebox.showerror(friendly.title, friendly.message, parent=self.root)
            return

        self.last_saved, self.unsaved = path, False
        self.save_status.configure(text=f"Saved: {path.name}")
        self.note(f"Saved {len(self.rows)} contact(s) to {path}.")
        if messagebox.askyesno("Spreadsheet saved", f"Saved to:\n{path}\n\nOpen it now?", parent=self.root):
            self.open_spreadsheet()

    def _confirm_replace_master(self, master: Path) -> bool:
        message = (f"This replaces {master.name} with the {len(self.rows)} contact(s) shown here.\n\n")
        if master.exists():
            existing = count_contact_rows(master)
            count = f"{existing} contact(s)" if existing is not None else "contacts"
            message += (f"The current master list has {count}. A backup copy is saved in "
                        f"output\\backups first. Contacts that are only in the current master list "
                        f"will not be in the new file.\n\n")
        return messagebox.askyesno("Replace master list?", message + "Continue?", icon="warning",
                                   parent=self.root)

    def _try_open(self, path, parent=None) -> bool:
        try:
            open_path(path)
            return True
        except Exception as exc:
            self.note(f"Could not open {path}.", f"{type(exc).__name__}: {exc}", logging.WARNING)
            messagebox.showinfo("Could not open", f"Windows could not open this automatically:\n{path}\n\n"
                                "You can find it with File Explorer.", parent=parent or self.root)
            return False

    def open_spreadsheet(self) -> None:
        if not self.last_saved:
            messagebox.showinfo("Open spreadsheet", "Save the spreadsheet first.", parent=self.root)
            return
        if not self.last_saved.exists():
            messagebox.showwarning("Open spreadsheet", f"The file is no longer at:\n{self.last_saved}",
                                   parent=self.root)
            return
        try:
            open_path(self.last_saved)
        except Exception as exc:
            self.note("Could not open the spreadsheet.", f"{type(exc).__name__}: {exc}", logging.WARNING)
            messagebox.showinfo("Spreadsheet saved, but not opened",
                                f"The spreadsheet is saved here:\n{self.last_saved}\n\nNo program on this "
                                "computer opened it (Excel may not be installed). Use Open output folder "
                                "to find it.", parent=self.root)

    def open_output_folder(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._try_open(self.output_dir)

    # ------------------------------------------------------------------ settings / close

    def open_settings(self, first_time: bool = False) -> None:
        if not self.running:
            SettingsDialog(self, first_time)

    def on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("Processing is still running",
                                       "Close anyway? The file being read right now will not be finished. "
                                       "Files that already finished are kept and won't be charged again.",
                                       icon="warning", parent=self.root):
                return
        elif self.unsaved and not messagebox.askyesno(
                "Close without saving?", "These contacts have not been saved to a spreadsheet, and "
                "corrections you made will be lost. Close anyway?", icon="warning", parent=self.root):
            return
        self.root.destroy()


class EditDialog(tk.Toplevel):
    """Correct one contact. Ticking or unticking 'Needs review' sets the *_Confident column."""

    def __init__(self, app: App, row: dict):
        super().__init__(app.root)
        self.app, self.row, self.changed = app, row, False
        px = app.px
        self.title("Edit contact")
        self.transient(app.root)
        self.resizable(True, False)
        frame = ttk.Frame(self, padding=px(12))
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        source = ttk.Frame(frame)
        source.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, px(4)))
        ttk.Label(source, text=f"From {row.get('_source_file', '?')}, page {row.get('_source_page', '?')}"
                  ).pack(side="left")
        ttk.Button(source, text="Open PDF", command=lambda: app.open_source(row, self)).pack(side="left",
                                                                                              padx=px(8))
        line = 1
        if row.get("_other_sources"):
            ttk.Label(frame, style="Muted.TLabel", wraplength=px(560), justify="left",
                      text="Earlier visits: " + "; ".join(row["_other_sources"])
                      ).grid(row=line, column=0, columnspan=3, sticky="w")
            line += 1
        ttk.Label(frame, style="Muted.TLabel", wraplength=px(560), justify="left",
                  text="Correct any value to match the PDF, then untick “Needs review”. "
                       "Yellow boxes are the ones flagged for review."
                  ).grid(row=line, column=0, columnspan=3, sticky="w", pady=(0, px(8)))
        line += 1

        self.fields = []
        colors = NIGHT if app.night.get() else DAY
        for value_col, confident_col, _ in FIELD_COLUMNS:
            ttk.Label(frame, text=value_col).grid(row=line, column=0, sticky="nw", padx=(0, px(8)), pady=px(2))
            if value_col == "Notes":
                widget = tk.Text(frame, height=3, width=56, wrap="word", font=("Segoe UI", 10),
                                 relief="solid", borderwidth=1, insertbackground=colors["fg"])
                widget.insert("1.0", str(row.get(value_col, "")))
                get = lambda w=widget: w.get("1.0", "end-1c")
            else:
                var = tk.StringVar(value=str(row.get(value_col, "")))
                widget = tk.Entry(frame, textvariable=var, width=56, font=("Segoe UI", 10),
                                  relief="solid", borderwidth=1, insertbackground=colors["fg"])
                get = var.get
            widget.grid(row=line, column=1, sticky="ew", pady=px(2))
            flag = tk.BooleanVar(value=not row.get(confident_col, False))
            ttk.Checkbutton(frame, text="Needs review", variable=flag,
                            command=lambda w=widget, f=flag: self._paint(w, f, colors)
                            ).grid(row=line, column=2, sticky="nw", padx=(px(8), 0), pady=px(2))
            self._paint(widget, flag, colors)
            self.fields.append((value_col, confident_col, get, flag))
            line += 1

        self.merge_flag = tk.BooleanVar(value=any(not row.get(c, False) for _, c in MERGE_FLAG_COLUMNS))
        visits = row.get("Visit Count", 1)
        prior = row.get("All Prior Visit Dates", "") or "none"
        ttk.Label(frame, text="Visits").grid(row=line, column=0, sticky="w", pady=px(2))
        ttk.Label(frame, text=f"{visits} visit(s); earlier visit dates: {prior}"
                  ).grid(row=line, column=1, sticky="w", pady=px(2))
        ttk.Checkbutton(frame, text="Needs review", variable=self.merge_flag
                        ).grid(row=line, column=2, sticky="w", padx=(px(8), 0))
        line += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=line, column=0, columnspan=3, sticky="e", pady=(px(10), 0))
        ttk.Button(buttons, text="Save changes", style="Primary.TButton", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(px(6), 0))
        self.bind("<Escape>", lambda e: self.destroy())

        self.grab_set()
        self.wait_window()

    @staticmethod
    def _paint(widget, flag: tk.BooleanVar, colors: dict) -> None:
        # Yellow boxes keep dark text so they stay readable in night mode.
        flagged = flag.get()
        widget.configure(background=REVIEW_BG if flagged else colors["field"],
                         foreground="black" if flagged else colors["fg"])

    def save(self) -> None:
        row = self.row
        edited = False
        for value_col, confident_col, get, flag in self.fields:
            new_value = get().strip()
            if new_value != str(row.get(value_col, "")):
                row[value_col] = new_value
                edited = True
            row[confident_col] = not flag.get()
        for _, confident_col in MERGE_FLAG_COLUMNS:
            row[confident_col] = not self.merge_flag.get()
        row["_edited"] = row.get("_edited", False) or edited
        any_flag = any(f.get() for *_, f in self.fields) or self.merge_flag.get()
        row["_checked"] = row.get("_checked", False) and not any_flag
        self.changed = True
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """First-time key entry. The key is saved only in this folder's .env file."""

    def __init__(self, app: App, first_time: bool = False):
        super().__init__(app.root)
        self.app = app
        px = app.px
        self.results: queue.Queue = queue.Queue()
        self.title("Settings")
        self.transient(app.root)
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=px(14))
        frame.grid(sticky="nsew")
        wrap = px(470)

        if first_time:
            ttk.Label(frame, wraplength=wrap, justify="left",
                      text="Before PDFs can be read, add the Gemini API key. This is done once per "
                           "computer, usually by the person who set up the app."
                      ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, px(10)))
        ttk.Label(frame, text="Gemini API key").grid(row=1, column=0, sticky="w")
        self.key_var = tk.StringVar(value=pipeline.get_api_key())
        self.entry = ttk.Entry(frame, textvariable=self.key_var, show="•", width=46)
        self.entry.grid(row=1, column=1, sticky="ew", padx=(px(8), 0))
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Show", variable=self.show_var,
                        command=lambda: self.entry.configure(show="" if self.show_var.get() else "•")
                        ).grid(row=1, column=2, padx=(px(6), 0))
        ttk.Label(frame, style="Muted.TLabel", wraplength=wrap, justify="left",
                  text=f"Saved only on this computer, in the .env file in the app folder. "
                       f"Model: {pipeline.get_model()}."
                  ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(px(6), 0))
        ttk.Label(frame, style="Muted.TLabel", wraplength=wrap, justify="left",
                  text="Privacy: when you process PDFs, their pages are uploaded to Google Gemini to be "
                       "read. The app is not offline."
                  ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(px(4), 0))
        self.test_label = ttk.Label(frame, wraplength=wrap, justify="left")
        self.test_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(px(8), 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(px(10), 0))
        self.btn_test = ttk.Button(buttons, text="Test key", command=self.test)
        self.btn_test.pack(side="left")
        ttk.Button(buttons, text="Save", style="Primary.TButton", command=self.save
                   ).pack(side="left", padx=(px(6), 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(px(6), 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.save())
        self.entry.focus_set()
        self.grab_set()
        self.wait_window()

    def _clean_key(self) -> str | None:
        key = self.key_var.get().strip()
        if not key or any(ch.isspace() for ch in key):
            self.test_label.configure(style="Error.TLabel",
                                      text="Paste the whole key (one word, no spaces).")
            return None
        return key

    def test(self) -> None:
        """Checks the key by looking up the model's details. This does not read any PDF."""
        key = self._clean_key()
        if not key:
            return
        self.btn_test.configure(state="disabled")
        self.test_label.configure(style="TLabel", text="Testing…")

        def work():
            try:
                pipeline.make_client(key).models.get(model=pipeline.get_model())
                self.results.put(None)
            except Exception as exc:
                self.results.put(describe_error(exc))

        threading.Thread(target=work, daemon=True).start()
        self.after(150, self._poll_test)

    def _poll_test(self) -> None:
        if not self.winfo_exists():
            return
        try:
            problem = self.results.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_test)
            return
        self.btn_test.configure(state="normal")
        if problem is None:
            self.test_label.configure(style="TLabel", text="✓ The key works. Click Save to keep it.")
        else:
            self.app.note(f"Key test failed: {problem.title}.", problem.detail, logging.WARNING)
            text = problem.message if problem.kind != "unknown" else "The key could not be checked."
            self.test_label.configure(style="Error.TLabel", text=f"{problem.title}. {text}")

    def save(self) -> None:
        key = self._clean_key()
        if not key:
            return
        try:
            set_key(pipeline.ENV_PATH, "GEMINI_API_KEY", key, quote_mode="never")
        except OSError as exc:
            self.app.note("Could not save the API key.", f"{type(exc).__name__}: {exc}", logging.ERROR)
            messagebox.showerror("Could not save", f"The key could not be saved to\n{pipeline.ENV_PATH}\n\n"
                                 "Check that the folder is not read-only.", parent=self)
            return
        os.environ["GEMINI_API_KEY"] = key
        self.app.note("API key saved in .env.")
        self.app.refresh_key_label()
        self.destroy()


def main() -> None:
    setup_logging()
    load_dotenv(pipeline.ENV_PATH)
    try:
        if sys.platform == "win32":
            try:  # sharp text on high-DPI screens
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        App(root)
        log.info("App started.")
        root.mainloop()
    except Exception:
        details = scrub(traceback.format_exc())
        log.error("Startup failed:\n%s", details)
        error_file = LOG_DIR / "startup-error.log"
        error_file.write_text(details, encoding="utf-8")
        try:
            box = tk.Tk()
            box.withdraw()
            messagebox.showerror(APP_TITLE, "The app could not start.\n\nTechnical details were saved to:\n"
                                 f"{error_file}\n\nTry running Setup.bat again.")
            box.destroy()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
