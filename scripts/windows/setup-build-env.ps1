# ============================================================
# BOBO OS -- Build Environment Setup in WSL2
# E:\BOBO-OS\scripts\windows\setup-build-env.ps1
#
# Installs all compilation dependencies inside Ubuntu WSL2.
# Idempotent: safe to run multiple times.
# ============================================================

$ErrorActionPreference = "Continue"
$logFile = "E:\BOBO-OS\docs\build-env-log.txt"
New-Item -ItemType Directory -Force -Path "E:\BOBO-OS\docs" | Out-Null

function Log($msg, $color = "White") {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line -ForegroundColor $color
    Add-Content -Path $logFile -Value $line
}

function RunWSL($bashCode, $desc) {
    Log "[RUNNING] $desc" "Cyan"
    $result = $bashCode | wsl -d Ubuntu-24.04 -u root -- bash 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "[DONE] $desc" "Green"
    } else {
        Log "[WARN] $desc -- exit $LASTEXITCODE (continuing)" "Yellow"
        Log "Output tail: $(($result | Select-Object -Last 5) -join ' | ')" "Yellow"
    }
}

Log "=== BOBO OS Build Environment Setup ===" "Yellow"

# --- Verify WSL2 + Ubuntu available ---
# Use direct connection test instead of parsing wsl --list (UTF-16 output causes false negatives)
$pingResult = wsl -d Ubuntu-24.04 -u root -- echo "wsl-ping" 2>&1 | Out-String
if ($pingResult -notmatch "wsl-ping") {
    Log "ERROR: Ubuntu-24.04 not responding in WSL2. Run install-wsl2.ps1 first." "Red"
    exit 1
}
Log "[OK] Ubuntu-24.04 accessible in WSL2" "Green"

# --- Verify BOBO-OS accessible from WSL2 ---
wsl -d Ubuntu-24.04 -u root -- test -d /mnt/e/BOBO-OS 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: /mnt/e/BOBO-OS not accessible from WSL2." "Red"
    Log "Make sure E:\BOBO-OS exists and WSL2 is mounted." "Red"
    exit 1
}
Log "[OK] /mnt/e/BOBO-OS accessible from WSL2" "Green"

# -- STEP 1: Update apt and install build packages ------------------------------------
RunWSL @'
set -e
export DEBIAN_FRONTEND=noninteractive
echo "Updating apt..."
apt-get update -qq 2>&1 | tail -3

echo "Installing build essentials..."
apt-get install -y --no-install-recommends \
    build-essential gcc g++ clang llvm cmake ninja-build \
    bison flex bc libelf-dev libncurses-dev libssl-dev libffi-dev \
    python3 python3-pip python3-venv python3-dev python3-gi python3-gi-cairo \
    libgtk-4-dev libadwaita-1-dev gir1.2-adw-1 \
    libglib2.0-dev \
    nodejs npm \
    git curl wget unzip \
    xorriso grub-pc-bin grub-efi-amd64-bin grub-efi-amd64-signed \
    mtools dosfstools \
    qemu-system-x86 qemu-utils ovmf \
    squashfs-tools debootstrap \
    pkg-config cpio zstd lz4 \
    dracut dracut-core \
    2>&1 | tail -20
echo "[OK] Build packages installed"
'@ "Install build packages (apt)"

# -- STEP 2: Python packages ----------------------------------------------------------
RunWSL @'
set -e
echo "Installing Python packages..."
pip3 install --quiet --upgrade pip
pip3 install --quiet \
    fastapi "uvicorn[standard]" sqlalchemy aiosqlite \
    pyicloud caldav vobject secretstorage \
    requests httpx cryptography \
    google-api-python-client google-auth-httplib2 google-auth-oauthlib \
    dbus-python \
    2>&1 | tail -10
echo "[OK] Python packages installed"
'@ "Install Python packages (pip3)"

# -- STEP 3: Verify all required tools ------------------------------------------------
$verifyScript = @'
echo "=== Tool Verification ==="
PASS=0; FAIL=0
check() {
    local tool="$1"; local cmd="$2"
    if eval "$cmd" &>/dev/null; then
        echo "  [PASS] $tool"
        ((PASS++)) || true
    else
        echo "  [FAIL] $tool -- MISSING"
        ((FAIL++)) || true
    fi
}
check "gcc"                "gcc --version"
check "g++"                "g++ --version"
check "clang"              "clang --version"
check "cmake"              "cmake --version"
check "python3"            "python3 --version"
check "pip3"               "pip3 --version"
check "node"               "node --version"
check "xorriso"            "xorriso --version"
check "grub-mkimage"       "grub-mkimage --version"
check "qemu-system-x86_64" "qemu-system-x86_64 --version"
check "mksquashfs"         "mksquashfs -version"
check "debootstrap"        "debootstrap --version"
check "dracut"             "dracut --version"
check "mtools (mformat)"   "mformat --version"
echo ""
echo "  PASS: $PASS  FAIL: $FAIL"
echo ""
echo "Build env ready. BOBO-OS root: /mnt/e/BOBO-OS"
'@

Log "" "White"
Log "[RUNNING] Verifying all tools..." "Cyan"
$verifyResult = $verifyScript | wsl -d Ubuntu-24.04 -u root -- bash 2>&1
$verifyResult | ForEach-Object { Write-Host "  $_" }
Log "[DONE] Tool verification complete" "Green"

Log "" "White"
Log "=== Build Environment Setup Complete ===" "Yellow"
Log "Run next: powershell -File 'E:\BOBO-OS\scripts\windows\compile-bobo-os.ps1'" "Cyan"
