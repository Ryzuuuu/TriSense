# mute_mode/train_classifier.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode Step 3: Training Script Structure for SignLanguageClassifier.
#
# Designed to ingest labeled (30, 126) sequence tensor datasets once recorded,
# while providing structural smoke-testing capabilities against dummy/synthetic
# tensors.
#
# IMPORTANT:
#   When evaluating on dummy/synthetic data, this script explicitly flags that
#   metrics represent structural smoke testing only and must never be interpreted
#   as real-world sign recognition accuracy.
# -----------------------------------------------------------------------------

import os
import sys
import glob
import random
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from typing import Dict, Any, Tuple, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mute_mode.config import (
    VOCABULARY,
    NUM_CLASSES,
    SEQ_LENGTH,
    FEATURE_DIM
)
from mute_mode.classifier import SignLanguageClassifier


class SignLanguageDataset(Dataset):
    """
    Dataset for sign language gesture sequence tensors (30 frames, 126 features).
    """
    def __init__(self, samples: List[Tuple[torch.Tensor, int]], is_train: bool = False, is_synthetic: bool = False):
        """
        Args:
            samples: List of (tensor_30x126, label_idx) tuples.
            is_train: Apply data augmentation if True.
            is_synthetic: Flag indicating whether data is synthetic/dummy.
        """
        self.samples = samples
        self.is_train = is_train
        self.is_synthetic = is_synthetic

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        x, y = self.samples[idx]
        if self.is_train:
            x = self._augment(x)
        return x, y

    def _augment(self, x: torch.Tensor) -> torch.Tensor:
        # 1. Jitter
        jitter = torch.randn_like(x) * 0.02
        x = x + jitter
        
        # 2. Time-warp: shift sequence forward/backward by 1-2 frames
        shift = random.randint(-2, 2)
        if shift > 0:
            x = torch.cat([torch.zeros(shift, FEATURE_DIM), x[:-shift]], dim=0)
        elif shift < 0:
            x = torch.cat([x[-shift:], torch.zeros(-shift, FEATURE_DIM)], dim=0)
            
        # 3. Mirroring (flip X, swap hands)
        if random.random() > 0.5:
            # Reshape to (30, 2 hands, 21 landmarks, 3 coords)
            x_reshaped = x.view(SEQ_LENGTH, 2, 21, 3).clone()
            x_reshaped[:, :, :, 0] *= -1.0 # flip X
            # Swap left (0) and right (1) hand indices
            x_reshaped = x_reshaped[:, [1, 0], :, :]
            x = x_reshaped.view(SEQ_LENGTH, FEATURE_DIM)
            
        return x

    @staticmethod
    def generate_dummy_dataset(num_samples: int = 100) -> "SignLanguageDataset":
        """
        Generates a synthetic/dummy dataset of random tensors for structural smoke testing.
        """
        samples = []
        for i in range(num_samples):
            # Random tensor of shape (30, 126) and random integer target in [0, NUM_CLASSES-1]
            x = torch.randn(SEQ_LENGTH, FEATURE_DIM, dtype=torch.float32)
            y = int(i % NUM_CLASSES)
            samples.append((x, y))
        return SignLanguageDataset(samples, is_synthetic=True)


def train_one_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device
) -> float:
    """
    Runs one training epoch. Returns average training loss.
    """
    model.train()
    total_loss = 0.0
    num_batches = 0

    for x_batch, y_batch in dataloader:
        x_batch = x_batch.to(device)
        y_batch = y_batch.to(device=device, dtype=torch.long)

        optimizer.zero_grad()
        logits = model(x_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        optimizer.step()

        total_loss += float(loss.item())
        num_batches += 1

    return total_loss / max(1, num_batches)


@torch.no_grad()
def evaluate_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    is_synthetic: bool = False
) -> Dict[str, float]:
    """
    Evaluates model on validation data.
    """
    model.eval()
    total_loss = 0.0
    correct = 0
    total_samples = 0
    num_batches = 0

    for x_batch, y_batch in dataloader:
        x_batch = x_batch.to(device)
        y_batch = y_batch.to(device=device, dtype=torch.long)

        logits = model(x_batch)
        loss = criterion(logits, y_batch)

        total_loss += float(loss.item())
        num_batches += 1

        preds = torch.argmax(logits, dim=-1)
        correct += int((preds == y_batch).sum().item())
        total_samples += y_batch.size(0)

    avg_loss = total_loss / max(1, num_batches)
    raw_acc = float(correct) / max(1, total_samples)

    if is_synthetic:
        print("\n" + "=" * 78)
        print(" [WARNING] STRUCTURAL SMOKE TEST ONLY (SYNTHETIC / DUMMY DATA) ")
        print(" Do NOT interpret loss or accuracy metrics as real-world sign recognition")
        print(" performance. This check verifies pipeline execution and gradient health.")
        print("=" * 78 + "\n")

    return {
        "val_loss": avg_loss,
        "structural_completion": 1.0,
        "raw_acc": raw_acc
    }


def save_checkpoint(
    model: SignLanguageClassifier,
    filepath: str,
    extra_metadata: Dict[str, Any] = None
) -> str:
    """
    Saves model checkpoint and vocabulary metadata.
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    checkpoint_data = {
        "state_dict": model.state_dict(),
        "vocabulary": VOCABULARY,
        "num_classes": NUM_CLASSES,
        "in_features": model.in_features,
        "hidden_size": model.hidden_size,
        "metadata": extra_metadata or {}
    }
    torch.save(checkpoint_data, filepath)
    return os.path.abspath(filepath)


def load_checkpoint(filepath: str, device: str = "cpu") -> SignLanguageClassifier:
    """
    Loads a SignLanguageClassifier from a saved checkpoint file.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Checkpoint not found at {filepath}")

    data = torch.load(filepath, map_location=device, weights_only=False)
    model = SignLanguageClassifier(
        in_features=data.get("in_features", FEATURE_DIM),
        num_classes=data.get("num_classes", NUM_CLASSES),
        hidden_size=data.get("hidden_size", 64)
    )
    model.load_state_dict(data["state_dict"])
    model.to(device)
    model.eval()
    return model

def load_real_dataset(dataset_dir: str) -> List[Tuple[torch.Tensor, int]]:
    samples = []
    for i, word in enumerate(VOCABULARY):
        word_dir = os.path.join(dataset_dir, word)
        if not os.path.isdir(word_dir):
            continue
        for file in glob.glob(os.path.join(word_dir, "*.npy")):
            arr = np.load(file)
            if arr.shape == (SEQ_LENGTH, FEATURE_DIM):
                samples.append((torch.from_numpy(arr).float(), i))
    return samples

def run_real_training():
    dataset_dir = os.path.join(os.path.dirname(__file__), "dataset")
    samples = load_real_dataset(dataset_dir)
    
    if len(samples) == 0:
        print("No real samples found! Exiting.")
        return
        
    random.seed(42)
    random.shuffle(samples)
    
    # 80/20 train/val split
    split_idx = int(0.8 * len(samples))
    train_samples = samples[:split_idx]
    val_samples = samples[split_idx:]
    
    print(f"=====================================================================")
    print(f" [REAL DATA] Training on {NUM_CLASSES}-word vocabulary.")
    print(f" Small-data regime detected! Total samples: {len(samples)}")
    print(f" Training samples  : {len(train_samples)}")
    print(f" Validation samples: {len(val_samples)}")
    print(f" * Note: Validation sets may have just 1 sample per class (or 0).")
    print(f" * Treat validation accuracy with appropriate skepticism.")
    print(f"=====================================================================")
    
    train_dataset = SignLanguageDataset(train_samples, is_train=True, is_synthetic=False)
    val_dataset = SignLanguageDataset(val_samples, is_train=False, is_synthetic=False)
    
    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False)
    
    device = torch.device("cpu")
    model = SignLanguageClassifier(in_features=FEATURE_DIM, num_classes=NUM_CLASSES, hidden_size=64).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()
    
    for epoch in range(1, 51):
        train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_metrics = evaluate_epoch(model, val_loader, criterion, device, is_synthetic=False)
        print(f"Epoch {epoch:02d} | Train Loss: {train_loss:.4f} | Val Loss: {val_metrics['val_loss']:.4f} | Val Acc: {val_metrics['raw_acc']:.2%}")
        
    save_path = os.path.join(os.path.dirname(__file__), "checkpoints", "real_model.pth")
    save_checkpoint(model, save_path)
    print(f"[INFO] Model saved to {save_path}")

if __name__ == "__main__":
    run_real_training()
