#!/usr/bin/env bash
# =============================================================================
# BOBO OS  -  Terminal Setup Script
# E:\BOBO-OS\apps\terminal\terminal-setup.sh
#
# Installs foot terminal emulator and deploys the BOBO OS terminal config.
# Also installs bash/zsh tweaks and the BOBO OS shell prompt.
# =============================================================================

set -euo pipefail

PASS=0; FAIL=0
log()  { echo "[Terminal] $*"; }
ok()   { log "PASS  $*"; (( PASS++ )) || true; }
fail() { log "FAIL  $*"; (( FAIL++ )) || true; }
warn() { log "WARN  $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="${SCRIPT_DIR}/terminal.conf"
FOOT_CONF_DIR="${HOME}/.config/foot"

# ---------------------------------------------------------------------------
# Install foot terminal
# ---------------------------------------------------------------------------
if command -v foot &>/dev/null; then
  ok "foot already installed: $(foot --version 2>/dev/null | head -1)"
else
  log "Installing foot terminal emulator..."
  if command -v apt-get &>/dev/null; then
    apt-get install -y foot 2>/dev/null && ok "foot installed via apt" || \
      { warn "foot not in apt  -  trying flatpak"; \
        flatpak install -y flathub org.codeberg.dnkl.foot 2>/dev/null && ok "foot installed via flatpak" || \
        fail "foot installation failed"; }
  elif command -v pacman &>/dev/null; then
    pacman -S --noconfirm foot 2>/dev/null && ok "foot installed via pacman" || \
      fail "foot installation failed"
  elif command -v dnf &>/dev/null; then
    dnf install -y foot 2>/dev/null && ok "foot installed via dnf" || \
      fail "foot installation failed"
  else
    fail "No supported package manager found; install foot manually"
  fi
fi

# ---------------------------------------------------------------------------
# Deploy foot config
# ---------------------------------------------------------------------------
mkdir -p "${FOOT_CONF_DIR}"
cp "${CONF_SRC}" "${FOOT_CONF_DIR}/foot.ini"
ok "foot config deployed: ${FOOT_CONF_DIR}/foot.ini"

# ---------------------------------------------------------------------------
# BOBO OS shell prompt (bash + zsh)
# ---------------------------------------------------------------------------
PROMPT_SNIPPET='
# BOBO OS prompt  -  shows user@host:dir with git branch + error indicator
__bobo_prompt() {
  local exit_code=$?
  local RED="\[\033[38;5;196m\]"
  local GRN="\[\033[38;5;82m\]"
  local BLU="\[\033[38;5;75m\]"
  local CYN="\[\033[38;5;51m\]"
  local YEL="\[\033[38;5;226m\]"
  local RST="\[\033[0m\]"

  local git_branch=""
  if command -v git &>/dev/null; then
    git_branch=$(git symbolic-ref --short HEAD 2>/dev/null) && \
      git_branch=" ${YEL}(${git_branch})${RST}"
  fi

  local err_indicator=""
  [[ "${exit_code}" -ne 0 ]] && err_indicator="${RED}✗${exit_code} ${RST}"

  PS1="${err_indicator}${BLU}\u${RST}@${CYN}\h${RST}:${GRN}\w${RST}${git_branch}\n\$ "
}
PROMPT_COMMAND="__bobo_prompt"
'

# Append to ~/.bashrc if not already there
if [[ -f "${HOME}/.bashrc" ]] && ! grep -q '__bobo_prompt' "${HOME}/.bashrc"; then
  printf '%s\n' "${PROMPT_SNIPPET}" >> "${HOME}/.bashrc"
  ok "BOBO OS bash prompt added to ~/.bashrc"
elif ! [[ -f "${HOME}/.bashrc" ]]; then
  printf '%s\n' "${PROMPT_SNIPPET}" > "${HOME}/.bashrc"
  ok "~/.bashrc created with BOBO OS prompt"
else
  ok "BOBO OS bash prompt already in ~/.bashrc"
fi

# .zshrc prompt (PROMPT)
ZSH_PROMPT_SNIPPET='
# BOBO OS zsh prompt
autoload -Uz vcs_info
precmd() { vcs_info }
zstyle ":vcs_info:git:*" formats " (%b)"
setopt PROMPT_SUBST
PROMPT="%F{75}%n%f@%F{51}%m%f:%F{82}%~%f%F{226}${vcs_info_msg_0_}%f
%# "
'
if [[ -f "${HOME}/.zshrc" ]] && ! grep -q 'bobo.*zsh.*prompt\|BOBO OS zsh' "${HOME}/.zshrc"; then
  printf '%s\n' "${ZSH_PROMPT_SNIPPET}" >> "${HOME}/.zshrc"
  ok "BOBO OS zsh prompt added to ~/.zshrc"
fi

# ---------------------------------------------------------------------------
# Useful aliases
# ---------------------------------------------------------------------------
ALIASES='
# BOBO OS aliases
alias ll="ls -lAh --color=auto"
alias la="ls -A --color=auto"
alias grep="grep --color=auto"
alias df="df -h"
alias free="free -h"
alias update="sudo flatpak update -y && sudo apt upgrade -y 2>/dev/null || true"
alias novastore="python3 /usr/local/lib/bobo/novastore/frontend/store.py"
alias bobo-settings="python3 /usr/local/lib/bobo/desktop/settings/settings.py"
'

if [[ -f "${HOME}/.bashrc" ]] && ! grep -q 'BOBO OS aliases' "${HOME}/.bashrc"; then
  printf '%s\n' "${ALIASES}" >> "${HOME}/.bashrc"
  ok "BOBO OS aliases added to ~/.bashrc"
fi

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
echo ""
echo "=== Terminal Setup Self-Test ==="
command -v foot &>/dev/null && ok "foot binary present" || fail "foot not installed"
[[ -f "${FOOT_CONF_DIR}/foot.ini" ]] && ok "foot.ini deployed" || fail "foot.ini missing"
grep -q 'bobo_prompt\|__bobo_prompt' "${HOME}/.bashrc" 2>/dev/null && \
  ok "BOBO OS prompt in .bashrc" || warn ".bashrc prompt not found"
echo "  PASS: ${PASS}  FAIL: ${FAIL}"
echo "================================"
[[ "${FAIL}" -eq 0 ]]
