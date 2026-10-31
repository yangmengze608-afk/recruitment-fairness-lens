"""Verify outputs_locked/PREDICTIONS_SEALED.json before opening any label. Exit 1 on any mismatch."""
import hashlib
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "outputs_locked"
seal = json.loads((OUT / "PREDICTIONS_SEALED.json").read_text(encoding="utf-8"))
bad = [f for f, h in seal["files_sha256"].items() if hashlib.sha256((OUT / f).read_bytes()).hexdigest() != h]
print(json.dumps({"sealed_utc": seal["sealed_utc"], "n_files": len(seal["files_sha256"]), "mismatch": bad}, ensure_ascii=False))
sys.exit(1 if bad else 0)
