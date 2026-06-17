#!/bin/bash
# =============================================================================
# build-bobo-apps.sh - Instalator master pentru aplicatiile concernului BOBO
# Ruleaza in rootfs-ul BOBO OS (live sau chroot). Instaleaza dependente,
# copiaza fisierele in locatiile XDG corecte, seteaza permisiuni, verifica.
#
# Utilizare:  sudo ./build-bobo-apps.sh           (instaleaza tot)
#             sudo ./build-bobo-apps.sh bobo-player (doar o aplicatie)
# =============================================================================
set -u
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TOTAL=32          # numarul total planificat de aplicatii
OK_COUNT=0
FAIL_LIST=()

log()  { echo -e "\033[1;34m[bobo-apps]\033[0m $*"; }
ok()   { echo -e "  \033[1;32mOK\033[0m   $*"; }
fail() { echo -e "  \033[1;31mFAIL\033[0m $*"; FAIL_LIST+=("$1"); }

# --- Aplicatiile implementate pana acum (se extinde la fiecare faza) ---------
# format: "nume_app"  (directorul din SRC_DIR si numele executabilului bobo-*)
APPS=(
  "bobo-player"
  "bobo-monitor"
  "bobo-settings"
  "bobo-text"
  "bobo-reader"
  "bobo-gallery"
  "bobo-archive"
  "bobo-mail"
  "bobo-installer"
  "bobo-update"
  "bobo-backup"
  "bobo-printer"
  "bobo-access"
  "bobo-login"
  "bobo-users"
  "bobo-search"
  "bobo-notif"
  "bobo-theme"
  "bobo-desk"
  "bobo-screen"
  "bobo-clip"
  "bobo-vpn"
  "bobo-share"
  "bobo-remote"
  "bobo-code"
  "bobo-vm"
  "bobo-dev"
  "bobo-cast"
  "bobo-phone"
  "bobo-ai-local"
  "bobo-scan"
  "bobo-coin"
)

# --- Dependente ESENTIALE (mereu instalate; apps GTK pornesc cu acestea) -----
ESSENTIAL_DEPS=(
  python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtksource-5
  python3-psutil wl-clipboard grim slurp libnotify-bin xdg-utils
)

# --- Dependente apt cumulate (deduplicate la instalare) ----------------------
APT_DEPS=(
  # comune GTK4 / Python
  python3-gi python3-gi-cairo gir1.2-gtk-4.0
  # APP 01 BoboPlayer (GStreamer)
  gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
  gstreamer1.0-libav gstreamer1.0-vaapi ffmpeg gstreamer1.0-gl
  # APP 02 BoboMonitor
  python3-psutil
  # APP 03 BoboSettings
  network-manager-gnome pulseaudio-utils
  # APP 04 BoboText
  gir1.2-gtksource-5 gir1.2-vte-2.91 python3-pygments
  # APP 05 BoboReader
  python3-fitz mupdf-tools
  # APP 06 BoboGallery
  python3-pillow imagemagick libimage-exiftool-perl python3-numpy
  # APP 07 BoboArchive
  p7zip-full unzip zip tar gzip bzip2 xz-utils
  # APP 08 BoboMail
  python3-keyring python3-html2text
  # APP 09 BoboInstaller
  parted gparted grub-pc-bin grub-efi-amd64-bin cryptsetup-bin rsync squashfs-tools dosfstools os-prober
  # APP 10 BoboUpdate
  python3-apt needrestart
  # APP 11 BoboBackup
  borgbackup rclone
  # APP 12 BoboPrinter
  cups cups-client cups-bsd printer-driver-all
  # APP 13 BoboAccess
  orca espeak-ng speech-dispatcher at-spi2-core wl-clipboard
  # APP 14 BoboLogin
  python3-pam
  # APP 15 BoboUsers
  accountsservice passwd
  # APP 16 BoboSearch
  xdg-utils
  # APP 17 BoboNotif
  python3-dbus libnotify-bin
  # APP 18 BoboTheme
  sassc adwaita-icon-theme papirus-icon-theme
  # APP 19 BoboDesk
  wf-shell
  # APP 20 BoboScreen
  grim slurp wf-recorder
  # APP 21 BoboClip
  wl-clipboard
  # APP 22 BoboVPN
  wireguard-tools network-manager-openvpn openvpn
  # APP 23 BoboShare
  python3-zeroconf python3-qrcode avahi-daemon
  # APP 24 BoboRemote
  freerdp2-x11 tigervnc-viewer openssh-client
  # APP 25 BoboCode
  gir1.2-vte-3.91 clangd nodejs npm git pyflakes3
  # APP 26 BoboVM
  qemu-system-x86 qemu-utils libvirt-daemon-system virtinst virt-viewer
  # APP 27 BoboDev
  podman buildah
  # APP 28 BoboCast
  python3-pychromecast
  # APP 29 BoboPhone
  kdeconnect
  # APP 31 BoboScan
  clamav clamav-daemon rkhunter chkrootkit lynis
  # APP 32 BoboCoin (restul prin pip)
  python3-cryptography python3-qrcode
)
# Pachete best-effort (fallback daca lipsesc)
APT_OPTIONAL=( gstreamer1.0-plugins-rs gnome-bluetooth-3.0 gir1.2-gtop-2.0 p7zip-rar )

PIP_DEPS=( psutil pymupdf ebooklib html2text imapclient mnemonic eth-account )

# ---------------------------------------------------------------- 1. apt
install_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then
    log "apt-get indisponibil - sar peste instalarea dependentelor de sistem"
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  # Dependentele esentiale se instaleaza MEREU (apps GTK pornesc cu ele)
  log "Instalez dependente esentiale (${#ESSENTIAL_DEPS[@]} pachete)..."
  apt-get install -y --no-install-recommends "${ESSENTIAL_DEPS[@]}" 2>/dev/null || \
    for p in "${ESSENTIAL_DEPS[@]}"; do apt-get install -y --no-install-recommends "$p" 2>/dev/null || echo "  skip $p"; done
  if [ "${BOBO_APPS_SKIP_DEPS:-0}" = "1" ]; then
    log "BOBO_APPS_SKIP_DEPS=1 - sar peste dependentele complete (doar esentiale + fisiere)"
    return
  fi
  log "Instalez dependente complete apt (${#APT_DEPS[@]} pachete)..."
  apt-get install -y --no-install-recommends "${APT_DEPS[@]}" || \
    for p in "${APT_DEPS[@]}"; do apt-get install -y --no-install-recommends "$p" || echo "  skip $p"; done
  for p in "${APT_OPTIONAL[@]}"; do
    apt-get install -y --no-install-recommends "$p" 2>/dev/null && ok "optional $p" || log "optional lipsa: $p (folosesc fallback Gtk.Video)"
  done
}

# ---------------------------------------------------------------- 2. pip
install_pip() {
  [ "${BOBO_APPS_SKIP_DEPS:-0}" = "1" ] && return
  [ ${#PIP_DEPS[@]} -eq 0 ] && return
  log "Instalez dependente pip..."
  pip3 install --break-system-packages "${PIP_DEPS[@]}" 2>/dev/null || \
    pip3 install "${PIP_DEPS[@]}" || true
}

# ---------------------------------------------------------------- 3. tema + WM
install_theme() {
  log "Instalez tema globala BOBO-Dark si keybindings Wayfire..."
  install -d /usr/share/themes/BOBO-Dark/gtk-4.0
  install -m 644 "$SRC_DIR/shared/BOBO-Dark-gtk.css" /usr/share/themes/BOBO-Dark/gtk-4.0/gtk.css 2>/dev/null && ok "tema BOBO-Dark"
  if [ -f "$SRC_DIR/shared/bobo-wayfire-defaults.ini" ]; then
    install -m 644 "$SRC_DIR/shared/bobo-wayfire-defaults.ini" /etc/bobo-wayfire-defaults.ini && ok "keybindings Wayfire"
  fi
}

# ---------------------------------------------------------------- 4. copiere app
install_app() {
  local app="$1"
  local d="$SRC_DIR/$app"
  if [ ! -d "$d" ]; then fail "$app (director lipsa)"; return; fi
  log "Instalez $app..."

  # executabil -> /usr/bin (chmod 755)
  if [ -f "$d/$app" ]; then
    install -m 755 "$d/$app" "/usr/bin/$app"
  fi
  # resurse (py, css, sub-module) -> /usr/share/<app>/
  install -d "/usr/share/$app"
  find "$d" -maxdepth 1 -type f \( -name "*.py" -o -name "*.css" \) -exec install -m 644 {} "/usr/share/$app/" \;
  # sub-directoare (ex: panels/) copiate recursiv
  for sub in "$d"/*/; do
    [ -d "$sub" ] || continue
    cp -r "$sub" "/usr/share/$app/"
  done
  # fisier .desktop -> /usr/share/applications
  if [ -f "$d/$app.desktop" ]; then
    install -d /usr/share/applications
    install -m 644 "$d/$app.desktop" "/usr/share/applications/$app.desktop"
  fi
  # daemon autostart (optional)
  if [ -f "$d/$app-autostart.desktop" ]; then
    install -d /etc/xdg/autostart
    install -m 644 "$d/$app-autostart.desktop" "/etc/xdg/autostart/$app.desktop"
  fi
  # iconita SVG -> hicolor
  if [ -f "$d/$app.svg" ]; then
    install -d /usr/share/icons/hicolor/scalable/apps
    install -m 644 "$d/$app.svg" "/usr/share/icons/hicolor/scalable/apps/$app.svg"
  fi
}

# ---------------------------------------------------------------- 5. post-install
post_install() {
  log "Actualizez bazele de date desktop/mime/icoane..."
  update-desktop-database /usr/share/applications/ 2>/dev/null || true
  update-mime-database /usr/share/mime/ 2>/dev/null || true
  gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
  ldconfig 2>/dev/null || true
}

# ---------------------------------------------------------------- 6. verificare
verify_app() {
  local app="$1"
  if "$app" --version >/dev/null 2>&1; then
    ok "$app porneste ($("$app" --version 2>/dev/null | head -1))"
    OK_COUNT=$((OK_COUNT+1))
  else
    fail "$app (--version a esuat)"
  fi
}

# ---------------------------------------------------------------- main
main() {
  log "===== Instalare aplicatii concern BOBO OS ====="
  install_apt
  install_pip
  install_theme

  local selected=("${APPS[@]}")
  [ $# -gt 0 ] && selected=("$@")

  for app in "${selected[@]}"; do install_app "$app"; done
  post_install
  for app in "${selected[@]}"; do verify_app "$app"; done

  echo
  log "===== Raport final ====="
  log "Instalate cu succes: $OK_COUNT/${#selected[@]} (din $TOTAL planificate)"
  if [ ${#FAIL_LIST[@]} -gt 0 ]; then
    log "Esecuri: ${FAIL_LIST[*]}"
    exit 1
  fi
  log "Toate aplicatiile selectate au fost instalate si verificate."
}

main "$@"
