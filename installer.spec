# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — 번역입력기 설치 프로그램.

앱 본체(dist/번역입력기.exe)를 데이터로 포함하는 단일 설치 exe를 만든다.
먼저 build_exe.spec 로 앱 본체를 빌드한 뒤 이 스펙을 빌드할 것.

    python -m PyInstaller build_exe.spec --noconfirm
    python -m PyInstaller installer.spec --noconfirm
산출물: dist/번역입력기_설치.exe

키 포함 설치 파일(설치 직후 바로 사용): 환경변수 TRANS_EMBED_KEY=1 로 빌드하면
이 PC 의 %APPDATA%\\my-app-trans\\config.json 에서 API 키·모델을 읽어
build/seed_config.json(git 제외)으로 만들어 함께 넣는다.
산출물: dist/번역입력기_설치_키포함.exe — 이 파일을 가진 사람은 키를 꺼낼 수 있으니
외부에 공유하지 말 것.
"""
import json
import os

block_cipher = None

# 앱 본체를 설치 exe 안에 포함(번들 루트에 풀림)
datas = [('dist/번역입력기.exe', '.')]
installer_name = '번역입력기_설치'
if os.environ.get('TRANS_EMBED_KEY') == '1':
    _cfg_file = os.path.join(os.environ['APPDATA'], 'my-app-trans', 'config.json')
    with open(_cfg_file, encoding='utf-8') as f:
        _cfg = json.load(f)
    _seed = {k: _cfg[k] for k in ('openrouter_api_key', 'model') if _cfg.get(k)}
    if not _seed.get('openrouter_api_key'):
        raise SystemExit(f'TRANS_EMBED_KEY=1 이지만 {_cfg_file} 에 API 키가 없습니다.')
    os.makedirs('build', exist_ok=True)
    _seed_file = os.path.join('build', 'seed_config.json')
    with open(_seed_file, 'w', encoding='utf-8') as f:
        json.dump(_seed, f, ensure_ascii=False)
    datas.append((_seed_file, '.'))
    installer_name = '번역입력기_설치_키포함'

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name=installer_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 패킹은 Defender ML 오탐의 주원인 — 끔
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
