"""
BoboPresent video exporter — render slides to MP4 (1080p / 4K) or WebM via ffmpeg,
applying xfade transitions between slides.
"""
import os
import shutil
import subprocess
from present.animation_engine import xfade_name

RES = {"1080p": "1920:1080", "4k": "3840:2160", "720p": "1280:720"}


def export(slide_images, out_path: str, seconds_per_slide=4, resolution="1080p",
           transition="fade", fmt=None) -> bool:
    """Render a list of slide PNGs to a video with transitions."""
    if not shutil.which("ffmpeg") or not slide_images:
        return False
    scale = RES.get(resolution, RES["1080p"])
    fmt = fmt or os.path.splitext(out_path)[1].lstrip(".") or "mp4"
    try:
        if len(slide_images) == 1 or transition == "none":
            concat = out_path + ".txt"
            with open(concat, "w") as fh:
                for img in slide_images:
                    fh.write("file '%s'\nduration %d\n" % (os.path.abspath(img), seconds_per_slide))
                fh.write("file '%s'\n" % os.path.abspath(slide_images[-1]))
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat,
                   "-vf", "scale=%s,format=yuv420p" % scale, "-c:v",
                   "libvpx-vp9" if fmt == "webm" else "libx264", out_path]
            subprocess.run(cmd, capture_output=True, timeout=900)
            os.remove(concat)
        else:
            # xfade chain
            xf = xfade_name(transition)
            inputs = []
            for img in slide_images:
                inputs += ["-loop", "1", "-t", str(seconds_per_slide), "-i", img]
            fc = []
            for i in range(len(slide_images)):
                fc.append("[%d:v]scale=%s,format=yuv420p,setsar=1[v%d]" % (i, scale, i))
            chain = "[v0]"
            offset = seconds_per_slide - 1
            for i in range(1, len(slide_images)):
                out = "[x%d]" % i
                fc.append("%s[v%d]xfade=transition=%s:duration=1:offset=%d%s"
                          % (chain, i, xf, offset * i, out if i < len(slide_images) - 1 else "[vout]"))
                chain = out if i < len(slide_images) - 1 else "[vout]"
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(fc),
                   "-map", "[vout]", "-c:v", "libvpx-vp9" if fmt == "webm" else "libx264", out_path]
            subprocess.run(cmd, capture_output=True, timeout=1200)
        return os.path.exists(out_path)
    except Exception as e:
        print("[video_exporter] %s" % e)
        return False
