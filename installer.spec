# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — 번역입력기 설치 프로그램.

앱 본체(dist/번역입력기.exe)를 데이터로 포함하는 단일 설치 exe를 만든다.
먼저 build_exe.spec 로 앱 본체를 빌드한 뒤 이 스펙을 빌드할 것.

    python -m PyInstaller build_exe.spec --noconfirm
    python -m PyInstaller installer.spec --noconfirm
산출물: dist/번역입력기_설치.exe
"""

block_cipher = None

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    # 앱 본체를 설치 exe 안에 포함(번들 루트에 풀림)
    datas=[('dist/번역입력기.exe', '.')],
    hiddenimports=[
        'comtypes.client',   # 바로가기 생성(WScript.Shell)
        'comtypes.stream',
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
    name='번역입력기_설치',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)
