# mute_mode/dataset_downloader.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode: WLASL Dataset Downloader & Landmark Extraction Engine.
#
# Implements priority-based WLASL video downloading (Direct MP4 -> YouTube yt-dlp)
# with .swf filtering, real 3D MediaPipe landmark extraction, EMA smoothing,
# 30-frame sequence buffering, and (30, 126) tensor persistence.
# -----------------------------------------------------------------------------

import os
import sys
import json
import shutil
import urllib.request
import numpy as np
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mute_mode.config import VOCABULARY, SEQ_LENGTH, FEATURE_DIM
from mute_mode.landmark_extractor import LandmarkExtractor
from mute_mode.sequence_buffer import GestureSequenceBuffer
from mute_mode.classifier import extract_sequence_tensor
from mute_mode.video_stream import VideoStreamer

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

WLASL_INDEX_URL = "https://raw.githubusercontent.com/dxli94/WLASL/master/start_kit/WLASL_v0.3.json"
DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WLASL_v0.3.json")
DEFAULT_DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")
DEFAULT_TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_videos")

MAX_CLIPS_PER_WORD = 8


def fetch_wlasl_index(cache_path: str = DEFAULT_CACHE_PATH) -> List[Dict[str, Any]]:
    """
    Downloads WLASL_v0.3.json from official repository or loads from local cache.
    """
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"[WLASL_AUDIT] Downloading WLASL_v0.3.json from official repository...")
    req = urllib.request.Request(
        WLASL_INDEX_URL,
        headers={"User-Agent": "TriSense-Research-Bot/1.0 (Academic Assistive Research)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return data


def prioritize_instances(instances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sorts WLASL video instances by user priority:
    1. Direct MP4 hosts (s3 buckets, spreadthesign, asldeafined, signstock, etc.)
    2. YouTube via yt-dlp (last resort)
    - Skips .swf links entirely (Flash, dead format)
    """
    priority1_mp4 = []
    priority2_yt = []

    for inst in instances:
        url = inst.get("url", "")
        if not url:
            continue
        # Skip Flash SWF links entirely
        if url.lower().endswith(".swf") or ".swf" in url.lower():
            continue

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if "youtube.com" in domain or "youtu.be" in domain:
            priority2_yt.append(inst)
        else:
            # Direct MP4 / non-YouTube sources
            priority1_mp4.append(inst)

    return priority1_mp4 + priority2_yt


def download_video_clip(url: str, output_path: str) -> bool:
    """
    Downloads video clip to output_path.
    Uses direct HTTP stream for MP4 links, or yt-dlp for YouTube URLs.
    Returns True if downloaded successfully and file exists > 0 bytes.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if "youtube.com" in domain or "youtu.be" in domain:
            if not HAS_YTDLP:
                return False
            import subprocess
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--quiet", "--no-warnings", "--socket-timeout", "15",
                "-f", "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", output_path,
                url
            ]
            try:
                subprocess.run(cmd, timeout=45, check=True)
            except subprocess.TimeoutExpired:
                print(f"DOWNLOAD TIMEOUT for {url}: Exceeded 45 seconds.")
                return False
            except subprocess.CalledProcessError:
                return False
        else:
            # Direct HTTP / MP4 stream
            import time
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=15) as resp:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f_out:
                    while True:
                        if time.time() - start_time > 45:
                            raise TimeoutError("MP4 download exceeded 45s")
                        chunk = resp.read(16384)
                        if not chunk:
                            break
                        f_out.write(chunk)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return True
        return False
    except Exception as e:
        print(f"DOWNLOAD ERROR for {url}: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        return False


def extract_landmarks_from_video(video_path: str) -> np.ndarray:
    """
    Opens video_path, extracts 21 3D MediaPipe hand keypoints per frame,
    applies EMA smoothing and 30-frame sequence buffering, and returns a
    (30, 126) float32 numpy array.
    """
    streamer = VideoStreamer(video_path=video_path, use_mock=True)
    extractor = LandmarkExtractor()
    buffer = GestureSequenceBuffer(window_size=SEQ_LENGTH)

    frames_processed = 0
    while True:
        ret, frame_bgr = streamer.read()
        if not ret or frame_bgr is None:
            break

        landmarks_dict = extractor.extract(frame_bgr)
        buffer.add_frame(landmarks_dict)
        frames_processed += 1

        # Avoid reading indefinitely long clips; 60 frames (~2 sec) is ample for gesture capture
        if frames_processed >= 60:
            break

    streamer.release()
    extractor.close()

    if frames_processed < 5:
        return None

    seq_dict = buffer.get_sequence()
    tensor_pt = extract_sequence_tensor(seq_dict)
    arr = tensor_pt.squeeze(0).cpu().numpy()  # shape (30, 126)

    # Validate shape and integrity
    if arr.shape != (SEQ_LENGTH, FEATURE_DIM):
        return None
    if np.isnan(arr).any() or np.isinf(arr).any():
        return None

    return arr


def run_bulk_download_pipeline(
    vocabulary: List[str] = VOCABULARY,
    max_clips: int = MAX_CLIPS_PER_WORD,
    dataset_dir: str = DEFAULT_DATASET_DIR,
    tmp_dir: str = DEFAULT_TMP_DIR,
) -> Dict[str, int]:
    """
    Executes bulk downloading and landmark extraction across the 12-word vocabulary.
    Returns dictionary mapping each word to the number of valid (30, 126) tensors saved.
    """
    wlasl_data = fetch_wlasl_index()
    gloss_map = {entry.get("gloss", "").lower(): entry for entry in wlasl_data}

    os.makedirs(dataset_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    results = {}

    print("\n" + "=" * 80)
    print(f" TriSense Mute Mode: Bulk Dataset Downloader (Target: {max_clips} Clips/Word)")
    print("=" * 80)

    for word in vocabulary:
        word_dir = os.path.join(dataset_dir, word)
        os.makedirs(word_dir, exist_ok=True)
        
        saved_count = len([f for f in os.listdir(word_dir) if f.endswith('.npy')])
        if saved_count >= max_clips:
            print(f"   [{word:<10}] Already has {saved_count} samples. Skipping.")
            results[word] = saved_count
            continue

        w_lower = word.lower()
        if w_lower not in gloss_map:
            print(f"   [{word:<10}] MISSING in WLASL -> 0 samples saved.")
            results[word] = 0
            continue

        instances = gloss_map[w_lower].get("instances", [])
        sorted_instances = prioritize_instances(instances)

        print(f"   [{word:<10}] Found {len(sorted_instances)} eligible instances. Resuming from {saved_count}...")

        for idx, inst in enumerate(sorted_instances):
            if saved_count >= max_clips:
                break

            url = inst.get("url", "")
            inst_id = inst.get("video_id", f"inst_{idx}")
            tmp_video_path = os.path.join(tmp_dir, f"{word}_{inst_id}.mp4")

            # Try downloading
            if not download_video_clip(url, tmp_video_path):
                continue

            # Try extracting landmarks
            tensor_arr = extract_landmarks_from_video(tmp_video_path)
            if os.path.exists(tmp_video_path):
                try:
                    os.remove(tmp_video_path)
                except OSError:
                    pass

            if tensor_arr is not None:
                out_npy_path = os.path.join(word_dir, f"sample_{saved_count:02d}.npy")
                np.save(out_npy_path, tensor_arr)
                saved_count += 1

        print(f"              -> Saved {saved_count} labeled (30, 126) tensors to dataset/{word}/")
        results[word] = saved_count

    # Cleanup temporary directory
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("-" * 80)
    print(" Final Per-Word WLASL Sample Counts:")
    total_samples = 0
    for word in vocabulary:
        count = results.get(word, 0)
        total_samples += count
        print(f"   • {word:<15}: {count} samples")
    print("-" * 80)
    print(f" Total Real Labeled Tensors Extracted: {total_samples}")
    print("=" * 80)

    return results


def main():
    import socket
    socket.setdefaulttimeout(15.0)
    
    WEAK_WORDS = [
        "bed", "cut", "inform", "last", "close", "copy", "crash", "order", "tell",
        "big", "careful", "cat", "cheat", "country", "cry", "delay", "improve", "show", "take", "theory", "thursday",
        "balance", "banana", "bar", "beard", "because", "black", "blanket", "blue", "call", "catch", "convince", "corn", 
        "daughter", "fine", "full", "help", "party", "score", "secretary", "soon", "sweet", "walk", "year"
    ]
    
    results = run_bulk_download_pipeline(vocabulary=WEAK_WORDS)
    print("[INFO] Bulk dataset download and landmark extraction pipeline complete.")


if __name__ == "__main__":
    main()
