"""The "?" helper: tutorial definitions, placement, navigation, and that it never acts. No Gemini calls."""
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import gui
import helper
import pipeline
from tutorials import TARGETS, TUTORIALS


def all_steps():
    for tutorial in TUTORIALS:
        for topic in tutorial.get("topics", [{"steps": tutorial.get("steps", [])}]):
            yield from topic["steps"]


class PlacementTests(unittest.TestCase):
    def test_bubble_goes_beside_the_target_without_covering_it(self):
        win, size = (1000, 700), (300, 150)
        self.assertEqual(helper.bubble_position(win, (50, 100, 80, 30), size, 10), (50, 140))  # below
        self.assertEqual(helper.bubble_position(win, (50, 600, 80, 30), size, 10), (50, 440))  # above
        x, y = helper.bubble_position(win, (900, 300, 90, 30), size, 10)  # near the right edge
        self.assertLessEqual(x + 300, 1000)
        # A target filling most of the window: stays inside the window, in the least covering spot.
        x, y = helper.bubble_position(win, (0, 100, 1000, 500), size, 10)
        self.assertTrue(0 <= x <= 700 and 0 <= y <= 550)
        self.assertEqual(helper.bubble_position((200, 100), (0, 0, 10, 10), size, 10), (0, 0))  # tiny window

    def test_steps_respect_flags_and_topics(self):
        add = next(t for t in TUTORIALS if t["id"] == "add")
        self.assertEqual(len(helper.steps_for(add, flags={"dnd": True})),
                         len(helper.steps_for(add, flags={"dnd": False})) + 1)
        review = next(t for t in TUTORIALS if t["id"] == "review")
        whole = helper.steps_for(review)
        self.assertTrue(whole[0][0].startswith("Topic 1 of 4"))
        one = helper.steps_for(review, "check")
        self.assertEqual([w for w, _ in one], ["Checking against the PDF"] * 2)


class HelperAppTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = gui.TkinterDnD.Tk() if gui.TkinterDnD else tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.tmp = Path(tempfile.mkdtemp(prefix="tnocr helper "))
        env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key", "NIGHT_MODE": "0", "SIMPLE_VIEW": "0",
                                           "HELPER_HIDDEN": "0"})
        env.start()
        self.addCleanup(env.stop)
        patches = [mock.patch.object(pipeline, "ENV_PATH", self.tmp / ".env"),
                   mock.patch.multiple(gui.messagebox, askyesno=mock.DEFAULT, showinfo=mock.DEFAULT,
                                       showwarning=mock.DEFAULT, showerror=mock.DEFAULT)]
        self.env_path = patches[0].start()
        self.boxes = patches[1].start()
        for p in patches:
            self.addCleanup(p.stop)
        self.app = gui.App(self.root, output_dir=self.tmp / "output")
        self.helper = self.app.helper
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def card_texts(self):
        texts = []
        stack = [self.helper.card]
        while stack:
            widget = stack.pop()
            stack += widget.winfo_children()
            try:
                texts.append(str(widget.cget("text")))
            except tk.TclError:
                pass
        return " | ".join(texts)

    def test_every_target_is_a_real_control_and_every_text_fits(self):
        self.assertEqual(set(TARGETS), set(self.app.targets))
        for step in all_steps():
            self.assertTrue(step["target"] is None or step["target"] in TARGETS, step)
            step["text"].format(label="x")  # no stray braces
        ids = [t["id"] for t in TUTORIALS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_open_close_reopen_with_mouse_and_keys(self):
        self.helper.launcher.event_generate("<Button-1>", x=5, y=5)
        self.root.update()
        self.assertIsNotNone(self.helper.card)
        self.assertIn("What can I show you?", self.card_texts())
        self.helper.toggle_panel()  # F1 again closes
        self.assertIsNone(self.helper.card)
        self.root.focus_force()  # key events go to the focused window
        self.root.update()
        self.root.event_generate("<F1>")
        self.assertIsNotNone(self.helper.card)
        self.root.event_generate("<Escape>")
        self.assertIsNone(self.helper.card)
        self.helper.open_panel()
        self.helper.open_panel(next(t for t in TUTORIALS if t["id"] == "save"))
        self.assertIn("Show me how (all 3 topics)", self.card_texts())

    def test_every_tutorial_and_topic_runs_to_the_end_without_doing_anything(self):
        forbidden = {name: mock.patch.object(pipeline, name, side_effect=AssertionError(name))
                     for name in ("run_batch", "make_client", "file_sha256")}
        forbidden["set_key"] = mock.patch.object(helper, "set_key", side_effect=AssertionError("set_key"))
        forbidden["gui_set_key"] = mock.patch.object(gui, "set_key", side_effect=AssertionError("set_key"))
        forbidden["thread"] = mock.patch.object(gui.threading, "Thread", side_effect=AssertionError("thread"))
        forbidden["open"] = mock.patch.object(gui, "open_path", side_effect=AssertionError("open"))
        forbidden["dialog"] = mock.patch.object(gui.filedialog, "askopenfilenames", side_effect=AssertionError)
        for patch in forbidden.values():
            patch.start()
            self.addCleanup(patch.stop)
        runs = [(t, None) for t in TUTORIALS] + [(t, s["id"]) for t in TUTORIALS for s in t.get("topics", [])]
        for tutorial, topic in runs:
            self.helper.start(tutorial, topic)
            total = len(self.helper.run["steps"])
            self.assertGreater(total, 0)
            self.assertIn(f"Step 1 of {total}", self.card_texts())
            if total > 1:
                self.helper.go(1)
                self.helper.go(-1)  # Back
                self.assertEqual(self.helper.run["index"], 0)
            for _ in range(total):
                self.helper.go(1)
            self.assertIsNone(self.helper.run)
            self.assertIn("Done:", self.card_texts())
        self.assertTrue({t["id"] for t in TUTORIALS} <= self.helper.done)
        self.helper.close()
        self.assertEqual((self.app.items, self.app.rows), ([], []))
        self.assertFalse((self.tmp / "output").exists())
        self.assertFalse(self.env_path.exists())
        for box in self.boxes.values():
            box.assert_not_called()

    def test_highlight_surrounds_the_control_and_follows_resizing(self):
        add = next(t for t in TUTORIALS if t["id"] == "add")
        self.helper.start(add)
        self.root.update()
        x, y, w, h = self.helper.target_rect("btn_choose")
        top, bottom, left, right = (bar.place_info() for bar in self.helper.ring)
        self.assertLess(int(top["x"]), x)
        self.assertLess(int(top["y"]), y)
        self.assertGreater(int(bottom["y"]), y + h - 1)
        card = self.helper.card
        cx, cy = card.winfo_x(), card.winfo_y()
        overlaps = cx < x + w and x < cx + card.winfo_width() and cy < y + h and y < cy + card.winfo_height()
        self.assertFalse(overlaps)

        self.root.geometry(f"{self.app.px(840)}x{self.app.px(620)}")
        self.root.update()
        self.helper._relayout()
        self.root.update()
        self.assertLessEqual(card.winfo_x() + card.winfo_width(), self.root.winfo_width())
        self.assertLessEqual(card.winfo_y() + card.winfo_height(), self.root.winfo_height())
        self.helper.close()
        self.assertEqual(self.helper.ring, [])
        self.assertFalse([c for c in self.root.winfo_children() if str(c).startswith(".helper_")])

    def test_hidden_controls_are_explained_not_highlighted(self):
        errors = next(t for t in TUTORIALS if t["id"] == "errors")
        self.helper.start(errors, "details")
        self.helper.go(1)  # the Details box: closed until "Show details" is clicked
        self.assertEqual(self.helper.ring, [])
        self.assertIn("Not on screen right now", self.card_texts())
        self.assertIn("Show details", self.card_texts())
        self.app.toggle_details()  # the person opens it: the step now points at it
        self.root.update()
        self.helper._relayout()
        self.assertEqual(len(self.helper.ring), 4)
        self.assertNotIn("Not on screen", self.card_texts())

        with mock.patch.object(gui, "set_key"):
            self.app.toggle_simple()  # radio buttons are classic-only
        save = next(t for t in TUTORIALS if t["id"] == "save")
        self.helper.start(save, "master")
        self.assertIn("Classic view", self.card_texts())
        self.assertEqual(self.helper.ring, [])

    def test_hiding_is_remembered_and_f1_still_works(self):
        self.helper.open_panel()
        self.helper._hide_from_panel()
        self.root.update()
        self.assertFalse(self.helper.launcher.winfo_ismapped())
        self.assertIn("HELPER_HIDDEN=1", self.env_path.read_text())
        self.boxes["showinfo"].assert_called_once()
        self.helper.toggle_panel()
        self.assertIn("Show the ? button", self.card_texts())
        self.helper.set_hidden(False)
        self.root.update()
        self.assertTrue(self.helper.launcher.winfo_ismapped())
        self.assertIn("HELPER_HIDDEN=0", self.env_path.read_text())

    def test_reduced_motion_turns_animation_off(self):
        self.root.destroy()
        self.root = gui.TkinterDnD.Tk() if gui.TkinterDnD else tk.Tk()
        with mock.patch.object(helper, "reduced_motion", return_value=True):
            app = gui.App(self.root, output_dir=self.tmp / "output")
        self.assertFalse(app.helper.launcher.animate)
        app.helper.launcher.wave()
        self.assertEqual(app.helper.launcher.jobs, [])


if __name__ == "__main__":
    unittest.main()
