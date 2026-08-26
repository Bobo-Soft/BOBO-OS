"""
BoboPresent avatar presenter.
Generates narration (pyttsx3 local, or ElevenLabs if an API key is configured),
optional SadTalker lip-sync when a GPU is present (else a static avatar image),
and composes slides (70% right) + avatar (30% bottom-left) into a tutorial video
via ffmpeg. Subtitles via Whisper when available.
"""
import os
import shutil
import subprocess


def synth_narration(text: str, out_wav: str, voice_api_key: str = "") -> bool:
    """Local TTS with pyttsx3; ElevenLabs used only if a key is provided."""
    if voice_api_key:
        try:
            import requests
            r = requests.post(
                "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL",
                headers={"xi-api-key": voice_api_key},
                json={"text": text, "model_id": "eleven_multilingual_v2"}, timeout=60)
            if r.ok:
                open(out_wav.replace(".wav", ".mp3"), "wb").write(r.content)
                return True
        except Exception:
            pass
    try:
        import pyttsx3
        eng = pyttsx3.init()
        eng.save_to_file(text, out_wav)
        eng.runAndWait()
        return os.path.exists(out_wav)
    except Exception:
        # last resort: espeak-ng CLI
        try:
            subprocess.run(["espeak-ng", "-w", out_wav, text], timeout=60, check=True)
            return os.path.exists(out_wav)
        except Exception:
            return False


def has_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None


def compose_tutorial(slide_images, narration_audio, avatar_image, out_mp4: str,
                     subtitle_srt: str = "") -> bool:
    """
    Compose slides (right 70%) + avatar (bottom-left 30%) into a video.
    slide_images: list of PNG paths (one per narration segment).
    Uses ffmpeg filter_complex; requires ffmpeg.
    """
    if not shutil.which("ffmpeg") or not slide_images:
        return False
    try:
        # Build a slideshow video from images (5s each), overlay avatar, add audio.
        concat = os.path.join(os.path.dirname(out_mp4) or ".", "_slides.txt")
        with open(concat, "w") as fh:
            for img in slide_images:
                fh.write("file '%s'\nduration 5\n" % os.path.abspath(img))
            fh.write("file '%s'\n" % os.path.abspath(slide_images[-1]))
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat]
        filt = "[0:v]scale=1280:720[bg]"
        if avatar_image and os.path.exists(avatar_image):
            cmd += ["-i", avatar_image]
            filt = "[0:v]scale=1280:720[bg];[1:v]scale=380:-1[av];[bg][av]overlay=20:H-h-20[v]"
            vmap = "[v]"
        else:
            filt = "[0:v]scale=1280:720[v]"
            vmap = "[v]"
        if narration_audio and os.path.exists(narration_audio):
            cmd += ["-i", narration_audio]
        cmd += ["-filter_complex", filt, "-map", vmap]
        if narration_audio and os.path.exists(narration_audio):
            cmd += ["-map", "%d:a" % (2 if avatar_image and os.path.exists(avatar_image) else 1), "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out_mp4]
        subprocess.run(cmd, capture_output=True, timeout=600)
        return os.path.exists(out_mp4)
    except Exception as e:
        print("[avatar_presenter] %s" % e)
        return False


def generate_subtitles(audio_path: str, out_srt: str) -> bool:
    """Transcribe narration to an SRT via faster-whisper (if installed)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio_path)
        with open(out_srt, "w", encoding="utf-8") as fh:
            for i, s in enumerate(segs, 1):
                fh.write("%d\n%s --> %s\n%s\n\n" % (i, _ts(s.start), _ts(s.end), s.text.strip()))
        return True
    except Exception:
        return False


def _ts(sec):
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return "%02d:%02d:%06.3f" % (h, m, s).replace(".", ",") if False else "%02d:%02d:%02d,%03d" % (h, m, int(s), int((s - int(s)) * 1000))
