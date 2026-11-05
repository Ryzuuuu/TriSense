import os
import sys
import threading
import time
from flask import Flask, render_template
from flask_socketio import SocketIO

# Ensure the root directory is in the Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from shared.mode_manager import ModeManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'trisense_secret'
socketio = SocketIO(app, async_mode='threading')

print("[EMULATOR] Instantiating the REAL ModeManager...")
manager = ModeManager()

# --- Emulator WebSocket Callbacks ---
def on_caption_update(text_lines):
    # Depending on how the formatter passes data (array of lines or string)
    if isinstance(text_lines, list):
        text = "\n".join(text_lines)
    else:
        text = str(text_lines)
    socketio.emit('deaf_caption', {'text': text})

def on_telemetry(label, distance, ttc, duration):
    socketio.emit('blind_telemetry', {'label': label, 'distance': distance, 'ttc': ttc, 'duration': duration})

def on_prediction(word, confidence):
    socketio.emit('mute_prediction', {'word': word, 'confidence': confidence})

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    print("[EMULATOR] Web UI Connected.")
    broadcast_state()

@socketio.on('disconnect')
def handle_disconnect():
    print("[EMULATOR] Web UI Disconnected.")

@socketio.on('request_mode_switch')
def handle_mode_switch(data):
    new_mode = data.get('mode', 'IDLE')
    print(f"[EMULATOR] UI Requested Mode Switch to: {new_mode}")
    try:
        # Pass callbacks into the kwargs. The modified adapters will catch them.
        if new_mode == "DEAF":
            wav_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "deaf_mode", "real_speech.wav"))
            manager.switch_mode(new_mode, wav_path=wav_path, use_mock=True, on_caption_update=on_caption_update)
        elif new_mode == "MUTE":
            # Force use_mock=True in emulator so it streams the mock video and emits prediction
            manager.switch_mode(new_mode, use_mock=True, on_prediction=on_prediction)
        elif new_mode == "BLIND":
            manager.switch_mode(new_mode, on_telemetry=on_telemetry)
        else:
            manager.switch_mode(new_mode)
    except Exception as e:
        print(f"[EMULATOR] Switch failed: {e}")
        socketio.emit('error', {'message': str(e)})
    broadcast_state()

# --- Background Sync Thread ---
def background_poller():
    """Polls ModeManager state and ResourceGuard owners, broadcasting to UI."""
    while True:
        time.sleep(0.5)
        broadcast_state()

def broadcast_state():
    owners = manager.resource_guard._owners.copy()
    state = {
        'mode': manager.current_mode,
        'resources': {
            'SPEAKER': owners.get('SPEAKER', 'IDLE'),
            'CAMERA': owners.get('CAMERA', 'IDLE'),
            'MICROPHONE': owners.get('MICROPHONE', 'IDLE'),
            'DISPLAY': owners.get('DISPLAY', 'IDLE'),
            'GPIO_SENSORS': owners.get('GPIO_SENSORS', 'IDLE'),
            'GPIO_MOTORS': owners.get('GPIO_MOTORS', 'IDLE')
        }
    }
    socketio.emit('system_state', state)

if __name__ == '__main__':
    print("[EMULATOR] Starting TriSense Emulator Server on http://localhost:5000")
    threading.Thread(target=background_poller, daemon=True).start()
    socketio.run(app, host='127.0.0.1', port=5000, allow_unsafe_werkzeug=True)
