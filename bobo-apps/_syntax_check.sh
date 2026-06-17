#!/bin/bash
cd "$(dirname "$0")" || exit 1
rc=0
FILES="bobo-player/player.py bobo-monitor/monitor.py bobo-settings/settings.py bobo-text/editor.py bobo-reader/reader.py bobo-gallery/gallery.py bobo-archive/archive.py bobo-mail/mail.py bobo-installer/installer.py bobo-update/update.py bobo-backup/backup.py bobo-printer/printer.py bobo-access/access.py bobo-login/login.py bobo-users/users.py bobo-search/search.py bobo-notif/notif.py bobo-theme/theme.py bobo-desk/desk.py bobo-screen/screen.py bobo-clip/clip.py bobo-vpn/vpn.py bobo-share/share.py bobo-remote/remote.py bobo-code/code.py bobo-vm/vm.py bobo-dev/dev.py bobo-cast/cast.py bobo-phone/phone.py bobo-ai-local/ai.py bobo-scan/scan.py bobo-coin/coin.py"
for f in $FILES; do
  if python3 -m py_compile "$f" 2>/tmp/pyerr.txt; then
    echo "OK   $f"
  else
    echo "FAIL $f"; cat /tmp/pyerr.txt; rc=1
  fi
done
if bash -n build-bobo-apps.sh; then echo "OK   build-bobo-apps.sh"; else echo "FAIL build script"; rc=1; fi
exit $rc
