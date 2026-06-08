"""트레이에서 여는 설정 창.

API 키 / 모델 / 목표 언어 / 단축키를 편집하고 저장한다.
메인 스레드에서만 생성/사용할 것.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from config import LANGUAGES
from ui import font_family


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: dict,
                 on_save: Callable[[dict], None]) -> None:
        self.root = root
        self.on_save = on_save

        win = tk.Toplevel(root)
        self.win = win
        win.title("번역 입력기 설정")
        win.geometry("420x320")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#ffffff")

        fam = font_family(root)
        LBL = (fam, 9)
        ENT = (fam, 9)
        HINT = (fam, 8)
        pad = {"padx": 10, "pady": 3}
        frm = tk.Frame(win, bg="#ffffff")
        frm.pack(fill="both", expand=True, padx=8, pady=6)

        def label(text, row):
            tk.Label(frm, text=text, font=LBL, bg="#ffffff", fg="#202124").grid(
                row=row, column=0, sticky="w", **pad)

        label("OpenRouter API 키", 0)
        self.key_var = tk.StringVar(value=cfg.get("openrouter_api_key", ""))
        tk.Entry(frm, textvariable=self.key_var, width=32, show="•",
                 font=ENT).grid(row=0, column=1, sticky="we", **pad)

        label("모델", 1)
        self.model_var = tk.StringVar(value=cfg.get("model", ""))
        tk.Entry(frm, textvariable=self.model_var, width=32, font=ENT).grid(
            row=1, column=1, sticky="we", **pad)

        label("목표 언어", 2)
        self.lang_var = tk.StringVar(value=cfg.get("target_language", "영어"))
        ttk.Combobox(frm, textvariable=self.lang_var,
                     values=list(LANGUAGES.keys()), state="readonly",
                     width=30).grid(row=2, column=1, sticky="we", **pad)

        label("단축키", 3)
        self.hotkey_var = tk.StringVar(value=cfg.get("hotkey", "ctrl+shift+z"))
        tk.Entry(frm, textvariable=self.hotkey_var, width=32, font=ENT).grid(
            row=3, column=1, sticky="we", **pad)
        tk.Label(frm, text="예: ctrl+shift+z", fg="#9aa0a6", bg="#ffffff",
                 font=HINT).grid(row=4, column=1, sticky="w", padx=10)

        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto_mode", False)))
        tk.Checkbutton(frm, text="자동 감지 (입력란 클릭 시 자동 팝업)",
                       variable=self.auto_var, font=LBL, bg="#ffffff",
                       activebackground="#ffffff").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))

        self.msg = tk.Label(frm, text="", fg="#188038", bg="#ffffff", font=HINT)
        self.msg.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))

        btns = tk.Frame(win, bg="#ffffff")
        btns.pack(side="bottom", fill="x", padx=12, pady=8)
        tk.Button(btns, text="저장", width=8, font=LBL,
                  command=self._save).pack(side="right")
        tk.Button(btns, text="닫기", width=8, font=LBL,
                  command=self.close).pack(side="right", padx=6)

        frm.columnconfigure(1, weight=1)
        win.lift()
        win.focus_force()

    def _save(self) -> None:
        new_cfg = {
            "openrouter_api_key": self.key_var.get().strip(),
            "model": self.model_var.get().strip(),
            "target_language": self.lang_var.get().strip(),
            "hotkey": self.hotkey_var.get().strip().lower(),
            "auto_mode": self.auto_var.get(),
        }
        result = self.on_save(new_cfg)
        ok = bool(result) and "실패" not in result
        self.msg.configure(text=result or "저장되었습니다.",
                           fg="#2a8a2a" if ok else "#c0392b")

    def close(self) -> None:
        if self.win.winfo_exists():
            self.win.destroy()
