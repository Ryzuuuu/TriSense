# mute_mode/train_v2.py
# -----------------------------------------------------------------------------
# Trains and evaluates the Mute Mode v2 classifier on landmarks produced by
# build_landmarks.py.
#
# Evaluation protocol (honest by construction):
#   * the official WLASL train / val / test split is used, so no clip of the
#     same video ever appears on both sides
#   * the epoch is chosen on val only, and test is touched exactly once
#   * top 1 and top 5 accuracy are reported, plus per class accuracy
#
#   python mute_mode/train_v2.py                 # evaluate + save eval model
#   python mute_mode/train_v2.py --deploy        # also retrain on train+val for the device
# -----------------------------------------------------------------------------

import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mute_mode.config import VOCABULARY  # noqa: E402
from mute_mode.features import FEATURE_SETS, sequence_features, trim_to_activity  # noqa: E402
from mute_mode.classifier_v2 import SignClassifierV2, save_v2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LM_DIR = os.path.join(HERE, "landmarks")
CKPT_DIR = os.path.join(HERE, "checkpoints")


def load_sequences():
    with open(os.path.join(LM_DIR, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    word_to_idx = {w: i for i, w in enumerate(VOCABULARY)}
    items = []
    for m in index:
        if m["gloss"] not in word_to_idx:
            continue
        z = np.load(os.path.join(LM_DIR, m["gloss"], m["video_id"] + ".npz"))
        seq = {k: z[k].astype(np.float32) if z[k].dtype == np.float16 else z[k] for k in z.files}
        seq = trim_to_activity(seq)
        items.append((seq, word_to_idx[m["gloss"]], m.get("split", "train"), m.get("signer_id")))
    return items


class SeqDataset(Dataset):
    def __init__(self, items, train: bool, seed: int = 0, cols=None, augment: bool = True):
        self.items, self.train = items, train
        self.cols = np.array(cols if cols is not None else FEATURE_SETS["full"])
        self.augment = augment
        self.rng = np.random.default_rng(seed)
        if not (train and augment):  # deterministic features can be cached
            self.cache = [sequence_features(s)[:, self.cols] for s, *_ in items]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        seq, y = self.items[i][0], self.items[i][1]
        x = sequence_features(seq, rng=self.rng)[:, self.cols] if (self.train and self.augment) else self.cache[i]
        return torch.from_numpy(x), y


def run_epoch(model, loader, opt=None, sched=None, crit=None, device="cpu", mixup=0.0):
    train = opt is not None
    model.train(train)
    tot, correct, top5, loss_sum = 0, 0, 0, 0.0
    all_pred, all_true = [], []
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        with torch.set_grad_enabled(train):
            if train and mixup > 0 and np.random.rand() < 0.5:
                lam = float(np.random.beta(mixup, mixup))
                perm = torch.randperm(x.size(0), device=device)
                logits = model(lam * x + (1 - lam) * x[perm])
                loss = lam * crit(logits, y) + (1 - lam) * crit(logits, y[perm])
            else:
                logits = model(x)
                loss = crit(logits, y)
            if train:
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
        loss_sum += float(loss) * y.size(0)
        tot += y.size(0)
        pred = logits.argmax(1)
        correct += int((pred == y).sum())
        top5 += int((logits.topk(5, 1).indices == y[:, None]).any(1).sum())
        all_pred.append(pred.cpu())
        all_true.append(y.cpu())
    return {"loss": loss_sum / max(tot, 1), "top1": correct / max(tot, 1), "top5": top5 / max(tot, 1),
            "pred": torch.cat(all_pred).numpy() if all_pred else np.array([]),
            "true": torch.cat(all_true).numpy() if all_true else np.array([])}


def train_model(train_items, val_items, epochs, seed, args, device, log_prefix=""):
    torch.manual_seed(seed)
    np.random.seed(seed)
    cols = FEATURE_SETS[args.features]
    model = SignClassifierV2(num_classes=len(VOCABULARY), in_features=len(cols), width=args.width,
                             gru_hidden=args.gru, dropout=args.dropout).to(device)
    tl = DataLoader(SeqDataset(train_items, True, seed, cols, augment=not args.no_augment),
                    batch_size=args.batch, shuffle=True, drop_last=True)
    vl = DataLoader(SeqDataset(val_items, False, cols=cols), batch_size=128) if val_items else None
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.wd)
    steps = epochs * len(tl)
    warm = max(1, int(0.05 * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    crit = nn.CrossEntropyLoss(label_smoothing=args.smoothing)
    best, best_state, best_ep, history = -1.0, None, 0, []
    for ep in range(1, epochs + 1):
        tr = run_epoch(model, tl, opt, sched, crit, device, mixup=args.mixup)
        rec = {"epoch": ep, "train_loss": tr["loss"], "train_top1": tr["top1"]}
        if vl is not None:
            va = run_epoch(model, vl, crit=crit, device=device)
            rec.update(val_loss=va["loss"], val_top1=va["top1"], val_top5=va["top5"])
            if va["top1"] > best:
                best, best_ep = va["top1"], ep
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        history.append(rec)
        if ep % 10 == 0 or ep == epochs:
            msg = f"{log_prefix}ep {ep:3d} train {tr['loss']:.3f}/{tr['top1']:.1%}"
            if vl is not None:
                msg += f" | val {va['loss']:.3f} top1 {va['top1']:.1%} top5 {va['top5']:.1%} (best {best:.1%}@{best_ep})"
            print(msg, flush=True)
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_ep, best, history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=160)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--wd", type=float, default=0.05)
    ap.add_argument("--width", type=int, default=128)
    ap.add_argument("--gru", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--smoothing", type=float, default=0.1)
    ap.add_argument("--mixup", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--features", choices=sorted(FEATURE_SETS), default="full", help="feature set (ablation)")
    ap.add_argument("--no-augment", action="store_true", help="disable data augmentation (ablation)")
    ap.add_argument("--tag", default="", help="suffix for the report file name")
    ap.add_argument("--deploy", action="store_true", help="retrain on train+val for the device model")
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    items = load_sequences()
    split = {s: [it for it in items if it[2] == s] for s in ("train", "val", "test")}
    counts = np.bincount([it[1] for it in items], minlength=len(VOCABULARY))
    print(f"[DATA] {len(items)} clips | train {len(split['train'])} val {len(split['val'])} test {len(split['test'])}"
          f" | per word min {counts.min()} median {int(np.median(counts))} max {counts.max()}")

    t0 = time.time()
    model, best_ep, best_val, history = train_model(split["train"], split["val"], args.epochs, args.seed, args, device)
    crit = nn.CrossEntropyLoss()
    cols = FEATURE_SETS[args.features]
    te = run_epoch(model, DataLoader(SeqDataset(split["test"], False, cols=cols), batch_size=128), crit=crit, device=device)
    per_class = {}
    for c in range(len(VOCABULARY)):
        m = te["true"] == c
        if m.any():
            per_class[VOCABULARY[c]] = float((te["pred"][m] == c).mean())
    result = {
        "protocol": "official WLASL split, model selected on val, test evaluated once",
        "clips": {k: len(v) for k, v in split.items()},
        "params": model.get_parameter_count(),
        "best_epoch": best_ep, "val_top1": best_val,
        "test_top1": te["top1"], "test_top5": te["top5"],
        "per_class_test_top1": per_class,
        "train_seconds": round(time.time() - t0, 1),
        "args": vars(args),
    }
    print(f"\n[RESULT] params={result['params']:,}  val top1={best_val:.2%}  "
          f"TEST top1={te['top1']:.2%}  top5={te['top5']:.2%}  (best epoch {best_ep})")
    os.makedirs(CKPT_DIR, exist_ok=True)
    tag = args.tag or (args.features + ("_noaug" if args.no_augment else ""))
    if tag == "full":
        save_v2(model, os.path.join(CKPT_DIR, "sign_v2_eval.pth"), VOCABULARY, result)
    with open(os.path.join(CKPT_DIR, f"sign_v2_report_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump({**result, "history": history}, f, indent=1)

    if args.deploy and args.features != "full":
        raise SystemExit("--deploy only makes sense with --features full (the live recogniser uses all features)")
    if args.deploy:
        print("\n[DEPLOY] retraining on train+val with the selected epoch count ...")
        final, *_ = train_model(split["train"] + split["val"], [], max(best_ep, 40), args.seed, args, device, "[deploy] ")
        te2 = run_epoch(final, DataLoader(SeqDataset(split["test"], False, cols=cols), batch_size=128), crit=crit, device=device)
        meta = {**result, "deploy_test_top1": te2["top1"], "deploy_test_top5": te2["top5"],
                "deploy_note": "trained on train+val; test still held out"}
        save_v2(final, os.path.join(CKPT_DIR, "sign_v2.pth"), VOCABULARY, meta)
        print(f"[DEPLOY] test top1={te2['top1']:.2%} top5={te2['top5']:.2%} -> checkpoints/sign_v2.pth")


if __name__ == "__main__":
    main()
