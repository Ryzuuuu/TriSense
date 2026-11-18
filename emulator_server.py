# emulator_server.py
# -----------------------------------------------------------------------------
# TriSense demo console. Drives the REAL ModeManager and the real Blind, Deaf
# and Mute pipelines from a browser, with live inputs:
#
#   Blind : move the left / center / right obstacles (or run scripted scenarios);
#           the mock GPIO echoes those distances to the real HC-SR04 driver.
#   Deaf  : the browser microphone is streamed as 16 kHz PCM to the real Vosk
#           recogniser, or a recorded sample sentence is played.
#   Mute  : webcam frames, or frames from held out WLASL test videos, are sent
#           to the real sign recogniser; landmarks and predictions come back.
#
# Every phrase the device would speak is sent to the browser, which reads it
# aloud, and ResourceGuard ownership is shown live.
#
# Run:  python emulator_server.py   ->   http://127.0.0.1:5000
# -----------------------------------------------------------------------------

import atexit
import json
import os
import sys
import threading
import time

os.environ.setdefault("TRISENSE_TTS_CONSOLE", "1")  # the browser speaks; avoid double audio on the laptop

# The pipelines print non ASCII symbols (arrows, degree signs). On a Windows console
# with a legacy code page that raised UnicodeEncodeError and aborted mode switches.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from flask import Flask, abort, jsonify, render_template, send_from_directory  # noqa: E402
from flask_socketio import SocketIO  # noqa: E402

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from shared import tts_output  # noqa: E402
from shared.mode_manager import ModeManager, _ensure_headless_compat  # noqa: E402

app = Flask(__name__)
# Local-only dev server: override with TRISENSE_SECRET_KEY if you expose it.
app.config["SECRET_KEY"] = os.getenv("TRISENSE_SECRET_KEY") or os.urandom(16).hex()
socketio = SocketIO(app, async_mode="threading", max_http_buffer_size=4 * 1024 * 1024)

print("[EMULATOR] Instantiating the REAL ModeManager...")
manager = ModeManager()
atexit.register(manager.shutdown)

_ensure_headless_compat()
import RPi.GPIO  # noqa: E402,F401  (resolves to the bundled mock on a PC)
try:
    import mock_gpio  # the module behind the RPi.GPIO shim
except ImportError:
    mock_gpio = None

RAW_DIR = os.path.join(ROOT, "mute_mode", "raw_videos")
SAMPLE_WAV = os.path.join(ROOT, "deaf_mode", "real_speech.wav")

_state_lock = threading.Lock()
_distances = {"left": 250.0, "center": 250.0, "right": 250.0}
_audio_source = None
_video_source = None
_formatter = None


def log(msg, kind="info"):
    print(f"[EMULATOR] {msg}")
    socketio.emit("log", {"t": time.strftime("%H:%M:%S"), "msg": msg, "kind": kind})


# ── speech: everything the device says is mirrored to the browser ─────────────
tts_output.add_listener(lambda text: socketio.emit("speech", {"text": text}))


# ── pipeline callbacks ────────────────────────────────────────────────────────
def on_blind_state(states, phrase):
    socketio.emit("blind_state", {
        "sensors": [{"label": s.label, "distance": s.distance, "speed": s.speed, "ttc": s.ttc,
                     "pulse": s.pulse_ms, "reason": s.reason} for s in states],
        "phrase": phrase,
    })


def on_caption_update(text, is_final=True):
    global _formatter
    if _formatter is None:
        from deaf_mode.caption_formatter import CaptionFormatter
        _formatter = CaptionFormatter(max_chars_per_line=20, max_lines=3)
    socketio.emit("deaf_caption", {
        "text": str(text), "final": bool(is_final),
        "oled": _formatter.get_display_lines(str(text), is_final=bool(is_final)),
    })


def _pts(arr, n):
    return [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in arr[:n]]


def on_mute_status(lm, recording):
    if lm is None:
        return
    socketio.emit("mute_status", {
        "recording": bool(recording),
        "pose": _pts(lm["pose"][:25], 25) if lm["pose_ok"] else None,
        "lh": _pts(lm["lh"], 21) if lm["lh_ok"] else None,
        "rh": _pts(lm["rh"], 21) if lm["rh_ok"] else None,
    })


def on_mute_detail(pred):
    socketio.emit("mute_prediction", {
        "label": pred["label"], "confidence": pred["confidence"], "accepted": bool(pred["accepted"]),
        "top_k": pred.get("top_k", []), "frames": pred.get("frames"),
    })


# ── routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/clips")
def api_clips():
    """Held out WLASL test clips available locally (only whole clips, not cuts from long videos)."""
    path = os.path.join(RAW_DIR, "manifest.json")
    if not os.path.exists(path):
        return jsonify([])
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    clips = [{"gloss": m["gloss"], "path": m["path"], "split": m["split"]}
             for m in manifest if m.get("frame_end", -1) == -1 and m["split"] == "test"
             and os.path.exists(os.path.join(RAW_DIR, m["path"]))]
    clips.sort(key=lambda c: c["gloss"])
    return jsonify(clips)


@app.route("/clips/<path:rel>")
def clip_file(rel):
    full = os.path.abspath(os.path.join(RAW_DIR, rel))
    if not full.startswith(os.path.abspath(RAW_DIR)) or not os.path.exists(full):
        abort(404)
    return send_from_directory(RAW_DIR, rel)


@app.route("/media/sample.wav")
def sample_wav():
    if not os.path.exists(SAMPLE_WAV):
        abort(404)
    return send_from_directory(os.path.dirname(SAMPLE_WAV), os.path.basename(SAMPLE_WAV))


@app.route("/api/info")
def api_info():
    mute = manager.get_pipeline("MUTE")
    meta = {}
    try:
        from mute_mode.recognizer import DEFAULT_CHECKPOINT
        if os.path.exists(DEFAULT_CHECKPOINT):
            import torch
            meta = torch.load(DEFAULT_CHECKPOINT, map_location="cpu", weights_only=False).get("metadata", {})
    except Exception:
        pass
    from deaf_mode.config import VOSK_MODEL_PATH
    return jsonify({
        "vocabulary": __import__("mute_mode.config", fromlist=["VOCABULARY"]).VOCABULARY,
        "sign_test_top1": meta.get("deploy_test_top1"), "sign_test_top5": meta.get("deploy_test_top5"),
        "vosk_model": os.path.exists(VOSK_MODEL_PATH), "sample_wav": os.path.exists(SAMPLE_WAV),
        "mute_version": getattr(mute, "version", None),
    })


# ── socket events ─────────────────────────────────────────────────────────────
@socketio.on("connect")
def handle_connect():
    broadcast_state()


@socketio.on("request_mode_switch")
def handle_mode_switch(data):
    global _audio_source, _video_source
    data = data or {}
    new_mode = str(data.get("mode", "IDLE")).upper()
    log(f"Mode switch requested: {new_mode}")
    try:
        if new_mode == "BLIND":
            if mock_gpio is not None:
                with _state_lock:
                    mock_gpio.set_distances(dict(_distances))
            manager.switch_mode("IDLE")
            manager.switch_mode("BLIND", on_state=on_blind_state)
        elif new_mode == "DEAF":
            manager.switch_mode("IDLE")
            if data.get("source") == "sample":
                _audio_source = None
                manager.switch_mode("DEAF", wav_path=SAMPLE_WAV, use_mock=True, real_time=True,
                                    mock_display=True, on_caption_update=on_caption_update)
            else:
                from deaf_mode.audio_stream import PushAudioStreamer
                _audio_source = PushAudioStreamer()
                manager.switch_mode("DEAF", audio_source=_audio_source, mock_display=True,
                                    on_caption_update=on_caption_update)
        elif new_mode == "MUTE":
            from mute_mode.video_stream import PushVideoStream
            manager.switch_mode("IDLE")
            _video_source = PushVideoStream()
            manager.switch_mode("MUTE", video_source=_video_source, on_status=on_mute_status,
                                on_prediction_detail=on_mute_detail)
            log(f"Mute Mode using recogniser {manager.get_pipeline('MUTE').version}")
        else:
            manager.switch_mode("IDLE")
            _audio_source = _video_source = None
    except Exception as e:
        log(f"Switch failed: {e}", "error")
        socketio.emit("error", {"message": str(e)})
    broadcast_state()


@socketio.on("blind_set")
def handle_blind_set(data):
    vals = {}
    for k in ("left", "center", "right"):
        if k in (data or {}):
            v = data[k]
            vals[k] = None if v is None else float(v)
    with _state_lock:
        _distances.update(vals)
    if mock_gpio is not None:
        mock_gpio.set_distances(vals, noise_cm=float((data or {}).get("noise", 0.5)))


@socketio.on("audio_chunk")
def handle_audio_chunk(data):
    src = _audio_source
    if src is not None and isinstance(data, (bytes, bytearray)):
        src.push(bytes(data))


@socketio.on("mute_frame")
def handle_mute_frame(data):
    src = _video_source
    if src is None or not isinstance(data, (bytes, bytearray)):
        return
    import cv2
    import numpy as np
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is not None:
        src.push(frame)


@socketio.on("say")
def handle_say(data):
    """Lets the UI test the speaker path through the shared TTS worker."""
    text = str((data or {}).get("text", ""))[:60]
    if text:
        tts_output.speak(text, cooldown=0.5)


# ── state broadcast ───────────────────────────────────────────────────────────
def background_poller():
    while True:
        time.sleep(0.5)
        broadcast_state()


def broadcast_state():
    owners = manager.resource_guard.snapshot()
    socketio.emit("system_state", {
        "mode": manager.current_mode,
        "resources": {r: owners.get(r, "IDLE") for r in
                      ("SPEAKER", "CAMERA", "MICROPHONE", "DISPLAY", "GPIO_SENSORS", "GPIO_MOTORS")},
    })


if __name__ == "__main__":
    print("[EMULATOR] Starting TriSense demo console on http://127.0.0.1:5000")
    threading.Thread(target=background_poller, daemon=True).start()
    socketio.run(app, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True)
