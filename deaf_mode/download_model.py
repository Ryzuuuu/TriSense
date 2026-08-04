# deaf_mode/download_model.py
# -----------------------------------------------------------------------------
# Automated Model Downloader for TriSense Deaf Mode (Vosk ASR).
# Downloads vosk-model-small-en-us (~40MB) from official Alpha Cephei repository
# and unpacks it to 'models/vosk-model-small-en-us'.
# -----------------------------------------------------------------------------

import os
import sys
import urllib.request
import zipfile
import shutil

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "vosk-model-small-en-us")
TEMP_ZIP = os.path.join(MODEL_DIR, "vosk_model.zip")


def download_progress(count, block_size, total_size):
    percent = int(count * block_size * 100 / total_size)
    if percent % 10 == 0 and percent <= 100:
        sys.stdout.write(f"\r[DOWNLOAD] Downloading Vosk model... {percent}%")
        sys.stdout.flush()


def ensure_vosk_model():
    if os.path.exists(MODEL_PATH) and len(os.listdir(MODEL_PATH)) > 0:
        print(f"[MODEL_CHECK] Vosk model already exists at: '{MODEL_PATH}' [PASS]")
        return MODEL_PATH

    print(f"[MODEL_CHECK] Vosk model not found at '{MODEL_PATH}'. Starting download from {MODEL_URL}...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    try:
        urllib.request.urlretrieve(MODEL_URL, TEMP_ZIP, reporthook=download_progress)
        print("\n[DOWNLOAD] Download complete. Extracting model archive...")
        
        with zipfile.ZipFile(TEMP_ZIP, "r") as zip_ref:
            zip_ref.extractall(MODEL_DIR)
            
        extracted_dir = os.path.join(MODEL_DIR, "vosk-model-small-en-us-0.15")
        if os.path.exists(extracted_dir):
            if os.path.exists(MODEL_PATH):
                shutil.rmtree(MODEL_PATH)
            os.rename(extracted_dir, MODEL_PATH)
            
        if os.path.exists(TEMP_ZIP):
            os.remove(TEMP_ZIP)
            
        print(f"[MODEL_CHECK] Vosk model successfully extracted to '{MODEL_PATH}' [PASS]")
        return MODEL_PATH
    except Exception as e:
        print(f"\n[ERROR] Failed to download or extract Vosk model: {e}")
        if os.path.exists(TEMP_ZIP):
            os.remove(TEMP_ZIP)
        return None


if __name__ == "__main__":
    path = ensure_vosk_model()
    sys.exit(0 if path else 1)
