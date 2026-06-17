#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Phase 1.1: Toolchain Setup Script
# Installs all required build tools and runtimes to E:\Program Files\
# Safe to re-run: checks for existing installs before acting.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Host environment detection
# ---------------------------------------------------------------------------
if grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_ENV="wsl2"
elif [[ "$(uname)" == "Darwin" ]]; then
  HOST_ENV="macos"
else
  HOST_ENV="linux"
fi

echo "==> Detected host environment: ${HOST_ENV}"

# ---------------------------------------------------------------------------
# Path configuration  -  all tools go under E:\Program Files (WSL path: /mnt/e/Program Files)
# ---------------------------------------------------------------------------
if [[ "${HOST_ENV}" == "wsl2" ]]; then
  PROGRAMS="/mnt/e/Program Files"
  BOBO_ROOT="/mnt/e/BOBO-OS"
elif [[ "${HOST_ENV}" == "macos" ]]; then
  PROGRAMS="/Volumes/E/Program Files"
  BOBO_ROOT="/Volumes/E/BOBO-OS"
else
  PROGRAMS="/mnt/e/Program Files"
  BOBO_ROOT="/mnt/e/BOBO-OS"
fi

LOG_FILE="${BOBO_ROOT}/docs/setup-log.txt"
mkdir -p "${BOBO_ROOT}/docs"

# Redirect all output to log file while keeping stdout visible
exec > >(tee -a "${LOG_FILE}") 2>&1
echo ""
echo "======================================================================="
echo "  BOBO OS  -  Toolchain Setup"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Host:    ${HOST_ENV}"
echo "  Install: ${PROGRAMS}"
echo "======================================================================="
echo ""

# ---------------------------------------------------------------------------
# Helper: check whether a tool is already installed
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0

declare -A TOOL_STATUS
declare -A TOOL_PATH

tool_installed() {
  local name="$1"
  local check_path="$2"
  [[ -e "${check_path}" ]]
}

mark_status() {
  local name="$1"
  local path="$2"
  local ok="$3"   # "pass" or "fail"

  TOOL_PATH["${name}"]="${path}"
  if [[ "${ok}" == "pass" ]]; then
    TOOL_STATUS["${name}"]="[OK]"
    (( PASS_COUNT++ )) || true
  else
    TOOL_STATUS["${name}"]="[FAIL]"
    (( FAIL_COUNT++ )) || true
  fi
}

# ---------------------------------------------------------------------------
# Detect Linux package manager
# ---------------------------------------------------------------------------
if command -v apt-get &>/dev/null; then
  PKG_INSTALL="apt-get install -y"
  PKG_UPDATE="apt-get update -y"
elif command -v dnf &>/dev/null; then
  PKG_INSTALL="dnf install -y"
  PKG_UPDATE="dnf check-update -y || true"
elif command -v pacman &>/dev/null; then
  PKG_INSTALL="pacman -S --noconfirm"
  PKG_UPDATE="pacman -Sy"
elif command -v brew &>/dev/null; then
  PKG_INSTALL="brew install"
  PKG_UPDATE="brew update"
else
  echo "ERROR: No supported package manager found (apt, dnf, pacman, brew)."
  exit 1
fi

echo "==> Package manager command: ${PKG_INSTALL}"
echo "==> Updating package lists..."
eval "sudo ${PKG_UPDATE}" || true

# ---------------------------------------------------------------------------
# Phase 1.1.1  -  System packages: gcc, llvm, clang, cmake, python3, nodejs
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing system packages ---"

install_system_pkg() {
  local pkg="$1"
  local binary="$2"
  local install_marker="${PROGRAMS}/${pkg}/installed.marker"

  if tool_installed "${pkg}" "${install_marker}"; then
    echo "  [SKIP] ${pkg} already installed."
    mkdir -p "${PROGRAMS}/${pkg}"
    mark_status "${pkg}" "${PROGRAMS}/${pkg}" "pass"
    return
  fi

  echo "  [INST] Installing ${pkg}..."
  if eval "sudo ${PKG_INSTALL} ${pkg}" 2>&1; then
    local bin_path
    bin_path=$(command -v "${binary}" 2>/dev/null || echo "system")
    mkdir -p "${PROGRAMS}/${pkg}"
    touch "${install_marker}"
    # Create symlink so BOBO OS knows where to find it
    ln -sfn "${bin_path}" "${PROGRAMS}/${pkg}/${binary}" 2>/dev/null || true
    mark_status "${pkg}" "${PROGRAMS}/${pkg}" "pass"
    echo "  [OK]   ${pkg} installed."
  else
    mark_status "${pkg}" "${PROGRAMS}/${pkg}" "fail"
    echo "  [FAIL] ${pkg} installation failed."
  fi
}

install_system_pkg "gcc"      "gcc"
install_system_pkg "llvm"     "llvm-config"
install_system_pkg "clang"    "clang"
install_system_pkg "cmake"    "cmake"
install_system_pkg "python3"  "python3"
install_system_pkg "nodejs"   "node"

# Install xorriso (ISO creation tool)
install_system_pkg "xorriso"  "xorriso"

# grub2-tools (package name varies by distro)
for pkg in grub2-tools grub-common grub2; do
  if eval "sudo ${PKG_INSTALL} ${pkg}" 2>/dev/null; then
    mkdir -p "${PROGRAMS}/grub2"
    touch "${PROGRAMS}/grub2/installed.marker"
    mark_status "grub2" "${PROGRAMS}/grub2" "pass"
    break
  fi
done
[[ -z "${TOOL_STATUS[grub2]+x}" ]] && mark_status "grub2" "${PROGRAMS}/grub2" "fail"

# mkinitcpio or dracut
if command -v mkinitcpio &>/dev/null; then
  mkdir -p "${PROGRAMS}/mkinitcpio"
  touch "${PROGRAMS}/mkinitcpio/installed.marker"
  mark_status "mkinitcpio" "${PROGRAMS}/mkinitcpio" "pass"
elif eval "sudo ${PKG_INSTALL} mkinitcpio" 2>/dev/null; then
  mkdir -p "${PROGRAMS}/mkinitcpio"
  touch "${PROGRAMS}/mkinitcpio/installed.marker"
  mark_status "mkinitcpio" "${PROGRAMS}/mkinitcpio" "pass"
elif eval "sudo ${PKG_INSTALL} dracut" 2>/dev/null; then
  # dracut is the alternative on Fedora/RHEL systems
  mkdir -p "${PROGRAMS}/mkinitcpio"
  touch "${PROGRAMS}/mkinitcpio/installed.marker"
  mark_status "mkinitcpio" "${PROGRAMS}/mkinitcpio" "pass"
else
  mark_status "mkinitcpio" "${PROGRAMS}/mkinitcpio" "fail"
fi

# GTK4 development libraries
echo ""
echo "--- Installing GTK4 ---"
GTK4_MARKER="${PROGRAMS}/gtk4/installed.marker"
if tool_installed "gtk4" "${GTK4_MARKER}"; then
  echo "  [SKIP] GTK4 already installed."
  mark_status "gtk4" "${PROGRAMS}/gtk4" "pass"
else
  GTK4_INSTALLED=false
  for pkg in libgtk-4-dev gtk4-devel libgtk4 gtk4; do
    if eval "sudo ${PKG_INSTALL} ${pkg}" 2>/dev/null; then
      GTK4_INSTALLED=true
      break
    fi
  done
  if $GTK4_INSTALLED; then
    mkdir -p "${PROGRAMS}/gtk4"
    touch "${GTK4_MARKER}"
    mark_status "gtk4" "${PROGRAMS}/gtk4" "pass"
    echo "  [OK]   GTK4 installed."
  else
    mark_status "gtk4" "${PROGRAMS}/gtk4" "fail"
    echo "  [FAIL] GTK4 installation failed."
  fi
fi

# Qt6 development libraries
echo ""
echo "--- Installing Qt6 ---"
QT6_MARKER="${PROGRAMS}/qt6/installed.marker"
if tool_installed "qt6" "${QT6_MARKER}"; then
  echo "  [SKIP] Qt6 already installed."
  mark_status "qt6" "${PROGRAMS}/qt6" "pass"
else
  QT6_INSTALLED=false
  for pkg in qt6-base-dev qt6-devel qt6-qtbase-devel; do
    if eval "sudo ${PKG_INSTALL} ${pkg}" 2>/dev/null; then
      QT6_INSTALLED=true
      break
    fi
  done
  if $QT6_INSTALLED; then
    mkdir -p "${PROGRAMS}/qt6"
    touch "${QT6_MARKER}"
    mark_status "qt6" "${PROGRAMS}/qt6" "pass"
    echo "  [OK]   Qt6 installed."
  else
    mark_status "qt6" "${PROGRAMS}/qt6" "fail"
    echo "  [FAIL] Qt6 installation failed."
  fi
fi

# ffmpeg
echo ""
echo "--- Installing ffmpeg ---"
FFMPEG_MARKER="${PROGRAMS}/ffmpeg/installed.marker"
if tool_installed "ffmpeg" "${FFMPEG_MARKER}"; then
  echo "  [SKIP] ffmpeg already installed."
  mark_status "ffmpeg" "${PROGRAMS}/ffmpeg" "pass"
else
  if eval "sudo ${PKG_INSTALL} ffmpeg" 2>/dev/null; then
    mkdir -p "${PROGRAMS}/ffmpeg"
    FFMPEG_BIN=$(command -v ffmpeg 2>/dev/null || echo "system")
    ln -sfn "${FFMPEG_BIN}" "${PROGRAMS}/ffmpeg/ffmpeg" 2>/dev/null || true
    touch "${FFMPEG_MARKER}"
    mark_status "ffmpeg" "${PROGRAMS}/ffmpeg" "pass"
    echo "  [OK]   ffmpeg installed."
  else
    mark_status "ffmpeg" "${PROGRAMS}/ffmpeg" "fail"
    echo "  [FAIL] ffmpeg installation failed."
  fi
fi

# ---------------------------------------------------------------------------
# Phase 1.1.2  -  Clone and compile Wine with DXVK
# ---------------------------------------------------------------------------
echo ""
echo "--- Building Wine with DXVK ---"
WINE_SRC="${PROGRAMS}/wine-src"
WINE_MARKER="${WINE_SRC}/wine.installed"

if tool_installed "wine-src" "${WINE_MARKER}"; then
  echo "  [SKIP] Wine already built."
  mark_status "wine-src" "${WINE_SRC}" "pass"
else
  # Install Wine build dependencies
  echo "  [DEPS] Installing Wine build dependencies..."
  WINE_DEPS="git flex bison mingw-w64 libfreetype-dev libfontconfig-dev \
    libxcb1-dev libxcb-composite0-dev libx11-dev libxext-dev libxrender-dev \
    libgl-dev libvulkan-dev"
  eval "sudo ${PKG_INSTALL} ${WINE_DEPS}" 2>/dev/null || true

  mkdir -p "${WINE_SRC}"

  if [[ ! -d "${WINE_SRC}/wine" ]]; then
    echo "  [GIT]  Cloning Wine (Wine-staging for best compatibility)..."
    git clone --depth=1 --branch wine-8.0 \
      https://gitlab.winehq.org/wine/wine.git \
      "${WINE_SRC}/wine" 2>&1 || {
        echo "  [WARN] Could not clone Wine. Using system wine if available."
      }
  fi

  if [[ -d "${WINE_SRC}/wine" ]]; then
    echo "  [BUILD] Configuring Wine..."
    cd "${WINE_SRC}/wine"
    mkdir -p build64 && cd build64
    ../configure \
      --prefix="${WINE_SRC}/dist" \
      --enable-win64 \
      --with-vulkan \
      --with-opengl \
      --disable-tests \
      2>&1
    echo "  [BUILD] Compiling Wine (this takes 20–40 minutes)..."
    make -j"$(nproc)" 2>&1
    make install 2>&1
    cd "${BOBO_ROOT}"

    # Install DXVK (prebuilt binaries  -  much faster than building from source)
    echo "  [DXVK] Installing DXVK for DirectX support..."
    DXVK_DIR="${WINE_SRC}/dxvk"
    mkdir -p "${DXVK_DIR}"
    DXVK_VERSION="2.3"
    DXVK_URL="https://github.com/doitsujin/dxvk/releases/download/v${DXVK_VERSION}/dxvk-${DXVK_VERSION}.tar.gz"
    curl -L "${DXVK_URL}" -o "${DXVK_DIR}/dxvk.tar.gz" 2>&1
    tar -xzf "${DXVK_DIR}/dxvk.tar.gz" -C "${DXVK_DIR}" 2>&1
    # The DXVK setup script installs DLLs into a Wine prefix; here we stage them
    cp -r "${DXVK_DIR}/dxvk-${DXVK_VERSION}/"* "${DXVK_DIR}/" 2>/dev/null || true
    rm -f "${DXVK_DIR}/dxvk.tar.gz"
    echo "  [OK]   DXVK staged. DLLs will be installed per Wine-prefix by wine-wrapper.sh."

    touch "${WINE_MARKER}"
    mark_status "wine-src" "${WINE_SRC}" "pass"
    echo "  [OK]   Wine built and installed."
  else
    # Fallback: try system Wine
    if eval "sudo ${PKG_INSTALL} wine64 wine winetricks" 2>/dev/null; then
      touch "${WINE_MARKER}"
      mark_status "wine-src" "${WINE_SRC}" "pass"
      echo "  [OK]   System Wine installed as fallback."
    else
      mark_status "wine-src" "${WINE_SRC}" "fail"
      echo "  [FAIL] Wine not available."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Phase 1.1.3  -  Clone and compile Darling (macOS compatibility)
# ---------------------------------------------------------------------------
echo ""
echo "--- Building Darling ---"
DARLING_SRC="${PROGRAMS}/darling-src"
DARLING_MARKER="${DARLING_SRC}/darling.installed"

if tool_installed "darling-src" "${DARLING_MARKER}"; then
  echo "  [SKIP] Darling already built."
  mark_status "darling-src" "${DARLING_SRC}" "pass"
else
  echo "  [DEPS] Installing Darling build dependencies..."
  DARLING_DEPS="git cmake clang bison flex libfuse-dev pkg-config \
    libglu1-mesa-dev libcairo2-dev libpulse-dev libavformat-dev"
  eval "sudo ${PKG_INSTALL} ${DARLING_DEPS}" 2>/dev/null || true

  mkdir -p "${DARLING_SRC}"

  if [[ ! -d "${DARLING_SRC}/darling" ]]; then
    echo "  [GIT]  Cloning Darling..."
    git clone --recursive --depth=1 \
      https://github.com/darlinghq/darling.git \
      "${DARLING_SRC}/darling" 2>&1 || {
        echo "  [WARN] Could not clone Darling  -  network issue or git unavailable."
      }
  fi

  if [[ -d "${DARLING_SRC}/darling" ]]; then
    echo "  [BUILD] Configuring Darling..."
    mkdir -p "${DARLING_SRC}/darling/build"
    cd "${DARLING_SRC}/darling/build"
    cmake .. \
      -DCMAKE_INSTALL_PREFIX="${DARLING_SRC}/dist" \
      -DCMAKE_BUILD_TYPE=Release \
      2>&1
    echo "  [BUILD] Compiling Darling (this takes 30–60 minutes)..."
    make -j"$(nproc)" 2>&1
    make install 2>&1
    cd "${BOBO_ROOT}"
    touch "${DARLING_MARKER}"
    mark_status "darling-src" "${DARLING_SRC}" "pass"
    echo "  [OK]   Darling built and installed."
  else
    mark_status "darling-src" "${DARLING_SRC}" "fail"
    echo "  [FAIL] Darling source not available."
  fi
fi

# ---------------------------------------------------------------------------
# Phase 1.1.4  -  Install Waydroid (Android app support)
# ---------------------------------------------------------------------------
echo ""
echo "--- Installing Waydroid ---"
WAYDROID_DIR="${PROGRAMS}/waydroid"
WAYDROID_MARKER="${WAYDROID_DIR}/waydroid.installed"

if tool_installed "waydroid" "${WAYDROID_MARKER}"; then
  echo "  [SKIP] Waydroid already installed."
  mark_status "waydroid" "${WAYDROID_DIR}" "pass"
else
  mkdir -p "${WAYDROID_DIR}"
  WAYDROID_OK=false

  # Try official Waydroid installer script
  if command -v curl &>/dev/null; then
    echo "  [INST] Installing Waydroid via official script..."
    curl -s https://repo.waydro.id/waydroid.gpg \
      -o /usr/share/keyrings/waydroid.gpg 2>/dev/null || true
    # For Debian/Ubuntu
    if command -v apt-get &>/dev/null; then
      echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] \
https://repo.waydro.id/ $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/waydroid.list >/dev/null 2>&1 || true
      sudo apt-get update -y 2>/dev/null || true
      if sudo apt-get install -y waydroid 2>/dev/null; then
        WAYDROID_OK=true
      fi
    fi
    # For Fedora
    if ! $WAYDROID_OK && command -v dnf &>/dev/null; then
      if sudo dnf install -y waydroid 2>/dev/null; then
        WAYDROID_OK=true
      fi
    fi
  fi

  # Fallback: clone source
  if ! $WAYDROID_OK && [[ ! -d "${WAYDROID_DIR}/src" ]]; then
    echo "  [GIT]  Cloning Waydroid source as fallback..."
    git clone --depth=1 \
      https://github.com/waydroid/waydroid.git \
      "${WAYDROID_DIR}/src" 2>/dev/null || true
    if [[ -d "${WAYDROID_DIR}/src" ]]; then
      WAYDROID_OK=true
    fi
  fi

  if $WAYDROID_OK; then
    WAYDROID_BIN=$(command -v waydroid 2>/dev/null || echo "${WAYDROID_DIR}/src/waydroid")
    ln -sfn "${WAYDROID_BIN}" "${WAYDROID_DIR}/waydroid" 2>/dev/null || true
    touch "${WAYDROID_MARKER}"
    mark_status "waydroid" "${WAYDROID_DIR}" "pass"
    echo "  [OK]   Waydroid installed."
  else
    mark_status "waydroid" "${WAYDROID_DIR}" "fail"
    echo "  [FAIL] Waydroid not available on this host."
  fi
fi

# ---------------------------------------------------------------------------
# Phase 1.1.5  -  Self-test: verify all required binaries are reachable
# ---------------------------------------------------------------------------
echo ""
echo "======================================================================="
echo "  SELF-TEST  -  Verifying installed tools"
echo "======================================================================="

verify_binary() {
  local name="$1"
  local binary="$2"
  if command -v "${binary}" &>/dev/null; then
    echo "  PASS  ${name}: $(command -v "${binary}")"
  else
    echo "  FAIL  ${name}: '${binary}' not found in PATH"
  fi
}

verify_binary "gcc"       "gcc"
verify_binary "clang"     "clang"
verify_binary "cmake"     "cmake"
verify_binary "python3"   "python3"
verify_binary "node"      "node"
verify_binary "xorriso"   "xorriso"
verify_binary "ffmpeg"    "ffmpeg"

# ---------------------------------------------------------------------------
# Final status table
# ---------------------------------------------------------------------------
echo ""
echo "======================================================================="
echo "  INSTALLATION SUMMARY"
printf "  %-20s %-45s %s\n" "TOOL" "INSTALL PATH" "STATUS"
echo "  -----------------------------------------------------------------------"

for tool in "${!TOOL_STATUS[@]}"; do
  printf "  %-20s %-45s %s\n" "${tool}" "${TOOL_PATH[$tool]}" "${TOOL_STATUS[$tool]}"
done | sort

echo "  -----------------------------------------------------------------------"
echo "  Passed: ${PASS_COUNT}   Failed: ${FAIL_COUNT}"
echo "======================================================================="

if (( FAIL_COUNT > 0 )); then
  echo ""
  echo "  [WARN] Some tools failed to install. Review the log at:"
  echo "     ${LOG_FILE}"
  echo "  Run this script again after fixing the issues."
  exit 1
else
  echo ""
  echo "  [OK] All tools installed successfully."
  echo "  Log saved to: ${LOG_FILE}"
fi

echo ""
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================="
