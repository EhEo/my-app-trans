# 팝업에서 Shift+Tab 으로 목표 언어를 순서대로 바꾸는 동작 검증
import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from popup import Popup  # noqa: E402

LANGS = ["영어", "중국어", "베트남어", "한국어"]


class TestLanguageCycle(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.changes: list[str] = []

    def tearDown(self) -> None:
        self.root.destroy()

    def make(self, language: str, languages=LANGS) -> Popup:
        return Popup(self.root, on_submit=lambda t: None, languages=languages,
                     language=language, on_language_change=self.changes.append)

    def test_shift_tab_is_bound_on_input(self):
        p = self.make("영어")
        self.assertTrue(p.text.bind("<Shift-Tab>"))

    def test_cycles_forward_and_wraps(self):
        p = self.make("베트남어")
        for _ in range(3):
            self.assertEqual(p._cycle_language(), "break")
        self.assertEqual(self.changes, ["한국어", "영어", "중국어"])
        assert p._lang_btn is not None
        self.assertEqual(p._lang_btn.cget("text"), "중국어로 ▾")
        self.assertEqual(p._lang_var.get(), "중국어")

    def test_does_not_insert_text(self):
        p = self.make("영어")
        p.text.insert("1.0", "안녕")
        p._cycle_language()
        self.assertEqual(p.text.get("1.0", "end-1c"), "안녕")

    def test_ignored_while_translating(self):
        p = self.make("영어")
        p.text.insert("1.0", "안녕")
        p._submit()
        p._cycle_language()
        self.assertEqual(self.changes, [])

    def test_no_languages_is_noop(self):
        p = self.make("", languages=None)
        self.assertEqual(p._cycle_language(), "break")
        self.assertEqual(self.changes, [])


if __name__ == "__main__":
    unittest.main()
