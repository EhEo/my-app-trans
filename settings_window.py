# 트레이에서 여는 설정 창 - 단축키는 Ctrl/Shift/Alt 체크박스 + 1자 키 조합으로 편집
"""트레이에서 여는 설정 창.

API 키 / 모델 / 목표 언어 / 단축키를 편집하고 저장한다.
단축키는 Ctrl·Shift·Alt 체크박스(멀티 선택) + 키 1자 입력으로 구성된다.
저장 시 'ctrl + shift + z' 형태로 직렬화된다(RegisterHotKey 는 좌/우를 구분하지
않으므로 통합 표기).
메인 스레드에서만 생성/사용할 것.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from config import LANGUAGES
from ui import font_family


def _parse_hotkey(hk: str) -> tuple[dict, str]:
    """기존 hotkey 문자열을 (modifier dict, 키 문자열) 로 파싱한다.

    좌/우 표기(left ctrl 등)는 통합 플래그로 접어 읽는다 — RegisterHotKey 가
    좌/우를 구분하지 않으므로 UI 도 통합 체크박스 하나로 표시한다.
    """
    state = {"ctrl": False, "shift": False, "alt": False}
    key = ""
    if not hk:
        return state, key
    parts = [p.strip() for p in hk.replace("+", " + ").split("+")]
    parts = [p.strip().lower() for p in parts if p.strip()]
    for p in parts:
        if p in ("ctrl", "control", "left ctrl", "right ctrl",
                 "lctrl", "rctrl", "leftctrl", "rightctrl"):
            state["ctrl"] = True
        elif p in ("shift", "left shift", "right shift",
                   "lshift", "rshift", "leftshift", "rightshift"):
            state["shift"] = True
        elif p in ("alt", "left alt", "right alt",
                   "lalt", "ralt", "leftalt", "rightalt"):
            state["alt"] = True
        else:
            key = p  # 마지막 비-modifier 토큰을 키로 채택
    return state, key


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: dict,
                 on_save: Callable[[dict], None]) -> None:
        self.root = root
        self.on_save = on_save

        win = tk.Toplevel(root)
        self.win = win
        win.title("번역 입력기 설정")
        win.geometry("440x430")
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
                row=row, column=0, sticky="nw", **pad)

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

        # --- 단축키 영역 ---
        label("단축키", 3)
        hk = tk.Frame(frm, bg="#ffffff")
        hk.grid(row=3, column=1, sticky="we", **pad)

        state, key = _parse_hotkey((cfg.get("hotkey") or "").lower())
        self.ctrl_var = tk.BooleanVar(value=state["ctrl"])
        self.shift_var = tk.BooleanVar(value=state["shift"])
        self.alt_var = tk.BooleanVar(value=state["alt"])

        def mod_row(text: str, var: tk.BooleanVar, r: int) -> None:
            tk.Checkbutton(hk, text=text, variable=var, bg="#ffffff",
                           activebackground="#ffffff", font=LBL).grid(
                row=r, column=0, columnspan=2, sticky="w")

        mod_row("Ctrl", self.ctrl_var, 0)
        mod_row("Shift", self.shift_var, 1)
        mod_row("Alt", self.alt_var, 2)

        # 키 1자 입력
        tk.Label(hk, text="키", font=LBL, bg="#ffffff",
                 width=6, anchor="w").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.key_char_var = tk.StringVar(value=key[:1] if len(key) == 1 else "")

        def _max1(P: str) -> bool:
            return len(P) <= 1

        vcmd = (win.register(_max1), "%P")
        key_entry = tk.Entry(hk, textvariable=self.key_char_var, width=4,
                             font=ENT, justify="center",
                             validate="key", validatecommand=vcmd)
        key_entry.grid(row=3, column=1, sticky="w", pady=(6, 0))
        tk.Label(hk, text="(글자 한 개 — 예: z, a, 1)",
                 fg="#9aa0a6", bg="#ffffff", font=HINT).grid(
            row=3, column=2, sticky="w", padx=4, pady=(6, 0))

        # 현재 조합 미리보기
        self.hk_preview = tk.Label(hk, text="", fg="#5f6368", bg="#ffffff",
                                    font=HINT)
        self.hk_preview.grid(row=4, column=0, columnspan=3, sticky="w",
                              pady=(4, 0))
        for v in (self.ctrl_var, self.shift_var, self.alt_var):
            v.trace_add("write", lambda *_: self._update_preview())
        self.key_char_var.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

        # 자동 감지 모드
        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto_mode", False)))
        tk.Checkbutton(frm, text="자동 감지 (입력란 클릭 시 자동 팝업)",
                       variable=self.auto_var, font=LBL, bg="#ffffff",
                       activebackground="#ffffff").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))

        self.msg = tk.Label(frm, text="", fg="#188038", bg="#ffffff", font=HINT)
        self.msg.grid(row=5, column=0, columnspan=2, sticky="w",
                       padx=10, pady=(6, 0))

        btns = tk.Frame(win, bg="#ffffff")
        btns.pack(side="bottom", fill="x", padx=12, pady=8)
        tk.Button(btns, text="저장", width=8, font=LBL,
                  command=self._save).pack(side="right")
        tk.Button(btns, text="닫기", width=8, font=LBL,
                  command=self.close).pack(side="right", padx=6)

        frm.columnconfigure(1, weight=1)
        win.lift()
        win.focus_force()

    def _build_hotkey(self) -> str:
        """체크박스 + 키 문자를 'ctrl + shift + z' 형태로 직렬화."""
        parts = []
        if self.ctrl_var.get():
            parts.append("ctrl")
        if self.shift_var.get():
            parts.append("shift")
        if self.alt_var.get():
            parts.append("alt")
        key = (self.key_char_var.get() or "").strip().lower()
        if key:
            parts.append(key)
        return " + ".join(parts)

    def _update_preview(self) -> None:
        hk = self._build_hotkey()
        self.hk_preview.configure(text=f"현재 조합: {hk}" if hk else "현재 조합: (비어있음)")

    def _save(self) -> None:
        hotkey = self._build_hotkey()
        key = (self.key_char_var.get() or "").strip()
        if not key:
            self.msg.configure(text="키 1글자를 입력해주세요.", fg="#c0392b")
            return
        new_cfg = {
            "openrouter_api_key": self.key_var.get().strip(),
            "model": self.model_var.get().strip(),
            "target_language": self.lang_var.get().strip(),
            "hotkey": hotkey,
            "auto_mode": self.auto_var.get(),
        }
        result = self.on_save(new_cfg)
        ok = bool(result) and "실패" not in result
        self.msg.configure(text=result or "저장되었습니다.",
                           fg="#2a8a2a" if ok else "#c0392b")

    def close(self) -> None:
        if self.win.winfo_exists():
            self.win.destroy()
