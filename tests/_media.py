"""What a video file holds, read from ffmpeg's own report, so tests do not need ffprobe (the ffmpeg that
comes with imageio-ffmpeg has no ffprobe)."""
import re
import subprocess


def media_info(path) -> dict:
    from sciview.export import find_ffmpeg
    err = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, encoding="utf-8",
                         errors="replace").stderr
    info = {"duration": None, "chapters": [], "streams": []}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    for line in err.splitlines():
        s = line.strip()
        c = re.match(r"Chapter #\d+:\d+: start (-?[\d.]+), end (-?[\d.]+)", s)
        if c:
            info["chapters"].append({"start": float(c[1]), "end": float(c[2]), "title": None})
            continue
        t = re.match(r"title\s*: (.*)", s)
        if t and info["chapters"] and not info["streams"] and info["chapters"][-1]["title"] is None:
            info["chapters"][-1]["title"] = t[1].strip()
            continue
        st = re.match(r"Stream #\d+:\d+.*?: (Video|Audio|Subtitle|Data): (\w+)(.*)", s)
        if st:
            d = {"type": st[1].lower(), "codec": st[2]}
            if d["type"] == "video":
                pf = re.match(r"[^,]*, (\w+)", st[3])
                wh = re.search(r", (\d+)x(\d+)", st[3])
                d["pix_fmt"] = pf[1] if pf else None
                d["size"] = (int(wh[1]), int(wh[2])) if wh else None
            info["streams"].append(d)
    return info


def video(info: dict) -> dict:
    return next(s for s in info["streams"] if s["type"] == "video")
