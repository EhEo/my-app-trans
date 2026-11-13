"""UI 공통 유틸 — 글꼴 선택, 색 토큰, 키캡 위젯.

글꼴: Pretendard(설치 시) → Noto Sans KR → Segoe UI 순으로 사용. 한 번 찾으면 캐시.
색: 회색 램프 하나에서 표면·선·텍스트를 뽑고, 강조색은 트레이 아이콘의 파랑 하나만 쓴다.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

_PREFERRED = ("Pretendard", "Noto Sans KR", "Segoe UI")
_cached: str | None = None

# --- 색 토큰 (라이트) ---
CARD = "#ffffff"         # 카드·창 바탕
SURFACE = "#f4f4f2"      # 키캡, 꺼진 토글 바탕
HAIRLINE = "#e2e2de"     # 구분선, 입력칸 테두리
OUTLINE = "#cfcfca"      # 화면 위에 떠 있는 카드의 외곽선
TEXT1 = "#1f1f1e"        # 본문
TEXT2 = "#575753"        # 라벨·보조
TEXT3 = "#73736f"        # 안내·흐린 글자 (흰 바탕 대비 4.6:1)
ACCENT = "#1a73e8"       # 주 동작·선택·목표 언어 (트레이 아이콘 색)
ACCENT_DARK = "#1765cc"  # 주 버튼 눌림
ACCENT_TINT = "#e8f0fe"  # 켜진 토글 바탕
ERR = "#c5221f"
OK = "#188038"


def font_family(root=None) -> str:
    global _cached
    if _cached:
        return _cached
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    for fam in _PREFERRED:
        if fam in fams:
            _cached = fam
            return fam
    _cached = "Segoe UI"
    return _cached


def keycap(parent: tk.Misc, text: str, fam: str) -> tk.Label:
    """단축키를 키보드 키 모양으로 보여주는 작은 라벨 (이 앱의 시그니처 요소)."""
    return tk.Label(parent, text=text, font=(fam, 8), fg=TEXT2, bg=SURFACE,
                    padx=4, pady=0, bd=0, highlightthickness=1,
                    highlightbackground=HAIRLINE, highlightcolor=HAIRLINE)
