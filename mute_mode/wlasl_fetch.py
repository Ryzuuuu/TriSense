# mute_mode/wlasl_fetch.py
# -----------------------------------------------------------------------------
# Parallel WLASL video fetcher for the TriSense Mute Mode vocabulary.
#
# The original downloader stopped at 8 clips per word and threw the video away
# after extracting only its first 60 frames. This script instead downloads every
# reachable WLASL instance for the vocabulary into a local cache so landmarks
# can be (re)extracted with any feature recipe, and records the metadata that
# matters for a fair evaluation: the official train/val/test split, signer id,
# and the frame_start/frame_end window of the sign inside the video.
#
#   python mute_mode/wlasl_fetch.py --workers 16
#
# Output:
#   mute_mode/raw_videos/<gloss>/<video_id>.mp4     (git ignored)
#   mute_mode/raw_videos/manifest.json              one entry per saved video
# -----------------------------------------------------------------------------

import argparse
import json
import os
import subprocess
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mute_mode.config import VOCABULARY  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "WLASL_v0.3.json")
RAW_DIR = os.path.join(HERE, "raw_videos")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")
FAILED_PATH = os.path.join(RAW_DIR, "failed.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_lock = threading.Lock()


def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _looks_like_video(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) < 2048:
        return False
    with open(path, "rb") as f:
        head = f.read(64)
    # MP4/MOV ('ftyp'), WebM/MKV (EBML), FLV, AVI (RIFF)
    return b"ftyp" in head or head.startswith(b"\x1a\x45\xdf\xa3") or head.startswith(b"FLV") or head.startswith(b"RIFF")


def _download_http(url: str, out: str, timeout: int = 20) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": url})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(out, "wb") as f:
        total = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 80 * 1024 * 1024:  # a single sign clip is never this big
                raise IOError("file too large")
            f.write(chunk)
    return _looks_like_video(out)


def _download_ytdlp(url: str, out: str, timeout: int = 120) -> bool:
    cmd = [
        sys.executable, "-m", "yt_dlp", "--quiet", "--no-warnings", "--no-playlist",
        "--socket-timeout", "15", "--retries", "2",
        # video only is enough (no audio needed) and avoids needing ffmpeg to merge streams
        "-f", "bv*[height<=480][ext=mp4]/bv*[height<=480]/b[height<=480]/bv*/b",
        "-o", out, url,
    ]
    subprocess.run(cmd, timeout=timeout, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _looks_like_video(out)


# Hosts that moved since WLASL was published (same files, new address with a valid certificate)
HOST_REWRITES = {
    "https://aslsignbank.haskins.yale.edu/": "https://aslsignbank.com/",
    "http://aslsignbank.haskins.yale.edu/": "https://aslsignbank.com/",
}


def fetch_one(gloss: str, inst: dict) -> dict:
    url = inst.get("url", "")
    for old, new in HOST_REWRITES.items():
        if url.startswith(old):
            url = new + url[len(old):]
    vid = inst["video_id"]
    out_dir = os.path.join(RAW_DIR, gloss)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{vid}.mp4")
    meta = {
        "gloss": gloss,
        "video_id": vid,
        "path": os.path.relpath(out, RAW_DIR).replace("\\", "/"),
        "split": inst.get("split"),
        "signer_id": inst.get("signer_id"),
        "frame_start": inst.get("frame_start", 1),
        "frame_end": inst.get("frame_end", -1),
        "fps": inst.get("fps", 25),
        "source": inst.get("source"),
        "url": url,
    }
    if _looks_like_video(out):
        return {**meta, "ok": True, "cached": True}
    if not url or ".swf" in url.lower():
        return {**meta, "ok": False, "error": "swf/empty"}
    try:
        ok = _download_ytdlp(url, out) if _is_youtube(url) else _download_http(url, out)
        if not ok and not _is_youtube(url):
            # some hosts serve HTML wrappers; yt-dlp's generic extractor can often resolve them
            if os.path.exists(out):
                os.remove(out)
            ok = _download_ytdlp(url, out, timeout=60)
    except Exception as e:  # network errors, 404s, timeouts
        ok = False
        err = f"{type(e).__name__}: {e}"[:160]
    else:
        err = None if ok else "not a video"
    if not ok and os.path.exists(out):
        try:
            os.remove(out)
        except OSError:
            pass
    return {**meta, "ok": ok, **({"error": err} if err else {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--retry-failed", action="store_true", help="also retry instances that failed before")
    args = ap.parse_args()

    with open(INDEX_PATH, encoding="utf-8") as f:
        index = {e["gloss"]: e for e in json.load(f)}

    os.makedirs(RAW_DIR, exist_ok=True)
    manifest = {}
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = {m["video_id"]: m for m in json.load(f)}
    failed = {}
    if os.path.exists(FAILED_PATH) and not args.retry_failed:
        with open(FAILED_PATH, encoding="utf-8") as f:
            failed = json.load(f)

    jobs = []
    for gloss in VOCABULARY:
        for inst in index[gloss]["instances"]:
            vid = inst["video_id"]
            if vid in manifest or vid in failed:
                continue
            jobs.append((gloss, inst))
    print(f"[FETCH] {len(manifest)} cached, {len(failed)} known failures, {len(jobs)} to try")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(fetch_one, g, i) for g, i in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            with _lock:
                done += 1
                if r["ok"]:
                    manifest[r["video_id"]] = {k: v for k, v in r.items() if k not in ("ok", "cached", "error")}
                else:
                    failed[r["video_id"]] = r.get("error", "?")
                if done % 25 == 0 or done == len(jobs):
                    print(f"[FETCH] {done}/{len(jobs)}  ok={len(manifest)}  failed={len(failed)}", flush=True)
                    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                        json.dump(list(manifest.values()), f, indent=1)
                    with open(FAILED_PATH, "w", encoding="utf-8") as f:
                        json.dump(failed, f, indent=1)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(list(manifest.values()), f, indent=1)
    with open(FAILED_PATH, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=1)
    per_word = {g: 0 for g in VOCABULARY}
    for m in manifest.values():
        per_word[m["gloss"]] += 1
    counts = sorted(per_word.values())
    print(f"[FETCH] done. videos={len(manifest)}  min/median/max per word = {counts[0]}/{counts[len(counts)//2]}/{counts[-1]}")


if __name__ == "__main__":
    main()
