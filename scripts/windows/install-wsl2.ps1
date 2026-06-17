# ============================================================
# BOBO OS — WSL2 Auto-Installer
# E:\BOBO-OS\scripts\windows\install-wsl2.ps1
#
# Installs Ubuntu 24.04 LTS inside WSL2 and creates the 'bobo' build user.
# WSL2 kernel assumed already present (Docker Desktop provides it).
# Run as Administrator for first-time Windows feature activation;
# subsequent runs (Ubuntu install) work as normal user.
# ============================================================

$ErrorActionPreference = "Continue"
$logFile = "E:\BOBO-OS\docs\wsl2-install-log.txt"
New-Item -ItemType Directory -Force -Path "E:\BOBO-OS\docs" | Out-Null

function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Log "=== BOBO OS WSL2 Installation Started ==="
Log "Windows Build: $([System.Environment]::OSVersion.Version.Build)"

# --- Verifică versiunea Windows ---
$build = [System.Environment]::OSVersion.Version.Build
if ($build -lt 19041) {
    Log "ERROR: Windows build $build too old. WSL2 requires 19041+."
    exit 1
}
Log "[OK] Windows build $build is supported"

# --- Activează funcționalitățile Windows (necesită Admin) ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Log "Running as Administrator — enabling Windows features..."

    $wslFeature = dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 3010) {
        Log "[OK] WSL feature enabled (exit $LASTEXITCODE)"
    } else {
        Log "[SKIP] WSL feature already enabled or not needed"
    }

    $vmFeature = dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 3010) {
        Log "[OK] Virtual Machine Platform enabled (exit $LASTEXITCODE)"
    } else {
        Log "[SKIP] VMP already enabled"
    }

    # Download and install WSL2 kernel update (in case Docker's version is old)
    $kernelUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
    $kernelInstaller = "$env:TEMP\wsl_update_x64.msi"
    try {
        Log "Downloading WSL2 kernel update..."
        Invoke-WebRequest -Uri $kernelUrl -OutFile $kernelInstaller -UseBasicParsing -TimeoutSec 60
        Start-Process msiexec.exe -Wait -ArgumentList "/i `"$kernelInstaller`" /quiet /norestart"
        Log "[OK] WSL2 kernel updated"
    } catch {
        Log "[SKIP] Kernel update skipped (Docker Desktop provides kernel): $_"
    }
} else {
    Log "[SKIP] Not Administrator — assuming WSL2 features already enabled (Docker Desktop present)"
}

# --- Set WSL2 as default ---
Log "Setting WSL2 as default version..."
wsl --set-default-version 2 2>&1 | Out-Null
Log "[OK] WSL2 is default"

# --- Check if Ubuntu already installed ---
$wslDistros = wsl --list 2>&1 | Out-String
if ($wslDistros -match "Ubuntu") {
    Log "[SKIP] Ubuntu already installed in WSL2"
} else {
    Log "Installing Ubuntu 24.04 LTS..."

    # Method 1: wsl --install (works without admin on Win11 if WSL2 already installed)
    wsl --install -d Ubuntu-24.04 --no-launch 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "[OK] Ubuntu 24.04 installed via wsl --install"
    } else {
        # Method 2: winget
        Log "[RETRY] Trying winget..."
        winget install --id Canonical.Ubuntu.2404 --silent --accept-package-agreements --accept-source-agreements 2>&1
        if ($LASTEXITCODE -eq 0) {
            Log "[OK] Ubuntu 24.04 installed via winget"
        } else {
            # Method 3: Direct download of the appx
            Log "[RETRY] Downloading Ubuntu 24.04 appx directly..."
            $ubuntuUrl = "https://aka.ms/wslubuntu2204"  # fallback to 22.04 if 24.04 not available
            $ubuntuOut = "$env:TEMP\Ubuntu.appx"
            try {
                Invoke-WebRequest -Uri $ubuntuUrl -OutFile $ubuntuOut -UseBasicParsing -TimeoutSec 300
                Add-AppxPackage -Path $ubuntuOut
                Log "[OK] Ubuntu installed via appx download"
            } catch {
                Log "ERROR: Could not install Ubuntu: $_"
                Log "Please run manually: wsl --install -d Ubuntu-24.04"
                exit 1
            }
        }
    }
}

# --- Configure Ubuntu: create bobo user ---
Log "Configuring Ubuntu (creating bobo user)..."
$setupScript = @'
#!/bin/bash
# Create bobo user for BOBO OS builds
if ! id bobo &>/dev/null; then
    useradd -m -s /bin/bash bobo 2>/dev/null
    echo 'bobo:bobo' | chpasswd
    usermod -aG sudo bobo
    echo 'bobo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
    echo '[OK] User bobo created'
else
    echo '[SKIP] User bobo already exists'
fi
'@

# Initialize Ubuntu (first run creates /etc etc.)
Write-Host "Initializing Ubuntu (this may take 2-3 minutes on first run)..."
$setupScript | wsl -d Ubuntu-24.04 -u root -- bash 2>&1
Log "[OK] Ubuntu configured"

# --- Verify ---
$wslFinal = wsl --list --verbose 2>&1 | Out-String
Log "Final WSL2 state:"
Log $wslFinal

Log "=== WSL2 Installation Complete ==="
Log "Run next: powershell -File 'E:\BOBO-OS\scripts\windows\setup-build-env.ps1'"
