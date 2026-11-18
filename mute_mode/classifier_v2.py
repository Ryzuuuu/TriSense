# mute_mode/classifier_v2.py
# -----------------------------------------------------------------------------
# Mute Mode v2 sign classifier: compact temporal CNN + bidirectional GRU with
# attention pooling. Roughly 0.18 M parameters (about 0.7 MB in float32), still
# small enough for real time CPU inference on a Raspberry Pi 4.
#
# Input : (batch, SEQ_LEN=32, FEATURE_DIM_V2=226) from mute_mode/features.py
# Output: (batch, num_classes) logits
# -----------------------------------------------------------------------------

from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from mute_mode.features import FEATURE_DIM_V2


class _SepConvBlock(nn.Module):
    """Depthwise separable temporal convolution with a residual connection."""

    def __init__(self, ch: int, k: int = 5, dilation: int = 1, p: float = 0.2):
        super().__init__()
        pad = (k - 1) // 2 * dilation
        self.dw = nn.Conv1d(ch, ch, k, padding=pad, dilation=dilation, groups=ch)
        self.pw = nn.Conv1d(ch, ch, 1)
        self.bn = nn.BatchNorm1d(ch)
        self.drop = nn.Dropout(p)

    def forward(self, x):
        return x + self.drop(F.gelu(self.bn(self.pw(self.dw(x)))))


class SignClassifierV2(nn.Module):
    def __init__(self, num_classes: int, in_features: int = FEATURE_DIM_V2, width: int = 128,
                 gru_hidden: int = 64, dropout: float = 0.3):
        super().__init__()
        self.in_features, self.num_classes = in_features, num_classes
        self.width, self.gru_hidden, self.dropout_p = width, gru_hidden, dropout
        self.input_drop = nn.Dropout(0.1)
        self.proj = nn.Linear(in_features, width)
        self.norm = nn.LayerNorm(width)
        self.blocks = nn.Sequential(
            _SepConvBlock(width, 5, 1, dropout),
            _SepConvBlock(width, 5, 2, dropout),
            _SepConvBlock(width, 5, 4, dropout),
        )
        self.gru = nn.GRU(width, gru_hidden, batch_first=True, bidirectional=True)
        self.attn = nn.Linear(2 * gru_hidden, 1)
        self.head_drop = nn.Dropout(dropout)
        self.fc = nn.Linear(4 * gru_hidden, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 2:
            x = x.unsqueeze(0)
        h = self.norm(self.proj(self.input_drop(x)))           # (B,T,W)
        h = self.blocks(h.transpose(1, 2)).transpose(1, 2)      # (B,T,W)
        g, _ = self.gru(h)                                      # (B,T,2H)
        w = torch.softmax(self.attn(g).squeeze(-1), dim=1)      # (B,T)
        att = torch.bmm(w.unsqueeze(1), g).squeeze(1)           # (B,2H)
        pooled = torch.cat([att, g.mean(dim=1)], dim=1)         # (B,4H)
        return self.fc(self.head_drop(pooled))

    def get_parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @torch.no_grad()
    def predict_step(self, x: torch.Tensor, vocabulary: List[str], top_k: int = 3) -> Dict[str, Any]:
        self.eval()
        probs = F.softmax(self.forward(x), dim=-1)[0]
        conf, idx = torch.topk(probs, k=min(top_k, probs.numel()))
        return {
            "class_idx": int(idx[0]),
            "label": vocabulary[int(idx[0])],
            "confidence": float(conf[0]),
            "top_k": [(vocabulary[int(i)], float(c)) for c, i in zip(conf, idx)],
        }


def save_v2(model: SignClassifierV2, path: str, vocabulary: List[str], metadata: Optional[dict] = None):
    torch.save({
        "arch": "SignClassifierV2",
        "state_dict": model.state_dict(),
        "vocabulary": list(vocabulary),
        "config": {"num_classes": model.num_classes, "in_features": model.in_features,
                   "width": model.width, "gru_hidden": model.gru_hidden, "dropout": model.dropout_p},
        "metadata": metadata or {},
    }, path)


def load_v2(path: str, device: str = "cpu"):
    data = torch.load(path, map_location=device, weights_only=False)
    model = SignClassifierV2(**data["config"])
    model.load_state_dict(data["state_dict"])
    model.to(device).eval()
    return model, data["vocabulary"], data.get("metadata", {})
