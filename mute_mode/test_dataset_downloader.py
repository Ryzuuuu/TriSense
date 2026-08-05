# mute_mode/test_dataset_downloader.py
# -----------------------------------------------------------------------------
# Verification Test Suite for WLASL Dataset Downloader & Landmark Extractor
# -----------------------------------------------------------------------------

import os
import sys
import unittest
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mute_mode.config import VOCABULARY, SEQ_LENGTH, FEATURE_DIM
from mute_mode.dataset_downloader import (
    prioritize_instances,
    fetch_wlasl_index,
    DEFAULT_DATASET_DIR
)


class TestDatasetDownloader(unittest.TestCase):
    def test_01_instance_prioritization_and_swf_filtering(self):
        """
        Verifies that .swf links are skipped entirely, direct MP4 links come first,
        and YouTube links come last.
        """
        dummy_instances = [
            {"url": "http://www.aslpro.com/main/t/thankyou.swf", "video_id": "01"},
            {"url": "https://www.youtube.com/watch?v=12345", "video_id": "02"},
            {"url": "https://s3-us-west-1.amazonaws.com/media.asldeafined.com/water.mp4", "video_id": "03"},
            {"url": "http://www.aslpro.com/hello.swf", "video_id": "04"},
            {"url": "https://media.spreadthesign.com/video/mp4/13/123.mp4", "video_id": "05"},
        ]

        sorted_inst = prioritize_instances(dummy_instances)
        urls = [inst["url"] for inst in sorted_inst]

        # Ensure no .swf or youtube in sorted_inst
        self.assertFalse(any(".swf" in u.lower() for u in urls), "SWF links were not filtered out!")
        self.assertFalse(any("youtube.com" in u.lower() or "youtu.be" in u.lower() for u in urls), "YouTube links were not filtered out!")
        # Ensure direct MP4 links are returned
        self.assertEqual(urls[0], "https://s3-us-west-1.amazonaws.com/media.asldeafined.com/water.mp4")
        self.assertEqual(urls[1], "https://media.spreadthesign.com/video/mp4/13/123.mp4")
        self.assertEqual(len(urls), 2)
        print("   [PASS] Instance prioritization correctly kept only direct MP4 links and dropped SWF/YouTube.")

    def test_02_index_coverage_audit(self):
        """
        Verifies that WLASL index parses cleanly and covers the 12 vocabulary words.
        """
        wlasl_data = fetch_wlasl_index()
        gloss_map = {entry.get("gloss", "").lower(): entry for entry in wlasl_data}

        covered = 0
        for word in VOCABULARY:
            if word.lower() in gloss_map:
                covered += 1

        self.assertEqual(covered, len(VOCABULARY), f"Expected {len(VOCABULARY)} words covered, found {covered}")
        print(f"   [PASS] Verified index coverage: {covered}/{len(VOCABULARY)} vocabulary words present in WLASL.")

    def test_03_saved_dataset_tensor_invariants(self):
        """
        Verifies that any generated .npy files in mute_mode/dataset/ match the
        (30, 126) float32 schema without NaN or Inf values.
        """
        if not os.path.exists(DEFAULT_DATASET_DIR):
            print("   [INFO] No dataset directory exists yet (bulk download not run). Skipping tensor inspection.")
            return

        total_tensors = 0
        for root, dirs, files in os.walk(DEFAULT_DATASET_DIR):
            for file in files:
                if file.endswith(".npy"):
                    f_path = os.path.join(root, file)
                    arr = np.load(f_path)
                    self.assertEqual(arr.shape, (SEQ_LENGTH, FEATURE_DIM), f"Invalid shape in {f_path}: {arr.shape}")
                    self.assertFalse(np.isnan(arr).any(), f"NaN values detected in {f_path}")
                    self.assertFalse(np.isinf(arr).any(), f"Inf values detected in {f_path}")
                    total_tensors += 1

        print(f"   [PASS] Checked {total_tensors} saved tensors in {DEFAULT_DATASET_DIR}: all match (30, 126) invariant.")

    def test_04_dataset_source_citation_exists(self):
        """
        Verifies that mute_mode/DATASET_SOURCE.md exists and cites WLASL & ASL Citizen.
        """
        doc_path = os.path.join(os.path.dirname(__file__), "DATASET_SOURCE.md")
        self.assertTrue(os.path.exists(doc_path), "DATASET_SOURCE.md is missing!")
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("WLASL", content)
        self.assertIn("ASL Citizen", content)
        print("   [PASS] DATASET_SOURCE.md exists and contains required citations.")


if __name__ == "__main__":
    print("=======================================================================")
    print(" TriSense Mute Mode Dataset Downloader Test Suite")
    print("=======================================================================")
    unittest.main(verbosity=0)
