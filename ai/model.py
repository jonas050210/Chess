"""Policy/Value-Netz. NumPy lauffähig; PyTorch/CUDA-Gerüst für Ubuntu."""
from __future__ import annotations

import os
import numpy as np

from .env import ACTION_SIZE, INPUT_DIM, PLANES

HIDDEN = 128
VALUE_WEIGHT = 1.0

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except Exception:  # pragma: no cover
    HAS_TORCH = False


class NumpyPolicyValueNet:
    """MLP: 1344 -> ReLU(128) -> 4672 Policy + 1 Value. Echt backpropagiert."""

    def __init__(self, seed: int = 0):
        rng = np.random.default_rng(seed)
        s1 = np.sqrt(2.0 / INPUT_DIM).astype(np.float32)
        s2 = np.sqrt(1.0 / HIDDEN).astype(np.float32)
        self.W1 = (rng.standard_normal((INPUT_DIM, HIDDEN)) * s1).astype(np.float32)
        self.b1 = np.zeros(HIDDEN, dtype=np.float32)
        self.Wp = (rng.standard_normal((HIDDEN, ACTION_SIZE)) * s2).astype(np.float32)
        self.bp = np.zeros(ACTION_SIZE, dtype=np.float32)
        self.Wv = (rng.standard_normal((HIDDEN, 1)) * s2).astype(np.float32)
        self.bv = np.zeros(1, dtype=np.float32)

    def forward(self, x: np.ndarray, mask: np.ndarray):
        x = np.atleast_2d(np.asarray(x, dtype=np.float32))
        mask = np.atleast_2d(np.asarray(mask, dtype=np.float32))
        h = np.maximum(0.0, x @ self.W1 + self.b1)
        logits = h @ self.Wp + self.bp
        logits = np.where(mask > 0, logits, -1e9)
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(shifted) * mask
        denom = exp.sum(axis=1, keepdims=True)
        probs = np.where(denom > 0, exp / np.maximum(denom, 1e-12),
                         mask / np.maximum(mask.sum(axis=1, keepdims=True), 1.0))
        value = np.tanh((h @ self.Wv + self.bv).ravel()).astype(np.float32)
        return probs.astype(np.float32), value

    def train_batch(self, states, masks, policy_targets, value_targets,
                    lr: float = 1e-3, value_weight: float = VALUE_WEIGHT) -> float:
        x = np.asarray(states, dtype=np.float32)
        m = np.asarray(masks, dtype=np.float32)
        pi = np.asarray(policy_targets, dtype=np.float32)
        z = np.asarray(value_targets, dtype=np.float32).reshape(-1)
        b = x.shape[0]
        if b == 0:
            return 0.0
        h_pre = x @ self.W1 + self.b1
        h = np.maximum(0.0, h_pre)
        logits = np.where(m > 0, h @ self.Wp + self.bp, -1e9)
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(shifted) * m
        p = exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-12)
        pre = (h @ self.Wv + self.bv).ravel()
        v = np.tanh(pre)

        policy_loss = -np.sum(pi * np.log(np.maximum(p, 1e-12))) / b
        value_loss = np.mean((v - z) ** 2)
        loss = float(policy_loss + value_weight * value_loss)

        dlogits = (p - pi) / b
        dlogits *= m
        dv = (2.0 * value_weight * (v - z) / b * (1.0 - v ** 2)).reshape(-1, 1)
        dWp, dbp = h.T @ dlogits, dlogits.sum(axis=0)
        dWv, dbv = h.T @ dv, dv.sum(axis=0)
        dh = dlogits @ self.Wp.T + dv @ self.Wv.T
        dh[h_pre <= 0] = 0.0
        dW1, db1 = x.T @ dh, dh.sum(axis=0)

        for name, grad in [("W1", dW1), ("b1", db1), ("Wp", dWp),
                           ("bp", dbp), ("Wv", dWv), ("bv", dbv)]:
            setattr(self, name, getattr(self, name) - lr * grad.astype(np.float32))
        return loss

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        np.savez_compressed(
            path, W1=self.W1, b1=self.b1, Wp=self.Wp, bp=self.bp,
            Wv=self.Wv, bv=self.bv,
            planes=np.array(PLANES, dtype=np.int32),
            input_dim=np.array(INPUT_DIM, dtype=np.int32),
        )

    @classmethod
    def load(cls, path: str) -> "NumpyPolicyValueNet":
        obj = cls(seed=0)
        with np.load(path) as d:
            old_in = int(d["W1"].shape[0])
            if old_in != INPUT_DIM:
                k = min(old_in, INPUT_DIM)
                obj.W1[:k] = d["W1"][:k].astype(np.float32)
                print(f"[model] Input {old_in} -> {INPUT_DIM}, Gewichte übernommen/ergänzt")
            else:
                obj.W1 = d["W1"].astype(np.float32)
            obj.b1 = d["b1"].astype(np.float32)
            obj.Wp = d["Wp"].astype(np.float32)
            obj.bp = d["bp"].astype(np.float32)
            obj.Wv = d["Wv"].astype(np.float32)
            obj.bv = d["bv"].astype(np.float32)
        return obj


if HAS_TORCH:
    class TorchPolicyValueNet(nn.Module):
        """ResNet auf 21x8x8 (Ubuntu + RTX 4060 Ti)."""
        def __init__(self, planes: int = PLANES, channels: int = 64, blocks: int = 4):
            super().__init__()
            self.stem = nn.Sequential(
                nn.Conv2d(planes, channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(channels), nn.ReLU(),
            )
            self.blocks = nn.ModuleList([
                nn.Sequential(
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels), nn.ReLU(),
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                ) for _ in range(blocks)
            ])
            self.policy = nn.Sequential(
                nn.Conv2d(channels, 32, 1), nn.ReLU(),
                nn.Flatten(), nn.Linear(32 * 8 * 8, ACTION_SIZE),
            )
            self.value = nn.Sequential(
                nn.Conv2d(channels, 8, 1), nn.ReLU(),
                nn.Flatten(), nn.Linear(8 * 8 * 8, 64), nn.ReLU(),
                nn.Linear(64, 1), nn.Tanh(),
            )

        def forward(self, x, mask=None):
            x = self.stem(x)
            for b in self.blocks:
                x = F.relu(x + b(x))
            logits = self.policy(x)
            if mask is not None:
                logits = logits.masked_fill(mask == 0, -1e4)
            return logits, self.value(x).squeeze(-1)

    class TorchPolicyValueWrapper:
        def __init__(self, channels: int = 64, blocks: int = 4,
                     device: str | None = None, checkpoint: str | None = None):
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
            weights = None
            if checkpoint and os.path.exists(checkpoint):
                # weights_only avoids unpickling arbitrary Python objects. v2
                # checkpoints also carry architecture dimensions for inference.
                saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
                if isinstance(saved, dict) and "state_dict" in saved:
                    if saved.get("planes", PLANES) != PLANES:
                        raise ValueError("Checkpoint input planes do not match this engine")
                    channels = int(saved["channels"])
                    blocks = int(saved["blocks"])
                    weights = saved["state_dict"]
                else:  # legacy raw state_dict
                    weights = saved
                    channels = int(weights["stem.0.weight"].shape[0])
                    blocks = len({key.split(".")[1] for key in weights
                                  if key.startswith("blocks.")})
            self.channels, self.blocks = channels, blocks
            self.net = TorchPolicyValueNet(channels=channels, blocks=blocks).to(self.device)
            if weights is not None:
                self.net.load_state_dict(weights, strict=True)
            self.net.eval()

        def forward(self, x: np.ndarray, mask: np.ndarray):
            self.net.eval()
            xt = torch.from_numpy(
                np.atleast_2d(np.asarray(x, np.float32)).reshape(-1, PLANES, 8, 8)
            ).to(self.device)
            mt = torch.from_numpy(np.atleast_2d(np.asarray(mask, np.float32))).to(self.device)
            with torch.no_grad():
                logits, value = self.net(xt, mt)
                probs = torch.softmax(logits, dim=1).cpu().numpy()
                v = value.cpu().numpy().ravel()
            return probs.astype(np.float32), v.astype(np.float32)

        def save(self, path: str):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            torch.save({"version": 2, "planes": PLANES, "channels": self.channels,
                        "blocks": self.blocks, "state_dict": self.net.state_dict()}, path)
else:
    TorchPolicyValueNet = None       # type: ignore
    TorchPolicyValueWrapper = None  # type: ignore


def load_net(path: str | None = None, prefer_torch: bool = False):
    if path and str(path).endswith(".pt") and HAS_TORCH:
        return TorchPolicyValueWrapper(checkpoint=path)
    if prefer_torch and HAS_TORCH:
        return TorchPolicyValueWrapper()
    if path and os.path.exists(path):
        return NumpyPolicyValueNet.load(path)
    return NumpyPolicyValueNet(seed=0)
