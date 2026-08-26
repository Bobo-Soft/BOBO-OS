#!/bin/bash
# Faza 16 heavy payload: install Coqui TTS (SKIP_HEAVY=0) into the voice venv.
# Best-effort and time-boxed; espeak-ng remains the fallback if this fails.
# Ollama model pulls (phi3:mini/llava) are NOT done here: they need a running
# Ollama server (not installed in the rootfs) and would add ~7 GB.
R="/root/bobo-rootfs"
mount -t proc proc "$R/proc" 2>/dev/null || true
mount --rbind /dev "$R/dev" 2>/dev/null || true
cp -f /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || true
cleanup(){ for m in dev sys proc; do umount -l "$R/$m" 2>/dev/null; done; }
trap cleanup EXIT

echo "=== installing Coqui TTS into voice venv (best-effort) ==="
chroot "$R" /usr/share/bobo-voice/venv/bin/pip install --quiet coqui-tts 2>&1 | tail -6 || \
chroot "$R" /usr/share/bobo-voice/venv/bin/pip install --quiet TTS 2>&1 | tail -6 || echo "TTS install failed (espeak-ng remains)"

echo -n "=== Coqui import test: "
chroot "$R" /usr/share/bobo-voice/venv/bin/python3 -c "import TTS; print('coqui-tts OK')" 2>&1 | tail -1

# refresh the office venv's TTS too (avatar narration) - shares torch cache
chroot "$R" /usr/share/bobo-office/venv/bin/pip install --quiet coqui-tts 2>&1 | tail -2 || true

chroot "$R" bash -c "apt-get clean 2>/dev/null; find / -name '*.pyc' -delete 2>/dev/null; rm -rf /root/.cache/pip 2>/dev/null" || true
echo "=== rootfs size: $(du -sh $R 2>/dev/null | cut -f1) ==="
echo "DONE"
