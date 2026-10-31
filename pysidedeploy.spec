[app]
title = DevStorageManager
project_dir = .
input_file = app.py
exec_directory = build
project_file =
icon =

[python]
python_path = .venv/Scripts/python.exe
packages = Nuitka==2.7.11

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Widgets
plugins = platforms,styles,imageformats

[nuitka]
mode = standalone
extra_args = --noinclude-qt-translations --windows-console-mode=disable --include-package=dev_storage_manager --include-module=win32timezone --assume-yes-for-downloads
