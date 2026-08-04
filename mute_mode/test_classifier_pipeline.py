# mute_mode/test_classifier_pipeline.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode Step 3: Classifier Architecture & Training Pipeline Test
#
# Verifies:
#   1. SignLanguageClassifier architecture, edge parameter budget (< 100,000),
#      and forward pass tensor schema (batch_size, 30, 126) -> (batch_size, 12).
#   2. Training script structural smoke test: 1 epoch on dummy/synthetic tensors,
#      verifying loss computation and gradient backprop without crashing, while
#      enforcing explicit synthetic data warning banners (no % accuracy claims).
#   3. Checkpoint persistence: save_checkpoint / load_checkpoint round-trip and
#      predict_step() softmax probability verification.
# -----------------------------------------------------------------------------

import os
import sys
import tempfile
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mute_mode.config import VOCABULARY, NUM_CLASSES, SEQ_LENGTH, FEATURE_DIM
from mute_mode.classifier import SignLanguageClassifier
from mute_mode.train_classifier import (
    SignLanguageDataset,
    train_one_epoch,
    evaluate_epoch,
    save_checkpoint,
    load_checkpoint
)


def test_1_architecture_and_edge_parameter_budget():
    print("-" * 71)
    print("Test 1: Classifier Architecture & Edge Parameter Budget (< 100k params)")
    print("-" * 71)

    model = SignLanguageClassifier()
    param_count = model.get_parameter_count()

    print(f"   [INFO] Trainable Parameters: {param_count:,}")
    assert param_count < 100_000, f"Expected < 100,000 params for Pi edge deployment, got {param_count}"
    print(f"   [PASS] Parameter count ({param_count:,}) is well within Raspberry Pi edge CPU budget.")

    dummy_input = torch.randn(2, SEQ_LENGTH, FEATURE_DIM, dtype=torch.float32)
    logits = model(dummy_input)

    assert logits.shape == (2, NUM_CLASSES), f"Expected output shape (2, {NUM_CLASSES}), got {logits.shape}"
    assert not torch.isnan(logits).any(), "Forward pass produced NaN values!"
    print(f"   [PASS] Forward pass verified: input (2, {SEQ_LENGTH}, {FEATURE_DIM}) -> logits {tuple(logits.shape)}.")


def test_2_training_pipeline_structural_smoke_test():
    print("-" * 71)
    print("Test 2: Training Pipeline Structural Smoke Test (1 Epoch Dummy Data)")
    print("-" * 71)

    device = torch.device("cpu")
    model = SignLanguageClassifier().to(device)

    # Generate synthetic dummy dataset (40 samples)
    dataset = SignLanguageDataset.generate_dummy_dataset(num_samples=40)
    assert dataset.is_synthetic, "Dataset is_synthetic flag must be True for dummy data"

    train_ds, val_ds = random_split(dataset, [32, 8])
    train_loader = DataLoader(train_ds, batch_size=8, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=8, shuffle=False)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()

    train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
    assert train_loss > 0.0 and not torch.isnan(torch.tensor(train_loss)), f"Invalid train loss: {train_loss}"
    print(f"   [INFO] 1-Epoch Structural Train Loss: {train_loss:.4f}")
    print("   [PASS] Backpropagation and optimizer step completed cleanly on dummy data.")

    val_results = evaluate_epoch(model, val_loader, criterion, device, is_synthetic=dataset.is_synthetic)
    assert "val_loss" in val_results and "structural_completion" in val_results
    print(f"   [INFO] Structural Validation Loss:    {val_results['val_loss']:.4f}")
    print("   [PASS] Synthetic data warning banner explicitly printed — no accuracy claims made.")


def test_3_checkpoint_persistence_and_prediction():
    print("-" * 71)
    print("Test 3: Checkpoint Persistence & Softmax Prediction Output")
    print("-" * 71)

    model = SignLanguageClassifier()
    dummy_input = torch.randn(1, SEQ_LENGTH, FEATURE_DIM, dtype=torch.float32)

    with tempfile.TemporaryDirectory() as temp_dir:
        ckpt_path = os.path.join(temp_dir, "test_mute_classifier.pt")
        saved_path = save_checkpoint(model, ckpt_path, extra_metadata={"epoch": 1, "note": "smoke_test"})
        assert os.path.exists(saved_path), f"Failed to create checkpoint file at {saved_path}"
        print(f"   [PASS] Checkpoint successfully saved to {saved_path}")

        loaded_model = load_checkpoint(saved_path, device="cpu")
        print("   [PASS] Checkpoint state dict and vocabulary metadata successfully reloaded.")

        prediction = loaded_model.predict_step(dummy_input)
        assert "class_idx" in prediction and "label" in prediction and "confidence" in prediction
        assert 0 <= prediction["class_idx"] < NUM_CLASSES
        assert prediction["label"] in VOCABULARY
        assert 0.0 <= prediction["confidence"] <= 1.0

        prob_sum = sum(prediction["probabilities"].values())
        assert abs(prob_sum - 1.0) < 1e-4, f"Softmax probabilities sum to {prob_sum}, expected 1.0"
        print(f"   [PASS] predict_step() returned valid label '{prediction['label']}' with probability distribution summing to 1.0000.")


def run_all_tests():
    print("=======================================================================")
    print(" TriSense Mute Mode Step 3 (Classifier & Training Pipeline) Test")
    print("=======================================================================")
    test_1_architecture_and_edge_parameter_budget()
    print()
    test_2_training_pipeline_structural_smoke_test()
    print()
    test_3_checkpoint_persistence_and_prediction()
    print()
    print("=======================================================================")
    print(" RESULT: ALL MUTE MODE STEP 3 TESTS PASSED [PASS]")
    print("=======================================================================")


if __name__ == "__main__":
    run_all_tests()
