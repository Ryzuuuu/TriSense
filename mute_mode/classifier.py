# mute_mode/classifier.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode Step 3: Classifier Architecture (1D-CNN + GRU Hybrid).
#
# Lightweight sequence classification model designed for edge inference
# (Raspberry Pi 4 CPU / TFLite / ONNX export).
#
# Architecture:
#   1. Input: (batch_size, 30 frames, 126 features)
#      [126 features = Left hand (63 coords) + Right hand (63 coords)]
#   2. 1D spatial-temporal convolutions (Conv1d 126->64, Conv1d 64->64)
#   3. Recurrent temporal sequence modeling (1-layer GRU, hidden_size=64)
#   4. Output classification head: Linear(64, 12 vocabulary classes)
#
# Parameter budget: ~62.6k trainable parameters (well under edge limit).
# -----------------------------------------------------------------------------

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Any, List
from mute_mode.config import (
    VOCABULARY,
    NUM_CLASSES,
    SEQ_LENGTH,
    FEATURE_DIM,
    NUM_LANDMARKS
)


def extract_sequence_tensor(sequence_result: Dict[str, Any]) -> torch.Tensor:
    """
    Converts a 30-frame sequence dictionary from GestureSequenceBuffer.get_sequence()
    into a PyTorch tensor of shape (1, 30, 126).
    
    Feature arrangement per frame (126 floats):
      [0..62]   = Left hand 21 landmarks (x, y, z)
      [63..125] = Right hand 21 landmarks (x, y, z)
    """
    frames = sequence_result.get("frames", [])
    if len(frames) != SEQ_LENGTH:
        raise ValueError(f"Expected sequence length {SEQ_LENGTH}, got {len(frames)}")

    tensor_data = []
    for f in frames:
        frame_feats = [0.0] * FEATURE_DIM
        for hand in f.get("hands", []):
            handedness = hand.get("handedness")
            lms = hand.get("landmarks", [])
            offset = 0 if handedness == "Left" else 63 if handedness == "Right" else None
            if offset is not None and not hand.get("missing", False):
                for idx, pt in enumerate(lms):
                    if idx < NUM_LANDMARKS:
                        frame_feats[offset + idx * 3 + 0] = float(pt.get("x", 0.0))
                        frame_feats[offset + idx * 3 + 1] = float(pt.get("y", 0.0))
                        frame_feats[offset + idx * 3 + 2] = float(pt.get("z", 0.0))
        tensor_data.append(frame_feats)

    # Shape: (1, 30, 126)
    return torch.tensor([tensor_data], dtype=torch.float32)


class SignLanguageClassifier(nn.Module):
    """
    Lightweight 1D-CNN + GRU hybrid sequence classifier for 12-word sign vocabulary.
    """
    def __init__(
        self,
        in_features: int = FEATURE_DIM,
        num_classes: int = NUM_CLASSES,
        hidden_size: int = 64,
        dropout_rate: float = 0.2
    ):
        super().__init__()
        self.in_features = in_features
        self.num_classes = num_classes
        self.hidden_size = hidden_size

        # 1D-CNN block for local spatial-temporal motif extraction
        # Note: Conv1d expects input shape (batch_size, channels=126, length=30)
        self.conv1 = nn.Conv1d(in_channels=in_features, out_channels=hidden_size, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(hidden_size)
        self.conv2 = nn.Conv1d(in_channels=hidden_size, out_channels=hidden_size, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(hidden_size)

        # GRU for temporal sequence dependency modeling
        # Takes input of shape (batch_size, length=30, channels=64)
        self.gru = nn.GRU(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True
        )

        self.dropout = nn.Dropout(dropout_rate)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        Args:
            x (torch.Tensor): Tensor of shape (batch_size, SEQ_LENGTH=30, FEATURE_DIM=126)
        Returns:
            logits (torch.Tensor): Unnormalized logit predictions of shape (batch_size, NUM_CLASSES=12)
        """
        if x.dim() == 2:
            x = x.unsqueeze(0)  # Convert (30, 126) -> (1, 30, 126)

        # Permute for Conv1d: (batch_size, 126, 30)
        x_conv = x.permute(0, 2, 1)

        x_conv = F.relu(self.bn1(self.conv1(x_conv)))
        x_conv = self.dropout(x_conv)
        x_conv = F.relu(self.bn2(self.conv2(x_conv)))
        x_conv = self.dropout(x_conv)

        # Permute back for GRU: (batch_size, 30, 64)
        x_seq = x_conv.permute(0, 2, 1)

        gru_out, _ = self.gru(x_seq)
        # Take the output representation of the last time step
        last_hidden = gru_out[:, -1, :]

        last_hidden = self.dropout(last_hidden)
        logits = self.fc(last_hidden)
        return logits

    def get_parameter_count(self) -> int:
        """Returns the total number of trainable parameters in the model."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @torch.no_grad()
    def predict_step(self, x: torch.Tensor) -> Dict[str, Any]:
        """
        Runs inference on an input tensor and returns structured classification results.
        """
        self.eval()
        logits = self.forward(x)
        probs = F.softmax(logits, dim=-1)
        max_prob, max_idx = torch.max(probs, dim=-1)

        pred_idx = int(max_idx.item())
        confidence = float(max_prob.item())
        prob_dict = {VOCABULARY[i]: float(probs[0, i].item()) for i in range(self.num_classes)}

        return {
            "class_idx": pred_idx,
            "label": VOCABULARY[pred_idx],
            "confidence": confidence,
            "probabilities": prob_dict
        }
