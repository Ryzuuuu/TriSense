# mute_mode/build_landmarks.py
# -----------------------------------------------------------------------------
# Extracts hands + upper body landmarks for every video fetched by
# wlasl_fetch.py, respecting each clip's WLASL frame_start/frame_end window.
#
#   python mute_mode/build_landmarks.py --workers 6
#
# Output: mute_mode/landmarks/<gloss>/<video_id>.npz  (float16, compressed)
#         mute_mode/landmarks/index.json             metadata for training
# -----------------------------------------------------------------------------

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw_videos")
OUT_DIR = os.path.join(HERE, "landmarks")


def _work(meta):
    from mute_mode.holistic import extract_video

    out = os.path.join(OUT_DIR, meta["gloss"], meta["video_id"] + ".npz")
    if os.path.exists(out):
        return meta, "cached"
    try:
        seq = extract_video(os.path.join(RAW_DIR, meta["path"]),
                            frame_start=int(meta.get("frame_start") or 1),
                            frame_end=int(meta.get("frame_end") or -1))
    except Exception as e:
        return meta, f"error: {e}"
    if seq is None:
        return meta, "unreadable or too short"
    if not (seq["lh_ok"] | seq["rh_ok"]).any():
        return meta, "no hands"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    np.savez_compressed(out, pose=seq["pose"].astype(np.float16), lh=seq["lh"].astype(np.float16),
                        rh=seq["rh"].astype(np.float16), lh_ok=seq["lh_ok"], rh_ok=seq["rh_ok"],
                        pose_ok=seq["pose_ok"], fps=seq["fps"])
    return meta, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()

    with open(os.path.join(RAW_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)
    index, problems = [], {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(_work, m) for m in manifest]
        for i, fut in enumerate(as_completed(futs), 1):
            meta, status = fut.result()
            if status in ("ok", "cached"):
                index.append({k: meta[k] for k in ("gloss", "video_id", "split", "signer_id", "source")})
            else:
                problems[meta["video_id"]] = status
            if i % 50 == 0 or i == len(futs):
                print(f"[LANDMARKS] {i}/{len(futs)}  ok={len(index)}  skipped={len(problems)}", flush=True)
    index.sort(key=lambda m: (m["gloss"], m["video_id"]))
    with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    with open(os.path.join(OUT_DIR, "skipped.json"), "w", encoding="utf-8") as f:
        json.dump(problems, f, indent=1)
    print(f"[LANDMARKS] wrote {len(index)} sequences")


if __name__ == "__main__":
    main()
