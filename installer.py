"""번역입력기 설치 프로그램.

이 exe 안에 포함된 앱 본체(번역입력기.exe)를 현재 사용자 폴더에 복사하고,
바탕화면과 시작프로그램(Startup) 폴더에 '번역입력기' 바로가기를 만든다.

- 관리자 권한 불필요: 모든 작업을 현재 사용자 영역에서 수행한다.
- 시작프로그램 폴더 바로가기 → Windows 로그인 시 자동 실행.

환경변수 TRANS_INSTALL_SILENT=1 이면 메시지박스/자동실행 없이 조용히 설치한다
(자동 검증용). 성공 시 종료코드 0, 실패 시 1.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
from pathlib import Path

from config import config_path, load_config, save_config

APP_EXE = "번역입력기.exe"
SHORTCUT_NAME = "번역입력기"          # 바로가기 이름(.lnk 제외)
INSTALL_SUBDIR = "번역입력기"          # %LOCALAPPDATA%\Programs\<여기>

SILENT = os.environ.get("TRANS_INSTALL_SILENT") == "1"


def msgbox(text: str, icon: int = 0x40) -> None:
    """안내 메시지박스. icon: 0x40=정보, 0x10=오류, 0x30=경고."""
    if SILENT:
        return
    # 0x10000=MB_SETFOREGROUND, 0x40000=MB_TOPMOST
    ctypes.windll.user32.MessageBoxW(0, text, "번역입력기 설치",
                                     icon | 0x10000 | 0x40000)


def resource_path(name: str) -> str:
    """번들된 리소스 경로. PyInstaller onefile 은 sys._MEIPASS 에 풀린다.

    개발 중(비동결) 에는 dist\\ 아래의 빌드 산출물을 사용한다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", name)


def apply_seed(seed_file: Path, cfg_file: Path | None = None) -> str:
    """번들된 초기 설정(seed_config.json: API 키·모델)을 사용자 설정에 적용한다.

    설정이 없거나 API 키가 비어 있을 때만 적용하고, 이미 키가 있으면 절대 덮어쓰지
    않는다. 키 포함 설치 파일(installer.spec + TRANS_EMBED_KEY=1)에서만 seed 가 있다.
    결과 안내문을 돌려준다(적용할 seed 가 없으면 빈 문자열).
    """
    try:
        seed = json.loads(Path(seed_file).read_text(encoding="utf-8"))
        if not isinstance(seed, dict) or not seed.get("openrouter_api_key"):
            return ""
    except (OSError, ValueError):
        return ""
    p = Path(cfg_file) if cfg_file is not None else config_path()
    cfg = load_config(p)  # 없으면 기본값으로 생성
    if cfg.get("openrouter_api_key"):
        return "기존 설정(API 키)을 그대로 유지했습니다."
    cfg.update({k: v for k, v in seed.items() if k in cfg and v})
    save_config(cfg, p)
    return "API 키가 미리 설정되어 있어 바로 사용할 수 있습니다."


def _special_folder(shell, key: str, fallback: str) -> str:
    """WScript.Shell 의 특수폴더 경로(OneDrive 리디렉션 등 반영). 실패 시 fallback."""
    try:
        p = str(shell.SpecialFolders(key))
        if p:
            return p
    except Exception:
        pass
    return fallback


def _create_shortcut(shell, lnk_path: Path, target: Path, workdir: Path) -> None:
    sc = shell.CreateShortcut(str(lnk_path))
    sc.TargetPath = str(target)
    sc.WorkingDirectory = str(workdir)
    sc.IconLocation = f"{target},0"
    sc.Description = SHORTCUT_NAME
    sc.Save()


def main() -> int:
    if os.name != "nt":
        msgbox("이 설치 프로그램은 Windows 전용입니다.", icon=0x10)
        return 1

    # 1) 앱 본체 복사
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    install_dir = local / "Programs" / INSTALL_SUBDIR
    install_dir.mkdir(parents=True, exist_ok=True)
    dst = install_dir / APP_EXE
    try:
        shutil.copy2(resource_path(APP_EXE), dst)
    except PermissionError:
        msgbox("앱이 실행 중인 것 같습니다.\n트레이에서 '종료' 후 다시 설치해주세요.",
               icon=0x30)
        return 1
    except OSError as e:
        msgbox(f"파일 복사 실패:\n{e}", icon=0x10)
        return 1

    # 2) 바로가기 생성 (바탕화면 + 시작프로그램)
    import comtypes.client
    shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)

    desktop = Path(_special_folder(
        shell, "Desktop",
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")))
    startup = Path(_special_folder(
        shell, "Startup",
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs\Startup")))

    made = []
    for folder in (desktop, startup):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _create_shortcut(shell, folder / f"{SHORTCUT_NAME}.lnk",
                             dst, install_dir)
            made.append(str(folder / f"{SHORTCUT_NAME}.lnk"))
        except Exception as e:  # 한쪽 실패해도 설치 자체는 진행
            print(f"[경고] 바로가기 생성 실패({folder}): {e}", flush=True)

    # 3) 키 포함 설치 파일이면 초기 설정(API 키) 적용 — 기존 키는 덮어쓰지 않음
    seed_msg = apply_seed(Path(resource_path("seed_config.json")))

    print(f"설치 위치: {dst}", flush=True)
    for m in made:
        print(f"바로가기: {m}", flush=True)
    if seed_msg:
        print(f"설정: {seed_msg}", flush=True)

    msgbox(
        f"설치가 완료되었습니다.\n\n"
        f"설치 위치:\n{dst}\n\n"
        f"바탕화면 바로가기와 시작프로그램(로그인 시 자동 실행) 등록 완료.\n"
        + (f"{seed_msg}\n" if seed_msg else "")
        + "\n지금 실행하려면 바탕화면의 '번역입력기' 바로가기를 더블클릭하세요.",
        icon=0x40,
    )

    # 설치 직후 자동실행은 하지 않는다. "설치기가 끝나며 다른 exe 를 바로 실행"
    # 하는 동작은 멀웨어 드로퍼의 전형적 시그니처라 백신 오탐(Bearfoos.A!ml 등)을
    # 키운다. 사용자가 바로가기로 직접 첫 실행하도록 안내만 한다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
