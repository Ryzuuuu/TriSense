# mute_mode/eval_live.py
# -----------------------------------------------------------------------------
# Streams held out WLASL test videos frame by frame through LiveSignRecognizer,
# exactly as a camera would feed it (sign segmentation included), and reports
# how often the spoken word is correct. This checks the live path, not just
# offline accuracy.
#
#   python mute_mode/eval_live.py --limit 60
# -----------------------------------------------------------------------------

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    import cv2
    from mute_mode.recognizer import LiveSignRecognizer

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--checkpoint", default=os.path.join(HERE, "checkpoints", "sign_v2.pth"))
    args = ap.parse_args()

    with open(os.path.join(HERE, "raw_videos", "manifest.json"), encoding="utf-8") as f:
        manifest = [m for m in json.load(f) if m["split"] == "test"]
    # skip clips cut from long videos: a camera never sees those boundaries
    manifest = [m for m in manifest if m.get("frame_end", -1) == -1][: args.limit]

    n = correct = top3 = accepted = accepted_ok = no_pred = 0
    t_frames = t_total = 0.0
    for m in manifest:
        rec = LiveSignRecognizer(args.checkpoint, conf_threshold=0.45)
        cap = cv2.VideoCapture(os.path.join(HERE, "raw_videos", m["path"]))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        preds, i = [], 0
        t0 = time.perf_counter()
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            p = rec.process_frame(frame, timestamp_s=i / fps)
            i += 1
            if p:
                preds.append(p)
        # end of clip: a real signer lowers their hands; flush with blank frames
        blank = frame * 0 if frame is not None else None
        for k in range(12):
            p = rec.process_frame(blank, timestamp_s=(i + k) / fps)
            if p:
                preds.append(p)
        t_total += time.perf_counter() - t0
        t_frames += i
        cap.release()
        rec.close()
        n += 1
        if not preds:
            no_pred += 1
            continue
        best = max(preds, key=lambda q: q["frames"])  # the main sign is the longest segment
        hit = best["label"] == m["gloss"]
        correct += hit
        top3 += m["gloss"] in [w for w, _ in best["top_k"]]
        if best["accepted"]:
            accepted += 1
            accepted_ok += hit
    print(f"[LIVE] clips={n}  top1={correct / n:.1%}  top3={top3 / n:.1%}  no_segment={no_pred}")
    if accepted:
        print(f"[LIVE] spoken (conf>=0.45): {accepted}/{n} clips, of which correct {accepted_ok / accepted:.1%}")
    print(f"[LIVE] processing speed on this machine: {t_frames / t_total:.1f} frames/s")


if __name__ == "__main__":
    main()
