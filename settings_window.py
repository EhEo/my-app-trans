# 트레이에서 여는 설정 창 - 단축키는 Ctrl/Shift/Alt 키캡 토글 + 1자 키 조합으로 편집
"""트레이에서 여는 설정 창.

API 키 / 모델 / 목표 언어 / 단축키를 편집하고 저장한다.
단축키는 Ctrl·Shift·Alt 키캡 토글(멀티 선택) + 키 1자 입력으로 구성된다.
저장 시 'ctrl + shift + z' 형태로 직렬화된다(RegisterHotKey 는 좌/우를 구분하지
않으므로 통합 표기).
메인 스레드에서만 생성/사용할 것.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from config import LANGUAGES
from ui import (ACCENT, ACCENT_DARK, ACCENT_TINT, CARD, ERR, HAIRLINE, OK,
                OUTLINE, SURFACE, TEXT1, TEXT2, TEXT3, font_family)

PAD = 24        # 창 가장자리 여백(px)
ROW_GAP = 12    # 같은 섹션 안의 행 간격
LABEL_W = 88    # 왼쪽 라벨 열 최소 폭


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
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg=CARD)

        fam = font_family(root)
        self.fam = fam
        LBL = (fam, 9)
        ENT = (fam, 10)

        frm = tk.Frame(win, bg=CARD)
        frm.pack(fill="both", expand=True, padx=PAD, pady=(PAD - 4, 8))
        frm.columnconfigure(0, minsize=LABEL_W)
        frm.columnconfigure(1, weight=1)
        self._row = 0

        def section(text: str, first: bool = False) -> None:
            tk.Label(frm, text=text, font=LBL, bg=CARD, fg=TEXT3).grid(
                row=self._row, column=0, columnspan=2, sticky="w",
                pady=(0 if first else ROW_GAP, 8))
            self._row += 1

        def row(text: str, widget: tk.Widget, gap: int = ROW_GAP) -> None:
            tk.Label(frm, text=text, font=LBL, bg=CARD, fg=TEXT2).grid(
                row=self._row, column=0, sticky="w", pady=(0, gap))
            widget.grid(row=self._row, column=1, sticky="we", pady=(0, gap))
            self._row += 1

        # --- 연결 ---
        section("연결", first=True)
        self.key_var = tk.StringVar(value=cfg.get("openrouter_api_key", ""))
        row("API 키", self._field(frm, self.key_var, ENT, show="•"))
        self.model_var = tk.StringVar(value=cfg.get("model", ""))
        row("모델", self._field(frm, self.model_var, ENT))

        # --- 입력 ---
        section("입력")
        self.lang_var = tk.StringVar(value=cfg.get("target_language", "영어"))
        row("번역 언어", self._lang_picker(frm, ENT))

        state, key = _parse_hotkey((cfg.get("hotkey") or "").lower())
        self.ctrl_var = tk.BooleanVar(value=state["ctrl"])
        self.shift_var = tk.BooleanVar(value=state["shift"])
        self.alt_var = tk.BooleanVar(value=state["alt"])
        self.key_char_var = tk.StringVar(value=key[:1] if len(key) == 1 else "")
        row("단축키", self._hotkey_row(frm), gap=4)
        tk.Label(frm, text="글자 키 한 개 (예: z, a, 1)", font=LBL, bg=CARD,
                 fg=TEXT3).grid(row=self._row, column=1, sticky="w",
                                pady=(0, ROW_GAP))
        self._row += 1

        self.auto_var = tk.BooleanVar(value=bool(cfg.get("auto_mode", False)))
        row("자동 열기", tk.Checkbutton(
            frm, text="입력란을 클릭하면 열기 (실험적)", variable=self.auto_var,
            font=LBL, bg=CARD, fg=TEXT1, activebackground=CARD,
            activeforeground=TEXT1, selectcolor=CARD, bd=0,
            highlightthickness=0, anchor="w", cursor="hand2"), gap=0)

        # --- 하단: 결과 메시지 + 버튼 ---
        tk.Frame(win, bg=HAIRLINE, height=1).pack(fill="x", pady=(16, 0))
        foot = tk.Frame(win, bg=CARD)
        foot.pack(fill="x", padx=PAD, pady=16)
        self.msg = tk.Label(foot, text="", font=LBL, bg=CARD, fg=OK, anchor="w")
        self.msg.pack(side="left", fill="x", expand=True)
        btn = {"font": LBL, "relief": "flat", "bd": 0, "padx": 16, "pady": 6,
               "cursor": "hand2", "highlightthickness": 0}
        tk.Button(foot, text="저장", command=self._save, bg=ACCENT, fg="#ffffff",
                  activebackground=ACCENT_DARK, activeforeground="#ffffff",
                  **btn).pack(side="right")
        tk.Button(foot, text="닫기", command=self.close, bg=SURFACE, fg=TEXT1,
                  activebackground=HAIRLINE, activeforeground=TEXT1,
                  **btn).pack(side="right", padx=(0, 8))

        for v in (self.ctrl_var, self.shift_var, self.alt_var):
            v.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

        win.lift()
        win.focus_force()

    # --- 위젯 빌더 ---
    @staticmethod
    def _bordered(parent: tk.Misc) -> tk.Frame:
        """헤어라인 테두리 상자. 안쪽 위젯이 포커스를 받으면 테두리가 강조색이 된다."""
        return tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=OUTLINE, highlightcolor=OUTLINE)

    @staticmethod
    def _focus_ring(box: tk.Frame, widget: tk.Widget) -> None:
        widget.bind("<FocusIn>", lambda e: box.configure(highlightbackground=ACCENT),
                    add="+")
        widget.bind("<FocusOut>", lambda e: box.configure(highlightbackground=OUTLINE),
                    add="+")

    def _field(self, parent: tk.Misc, var: tk.StringVar, font, **kw) -> tk.Frame:
        """평면 입력칸(테두리 상자 + 안쪽 여백 8px + 포커스 링)."""
        box = self._bordered(parent)
        ent = tk.Entry(box, textvariable=var, font=font, relief="flat", bd=0,
                       bg=CARD, fg=TEXT1, insertbackground=TEXT1,
                       highlightthickness=0, width=30, **kw)
        ent.pack(fill="x", padx=8, pady=6)
        self._focus_ring(box, ent)
        return box

    def _lang_picker(self, parent: tk.Misc, font) -> tk.Frame:
        """입력칸 모양의 언어 선택 — 팝업의 언어 메뉴와 같은 방식(라디오 메뉴)."""
        box = self._bordered(parent)
        mb = tk.Menubutton(box, textvariable=self.lang_var, font=font, anchor="w",
                           relief="flat", bd=0, bg=CARD, fg=TEXT1,
                           activebackground=CARD, activeforeground=TEXT1,
                           padx=8, pady=6, cursor="hand2", takefocus=1)
        menu = tk.Menu(mb, tearoff=0, font=font)
        for lang in LANGUAGES:
            menu.add_radiobutton(label=lang, variable=self.lang_var, value=lang)
        mb.configure(menu=menu)
        arrow = tk.Label(box, text="▾", font=font, bg=CARD, fg=TEXT3, cursor="hand2")
        arrow.pack(side="right", padx=(0, 8))
        # post() 는 grab 을 잡지 않아 창이 포커스를 잃으면 메뉴가 화면에 남을 수 있다
        # (3d3223d 의 고아 메뉴와 같은 유형) → tk_popup 으로 연다.
        arrow.bind("<Button-1>", lambda e: menu.tk_popup(
            mb.winfo_rootx(), mb.winfo_rooty() + mb.winfo_height()))
        mb.pack(side="left", fill="x", expand=True)
        return box

    def _hotkey_row(self, parent: tk.Misc) -> tk.Frame:
        """[Ctrl] + [Shift] + [Alt] + [z] — 켜진 수식키는 강조색 키캡으로 보인다."""
        rowf = tk.Frame(parent, bg=CARD)
        self._mod_btns: list[tuple[tk.Checkbutton, tk.BooleanVar]] = []
        for text, var in (("Ctrl", self.ctrl_var), ("Shift", self.shift_var),
                          ("Alt", self.alt_var)):
            b = tk.Checkbutton(rowf, text=text, variable=var, indicatoron=False,
                               font=(self.fam, 9), bd=0, padx=12, pady=4,
                               bg=SURFACE, selectcolor=ACCENT_TINT,
                               activebackground=SURFACE, highlightthickness=1,
                               cursor="hand2")
            b.pack(side="left")
            tk.Label(rowf, text="+", font=(self.fam, 9), bg=CARD,
                     fg=TEXT3).pack(side="left", padx=6)
            self._mod_btns.append((b, var))

        def _max1(P: str) -> bool:
            return len(P) <= 1

        # 키 입력칸은 옆 키캡과 같은 높이(9pt + 위아래 4px + 테두리 1px)로 맞춘다.
        box = self._bordered(rowf)
        ent = tk.Entry(box, textvariable=self.key_char_var, width=3,
                       font=(self.fam, 9), justify="center", relief="flat", bd=0,
                       bg=CARD, fg=TEXT1, insertbackground=TEXT1,
                       highlightthickness=0, validate="key",
                       validatecommand=(self.win.register(_max1), "%P"))
        ent.pack(padx=4, pady=4)
        self._focus_ring(box, ent)
        box.pack(side="left")
        return rowf

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
        """수식키 키캡의 켜짐/꺼짐을 글자색·테두리로 보여준다."""
        for b, var in self._mod_btns:
            on = var.get()
            b.configure(fg=ACCENT_DARK if on else TEXT2,
                        activeforeground=ACCENT_DARK if on else TEXT2,
                        highlightbackground=ACCENT if on else HAIRLINE,
                        highlightcolor=ACCENT if on else HAIRLINE)

    def _save(self) -> None:
        hotkey = self._build_hotkey()
        key = (self.key_char_var.get() or "").strip()
        if not key:
            self.msg.configure(text="단축키 글자를 입력해주세요.", fg=ERR)
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
        self.msg.configure(text=result or "저장되었습니다.", fg=OK if ok else ERR)

    def close(self) -> None:
        if self.win.winfo_exists():
            self.win.destroy()
