"""UI 공통 유틸 — 사용 가능한 최적 글꼴 선택.

Pretendard(설치 시) → Noto Sans KR → Segoe UI 순으로 사용. 한 번 찾으면 캐시.
"""
from __future__ import annotations

import tkinter.font as tkfont

_PREFERRED = ("Pretendard", "Noto Sans KR", "Segoe UI")
_cached: str | None = None


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
