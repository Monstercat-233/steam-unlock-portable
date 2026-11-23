# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（pywebview / WebView2 界面）。

路径全部相对 spec 自身所在目录推导，不写死盘符：
  ROOT      = 本 spec 所在目录（D:/STEAM入库/全自动入库_v2）
  SRC       = ROOT/src
  ICON      = SRC/app.ico（窗口/exe 图标）
  UIDIR     = SRC/ui（前端资源，main_app.py 用 paths.resource_dir() 定位）

pywebview 自带 PyInstaller hook（webview/__pyinstaller/hook-webview.py 收集
webview/lib 与 webview/js），hooks-contrib 的 hook-clr / hook-clr_loader 收
Python.Runtime.dll；hiddenimports 再兜底一次平台后端，避免 --windowed 下漏收。
界面 HTML 不是 Python 模块，必须显式 add-data 到 'ui' 子目录。
"""
import os

ROOT = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821 - SPEC 由 PyInstaller 注入
SRC = os.path.join(ROOT, 'src')
UIDIR = os.path.join(SRC, 'ui')
ICON = os.path.join(SRC, 'app.ico')

datas = [
    (os.path.join(SRC, 'depotkeys_master.json'), '.'),
    (os.path.join(SRC, 'crack_library.json'), '.'),
    (os.path.join(SRC, 'names.json'), '.'),
]
if os.path.isdir(UIDIR):
    datas.append((UIDIR, 'ui'))
if os.path.isfile(ICON):
    datas.append((ICON, '.'))

a = Analysis(
    [os.path.join(SRC, 'main_app.py')],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'clr_loader',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'ttkbootstrap', 'PIL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RukuCenter',
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
    icon=ICON if os.path.isfile(ICON) else None,
)
