#!/bin/bash
cd "$(dirname "$0")" || exit 1
rc=0
echo "--- py_compile ---"
PYFILES="main.py bobo-xcode \
engines/swift_engine.py engines/flutter_engine.py engines/react_native_engine.py \
engines/package_manager.py engines/lsp_server.py engines/__init__.py \
simulator/qemu_manager.py simulator/device_profiles.py simulator/touch_bridge.py simulator/__init__.py \
bridge/mac_connector.py bridge/signing_manager.py bridge/fastlane_runner.py \
bridge/project_packager.py bridge/appstore_uploader.py bridge/__init__.py \
ui/window.py ui/editor.py ui/file_tree.py ui/terminal.py ui/build_panel.py \
ui/simulator_panel.py ui/swift_preview.py ui/settings_dialog.py ui/__init__.py"
for f in $PYFILES; do
  if python3 -m py_compile "$f" 2>/tmp/xerr.txt; then echo "OK   $f"; else echo "FAIL $f"; cat /tmp/xerr.txt; rc=1; fi
done
echo "--- bash -n ---"
if bash -n install.sh; then echo "OK   install.sh"; else echo "FAIL install.sh"; rc=1; fi
echo "--- structure ---"
for d in ui bridge simulator engines templates; do [ -d "$d" ] && echo "OK   dir $d" || { echo "FAIL dir $d"; rc=1; }; done
for f in bobo-xcode.desktop bobo-xcode.svg ui/style.css; do [ -f "$f" ] && echo "OK   $f" || { echo "FAIL $f"; rc=1; }; done
exit $rc
