# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — 트레이 상주 번역 입력기.

단일 파일(onefile), 콘솔 없음(windowed) 으로 빌드한다.
빌드: python -m PyInstaller build_exe.spec --noconfirm
산출물: dist/번역입력기.exe
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # 동적/플러그인 형태라 PyInstaller가 정적 분석으로 놓치기 쉬운 모듈들
    hiddenimports=[
        'pystray._win32',        # pystray Windows 백엔드
        'PIL._tkinter_finder',   # PIL <-> tkinter 연동
        'comtypes.stream',       # uiautomation 의존
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='번역입력기',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 패킹은 Defender ML 오탐(Bearfoos.A!ml 등)의 주원인 — 끔
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 트레이 상주 앱 — 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',        # 실행파일/작업표시줄 아이콘
)
