# PyInstaller fallback after pyside6-deploy/Nuitka installation failed on long paths.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / 'app.py')], pathex=[str(root / 'src')],
             binaries=[], datas=[],
             hiddenimports=['win32timezone', 'send2trash.win.IFileOperationProgressSink'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore'],
             noarchive=False)
# Widgets app: avoid bundling unrelated QML/PDF/virtual-keyboard plugins.
qt_dlls = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll'}
qt_plugins = {'qwindows.dll', 'qoffscreen.dll', 'qminimal.dll', 'qmodernwindowsstyle.dll', 'qwindowsvistastyle.dll'}
filtered = []
for entry in a.binaries:
    destination = entry[0].replace('\\', '/')
    name = Path(destination).name.lower()
    if destination.startswith('PySide6/plugins/') and name not in qt_plugins:
        continue
    if name.startswith('qt6') and name.endswith('.dll') and name not in qt_dlls:
        continue
    if name == 'opengl32sw.dll':
        continue
    filtered.append(entry)
a.binaries = filtered
# Qt uses Windows' system ICU ABI. Never bundle an unrelated runtime's ICU.
for destination, source, kind in a.binaries:
    if Path(destination).name.lower() == 'icuuc.dll' and 'system32' not in str(source).lower():
        raise RuntimeError('Unrelated ICU DLL found. Build with scripts/build_windows.py and its isolated PATH.')
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='DevStorageManager', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False,
          uac_admin=False)
collect = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DevStorageManager')
