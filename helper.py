"""The "?" help character: a launcher in the header, a help panel, and "Show me how" tutorials.

Tutorial content lives in tutorials.py; this file only draws it. The panel and step bubble are
frames placed inside the app window, so they move and resize with it. A tutorial only reads where
controls are and draws a ring around them: it never clicks, processes, saves or changes settings.
Works offline: nothing here uses the network.
"""
from __future__ import annotations

import os
import random
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from dotenv import set_key

import pipeline
from tutorials import TARGETS, TUTORIALS

BODY, EDGE, ARM, INK, CHEEK, MOUTH = "#f5a524", "#c27a0e", "#9a5f0a", "#2a2321", "#f4978e", "#8e3b2e"


def reduced_motion() -> bool:
    """True when Windows' "Show animations in Windows" setting is off."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        enabled = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)  # SPI_GETCLIENTAREAANIMATION
        return not enabled.value
    except Exception:
        return False


def steps_for(tutorial: dict, topic_id: str | None = None, flags: dict | None = None) -> list[tuple[str, dict]]:
    """(where-label, step) pairs for a whole tutorial or one of its topics, minus steps whose
    `when` flag is off."""
    flags = flags or {}
    topics = tutorial.get("topics")
    if not topics:
        sections = [("", tutorial["steps"])]
    elif topic_id:
        sections = [(t["title"], t["steps"]) for t in topics if t["id"] == topic_id]
    else:
        sections = [(f"Topic {n} of {len(topics)}: {t['title']}", t["steps"]) for n, t in enumerate(topics, 1)]
    return [(where, s) for where, steps in sections for s in steps if not s["when"] or flags.get(s["when"])]


def bubble_position(window: tuple[int, int], target, size: tuple[int, int], gap: int) -> tuple[int, int]:
    """Top-left corner for a bubble of `size` inside `window` (w, h), beside `target` (x, y, w, h)
    without covering it: below, above, right, left, then whichever spot covers it least."""
    (win_w, win_h), (bw, bh) = window, size
    hi_x, hi_y = max(win_w - bw - gap, 0), max(win_h - bh - gap, 0)

    def clamp(value, high):
        return max(min(value, high), min(gap, high))

    if target is None:
        return max((win_w - bw) // 2, 0), max((win_h - bh) // 3, 0)
    tx, ty, tw, th = target
    beside = [(clamp(tx, hi_x), ty + th + gap), (clamp(tx, hi_x), ty - gap - bh),
              (tx + tw + gap, clamp(ty, hi_y)), (tx - gap - bw, clamp(ty, hi_y))]
    for x, y in beside:
        if 0 <= x <= win_w - bw and 0 <= y <= win_h - bh:
            return x, y

    def covered(spot):
        x, y = spot
        return max(0, min(x + bw, tx + tw) - max(x, tx)) * max(0, min(y + bh, ty + th) - max(y, ty))

    corners = [(gap, gap), (hi_x, gap), (gap, hi_y), (hi_x, hi_y)]
    return min([(clamp(x, hi_x), clamp(y, hi_y)) for x, y in beside + corners], key=covered)


class Mascot(tk.Canvas):
    """The question mark itself is the character: face on the curve, small arms on the stem.
    Drawn as vectors in a 64 x 84 grid, so it stays sharp at any size and display scaling."""

    W, H = 64, 84
    # The left arm waves: there is open space under the hook's tip.
    ARMS = {"rest": (23, 51, 16, 56, 13, 62), "up": (24, 50, 15, 45, 9, 37), "mid": (24, 50, 14, 48, 6, 44)}

    def __init__(self, parent, scale: float, bg: str, animate: bool = False, focusable: bool = False):
        self.s, self.pad = scale, 2 if focusable else 0
        super().__init__(parent, width=round(self.W * scale) + 2 * self.pad,
                         height=round(self.H * scale) + 2 * self.pad, bg=bg, bd=0,
                         highlightthickness=self.pad, highlightbackground=bg, takefocus=focusable,
                         cursor="hand2" if focusable else "")
        self.animate = animate
        self.jobs: list[str] = []
        self._draw()
        if animate:
            self._later(random.randint(3000, 6000), self.blink)
        self.bind("<Destroy>", lambda e: self._cancel() if e.widget is self else None, add="+")

    def _p(self, *coords):
        return [self.pad + v * self.s for v in coords]

    def _draw(self) -> None:
        width = 20 * self.s
        for color, dx, dy in ((EDGE, 1.3, 1.6), (BODY, 0, 0)):  # a soft edge below and right, then the body
            self.create_arc(*self._p(15 + dx, 13 + dy, 49 + dx, 47 + dy), start=-50, extent=215,
                            style="arc", outline=color, width=width)
            self.create_oval(*self._p(5.6 + dx, 15.6 + dy, 25.6 + dx, 35.6 + dy), fill=color, outline="")
            self.create_line(*self._p(42.9 + dx, 43 + dy, 35 + dx, 49 + dy, 32 + dx, 54 + dy),
                             fill=color, width=width, capstyle="round", smooth=True)
            self.create_oval(*self._p(24 + dx, 67 + dy, 40 + dx, 83 + dy), fill=color, outline="")
        for x in (19, 40):
            self.create_oval(*self._p(x, 15.5, x + 5, 18.5), fill=CHEEK, outline="")
        self.eyes = []
        for x in (26, 38):
            eye = self.create_oval(*self._p(x - 2.6, 7.5, x + 2.6, 14), fill=INK, outline="")
            shine = self.create_oval(*self._p(x - 1.2, 8.4, x + 0.4, 10), fill="white", outline="")
            self.eyes.append((eye, shine, x))
        self.create_arc(*self._p(27, 12, 37, 20), start=200, extent=140, style="arc", outline=MOUTH,
                        width=max(1.0, 1.8 * self.s))
        arm = max(1.5, 3.2 * self.s)
        self.create_line(*self._p(41, 51, 48, 56, 51, 62), fill=ARM, width=arm, capstyle="round", smooth=True)
        self.arm = self.create_line(*self._p(*self.ARMS["rest"]), fill=ARM, width=arm, capstyle="round",
                                    smooth=True)

    def _later(self, ms: int, func) -> None:
        self.jobs = [j for j in self.jobs if j in self.tk.call("after", "info")]
        self.jobs.append(self.after(ms, func))

    def _cancel(self) -> None:
        for job in self.jobs:
            self.after_cancel(job)
        self.jobs = []

    def blink(self) -> None:
        if self.winfo_viewable():
            for eye, shine, x in self.eyes:
                self.coords(eye, *self._p(x - 2.6, 10.6, x + 2.6, 11.4))
                self.itemconfigure(shine, state="hidden")
            self.after(140, self._open_eyes)
        self._later(random.randint(4500, 8000), self.blink)

    def _open_eyes(self) -> None:
        for eye, shine, x in self.eyes:
            self.coords(eye, *self._p(x - 2.6, 7.5, x + 2.6, 14))
            self.itemconfigure(shine, state="normal")

    def wave(self) -> None:
        """A short wave that settles back to rest. Skipped when animations are off."""
        if not self.animate:
            return
        for n, pose in enumerate(("up", "mid", "up", "mid", "up", "rest")):
            self._later(n * 150, lambda pose=pose: self.coords(self.arm, *self._p(*self.ARMS[pose])))


class Helper:
    """The launcher button, its panel, and the step-by-step "Show me how" runner."""

    def __init__(self, app, header, column: int):
        self.app, self.root, px = app, app.root, app.px
        self.hidden = os.getenv("HELPER_HIDDEN", "") == "1"
        self.motion = not reduced_motion()
        self.card = None
        self.ring: list[tk.Frame] = []
        self.run: dict | None = None
        self.done: set = set()
        self.return_focus = None
        self._layout_job = None
        self.launcher = Mascot(header, px(46) / Mascot.H, "white", animate=self.motion, focusable=True)
        self.launcher.grid(row=0, column=column, rowspan=2, padx=(px(10), 0))
        if self.hidden:
            self.launcher.grid_remove()
        for event in ("<Button-1>", "<Return>", "<space>"):
            self.launcher.bind(event, lambda e: self.toggle_panel())
        self.root.bind("<F1>", lambda e: self.toggle_panel())
        self.root.bind("<Escape>", lambda e: self.close() if self.card else None, add="+")
        self.root.bind("<Configure>", self._on_configure, add="+")
        self.root.bind("<ButtonPress-1>", self._click_outside, add="+")
        if self.motion and not self.hidden:
            self.root.after(1500, self.launcher.wave)  # one hello per session, no tutorial

    # ------------------------------------------------------------ look

    def restyle(self) -> None:
        """Called by App.apply_theme: colours and styles follow day, night and simple view."""
        style, c = ttk.Style(self.root), self.app.colors
        self.bg = style.lookup("TFrame", "background") or self.root.cget("bg")
        self.accent = c.get("accent", c["active"])
        self.launcher.configure(bg=self.bg, highlightbackground=self.bg, highlightcolor=self.accent)
        style.configure("HelperTitle.TLabel", font=("Segoe UI Semibold", 11))
        style.configure("HelperOk.TLabel", foreground=c["ok"])
        style.configure("HelperItem.TButton", anchor="w")
        if self.run:
            self._show_step()
        elif self.card:
            self._show_panel(self.card_page)

    def _new_card(self) -> ttk.Frame:
        self._clear()
        self.card = tk.Frame(self.root, name="helper_card", bg=self.accent, padx=self.app.px(2),
                             pady=self.app.px(2))
        inner = ttk.Frame(self.card, padding=self.app.px(12))
        inner.pack(fill="both", expand=True)
        return inner

    def _button(self, parent, text: str, command, style: str = "TButton") -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style=style)
        for key in ("<Return>", "<KP_Enter>"):
            button.bind(key, lambda e: button.invoke())
        return button

    def _clear(self) -> None:
        for widget in [self.card, *self.ring]:
            if widget is not None:
                widget.destroy()
        self.card, self.ring = None, []

    # ------------------------------------------------------------ panel

    def toggle_panel(self) -> None:
        if self.card and not self.run:
            self.close()
        else:
            self.open_panel()

    def open_panel(self, page=None, note: str = "") -> None:
        if not self.card:
            self.return_focus = self.root.focus_get()
        self.run = None
        self._show_panel(page, note)
        self.launcher.wave()

    def _show_panel(self, page=None, note: str = "") -> None:
        """page: None for the tutorial list, or a tutorial with topics to choose from."""
        px, wrap = self.app.px, self.app.px(270)
        inner = self._new_card()
        self.card_page = page
        head = ttk.Frame(inner)
        head.pack(fill="x", pady=(0, px(8)))
        Mascot(head, px(30) / Mascot.H, self.bg).pack(side="left", padx=(0, px(8)))
        items = ttk.Frame(inner)
        if page is None:
            ttk.Label(head, text="Hi! What can I show you?", style="HelperTitle.TLabel").pack(anchor="w")
            ttk.Label(head, text="Pick a topic. I only point and explain; nothing is processed or saved.",
                      style="Muted.TLabel", wraplength=wrap, justify="left").pack(anchor="w")
            for tutorial in TUTORIALS:
                more = "  ›" if tutorial.get("topics") else ""
                tick = "  ✓" if tutorial["id"] in self.done else ""
                self._button(items, tutorial["title"] + more + tick, lambda t=tutorial: self._choose(t),
                             "HelperItem.TButton").pack(fill="x", pady=px(1))
        else:
            ttk.Label(head, text=page["title"], style="HelperTitle.TLabel").pack(anchor="w")
            ttk.Label(head, text="Watch every topic, or pick just one.", style="Muted.TLabel",
                      wraplength=wrap, justify="left").pack(anchor="w")
            self._button(items, f"Show me how (all {len(page['topics'])} topics)", lambda: self.start(page),
                         "Primary.TButton").pack(fill="x", pady=(0, px(4)))
            for n, topic in enumerate(page["topics"], 1):
                tick = "  ✓" if (page["id"], topic["id"]) in self.done else ""
                self._button(items, f"{n}. {topic['title']}{tick}", lambda t=topic: self.start(page, t["id"]),
                             "HelperItem.TButton").pack(fill="x", pady=px(1))
        if note:
            ttk.Label(inner, text=note, style="HelperOk.TLabel", wraplength=wrap, justify="left"
                      ).pack(anchor="w", pady=(0, px(6)))
        items.pack(fill="x")
        bottom = ttk.Frame(inner)
        bottom.pack(fill="x", pady=(px(10), 0))
        if page is not None:
            self._button(bottom, "‹ All tutorials", lambda: self._show_panel()).pack(side="left")
        elif self.hidden:
            self._button(bottom, "Show the ? button", lambda: self.set_hidden(False)).pack(side="left")
        else:
            self._button(bottom, "Hide me", self._hide_from_panel).pack(side="left")
        self._button(bottom, "Close", self.close).pack(side="right")
        self._place_panel()
        first = items.winfo_children()
        (first[0] if first else self.card).focus_set()

    def _choose(self, tutorial: dict) -> None:
        if tutorial.get("topics"):
            self._show_panel(tutorial)
        else:
            self.start(tutorial)

    def _place_panel(self) -> None:
        self.card.update_idletasks()
        px, root = self.app.px, self.root
        cw, ch = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        win_w, win_h = root.winfo_width(), root.winfo_height()
        if self.launcher.winfo_viewable():
            right = self.launcher.winfo_rootx() - root.winfo_rootx() + self.launcher.winfo_width()
            top = self.launcher.winfo_rooty() - root.winfo_rooty() + self.launcher.winfo_height() + px(4)
        else:
            right, top = win_w - px(14), px(56)
        x = max(min(right - cw, win_w - cw - px(6)), px(6))
        y = max(min(top, win_h - ch - px(6)), 0)
        self.card.place(x=x, y=y)
        self.card.lift()

    def _hide_from_panel(self) -> None:
        self.set_hidden(True)
        self.close()
        messagebox.showinfo("Helper hidden", "The ? helper is hidden. Press F1, or tick “Show the ? help "
                            "button” in Settings…, to bring it back.", parent=self.root)

    def set_hidden(self, hidden: bool) -> None:
        """Hide or show the launcher and remember it in .env, like night mode. Only ever called from a
        click by the person."""
        self.hidden = hidden
        if hidden:
            self.launcher.grid_remove()
        else:
            self.launcher.grid()
        if self.card and not self.run:
            self._show_panel(self.card_page)
        try:
            set_key(pipeline.ENV_PATH, "HELPER_HIDDEN", "1" if hidden else "0", quote_mode="never")
        except OSError as exc:
            self.app.note("Could not remember the helper setting.", f"{type(exc).__name__}: {exc}")

    def close(self) -> None:
        self._clear()
        self.run = None
        focus = self.return_focus
        self.return_focus = None
        if self.launcher.winfo_viewable():
            self.launcher.focus_set()
        elif focus is not None and focus.winfo_exists():
            focus.focus_set()

    def _click_outside(self, event) -> None:
        if self.card is None or self.run:  # during a tutorial people may try the real controls
            return
        name = str(event.widget)
        if not (name.startswith(str(self.card)) or name.startswith(str(self.launcher))):
            self.close()

    # ------------------------------------------------------------ tutorial runner

    def start(self, tutorial: dict, topic_id: str | None = None) -> None:
        steps = steps_for(tutorial, topic_id, {"dnd": self.app.dnd})
        if not self.card:
            self.return_focus = self.root.focus_get()
        self.run = {"tutorial": tutorial, "topic": topic_id, "steps": steps, "index": 0}
        self._show_step()

    def go(self, delta: int) -> None:
        run = self.run
        run["index"] += delta
        if run["index"] < len(run["steps"]):
            self._show_step()
            return
        tutorial = run["tutorial"]  # finished
        self.done.add((tutorial["id"], run["topic"]) if run["topic"] else tutorial["id"])
        if tutorial.get("topics") and not run["topic"]:
            self.done.update((tutorial["id"], t["id"]) for t in tutorial["topics"])
        if tutorial.get("topics") and all((tutorial["id"], t["id"]) in self.done for t in tutorial["topics"]):
            self.done.add(tutorial["id"])
        self.run = None
        self._show_panel(tutorial if tutorial.get("topics") else None,
                         note=f"Done: {tutorial['title']}. Pick another topic, or Close.")

    def label(self, target_id: str) -> str:
        """The control's text as shown right now; icon-only buttons also get their name."""
        try:
            text = " ".join(str(self.app.targets[target_id].cget("text")).split())
        except tk.TclError:
            text = ""
        if len(text) <= 2:
            return f"{text} ({TARGETS[target_id]})" if text else TARGETS[target_id]
        return text

    def target_rect(self, target_id):
        """(x, y, w, h) inside the app window, or None when the control isn't visible there."""
        widget = self.app.targets.get(target_id)
        if widget is None or not widget.winfo_exists() or not widget.winfo_viewable():
            return None
        root = self.root
        x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        if w <= 1 or h <= 1 or x >= root.winfo_width() or y >= root.winfo_height():
            return None
        return x, y, w, h

    def _show_step(self) -> None:
        px, wrap = self.app.px, self.app.px(330)
        run = self.run
        index, steps = run["index"], run["steps"]
        where, step = steps[index]
        target = step["target"]
        self.root.update_idletasks()
        rect = self.target_rect(target) if target else None

        inner = self._new_card()
        head = ttk.Frame(inner)
        head.pack(fill="x", pady=(0, px(6)))
        Mascot(head, px(30) / Mascot.H, self.bg).pack(side="left", padx=(0, px(8)))
        ttk.Label(head, text=run["tutorial"]["title"], style="HelperTitle.TLabel").pack(anchor="w")
        position = f"Step {index + 1} of {len(steps)}"
        ttk.Label(head, text=f"{where}  ·  {position}" if where else position, style="Muted.TLabel",
                  wraplength=wrap - px(40), justify="left").pack(anchor="w")
        text = step["text"].format(label=f"“{self.label(target)}”" if target else "")
        ttk.Label(inner, text=text, wraplength=wrap, justify="left").pack(anchor="w")
        if target and rect is None:
            name = TARGETS[target]
            hint = step["missing"] or "It may be hidden in this view, or below the bottom of the window."
            ttk.Label(inner, text=f"Not on screen right now: {name}. {hint}", style="Warn.TLabel",
                      wraplength=wrap, justify="left").pack(anchor="w", pady=(px(6), 0))
        buttons = ttk.Frame(inner)
        buttons.pack(fill="x", pady=(px(10), 0))
        back = self._button(buttons, "‹ Back", lambda: self.go(-1))
        back.pack(side="left")
        if index == 0:
            back.state(["disabled"])
        last = index == len(steps) - 1
        nxt = self._button(buttons, "Finish" if last else "Next ›", lambda: self.go(1), "Primary.TButton")
        nxt.pack(side="left", padx=(px(6), 0))
        self._button(buttons, "Close", self.close).pack(side="right")
        self._place_step(rect)
        nxt.focus_set()

    def _place_step(self, rect) -> None:
        px, root = self.app.px, self.root
        for widget in self.ring:
            widget.destroy()
        self.ring = []
        if rect:
            x, y, w, h = rect
            t, g = max(2, px(3)), px(2)
            x, y, w, h = x - g - t, y - g - t, w + 2 * (g + t), h + 2 * (g + t)
            for n, (rx, ry, rw, rh) in enumerate(((x, y, w, t), (x, y + h - t, w, t),
                                                 (x, y, t, h), (x + w - t, y, t, h))):
                bar = tk.Frame(root, name=f"helper_ring{n}", bg=self.accent)
                bar.place(x=rx, y=ry, width=rw, height=rh)
                self.ring.append(bar)
            rect = (x, y, w, h)
        self.card.update_idletasks()
        size = (self.card.winfo_reqwidth(), self.card.winfo_reqheight())
        x, y = bubble_position((root.winfo_width(), root.winfo_height()), rect, size, px(10))
        self.card.place(x=x, y=y)
        self.card.lift()

    def _on_configure(self, event) -> None:
        """Window resized or controls moved: keep the ring and bubble beside their control."""
        if self.card is None or str(event.widget).startswith(".helper_") or self._layout_job:
            return
        self._layout_job = self.root.after_idle(self._relayout)

    def _relayout(self) -> None:
        self._layout_job = None
        if self.card is None:
            return
        if self.run:
            target = self.run["steps"][self.run["index"]][1]["target"]
            rect = self.target_rect(target) if target else None
            if target and (rect is None) != (not self.ring):  # appeared or disappeared: redraw the text too
                self._show_step()
            else:
                self._place_step(rect)
        else:
            self._place_panel()
