"""설정 파일 로드/저장.

설정은 %APPDATA%\\my-app-trans\\config.json 에 저장된다.
API 키가 코드/깃 저장소에 들어가지 않도록 앱 디렉터리 밖(APPDATA)에 둔다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "my-app-trans"

DEFAULTS = {
    "openrouter_api_key": "",
    "model": "google/gemini-2.5-flash-lite",
    "target_language": "영어",
    "hotkey": "ctrl+shift+z",
    "auto_mode": False,
}

# 목표 언어 한글 라벨 -> 번역 프롬프트용 영어 이름
LANGUAGES = {
    "영어": "English",
    "중국어": "Chinese",
    "베트남어": "Vietnamese",
    "한국어": "Korean",
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config(path: Path | None = None) -> dict:
    """설정을 읽어 반환한다. 파일이 없으면 기본값으로 생성한다.

    누락된 키는 기본값으로 채워서 항상 완전한 dict를 돌려준다.
    """
    p = Path(path) if path is not None else config_path()
    if not p.exists():
        save_config(DEFAULTS.copy(), p)
        return DEFAULTS.copy()

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
    except (json.JSONDecodeError, ValueError, OSError):
        # 손상된 파일은 기본값으로 덮어쓰지 않고, 기본값을 메모리상으로만 사용
        return DEFAULTS.copy()

    merged = DEFAULTS.copy()
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_config(cfg: dict, path: Path | None = None) -> None:
    p = Path(path) if path is not None else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
