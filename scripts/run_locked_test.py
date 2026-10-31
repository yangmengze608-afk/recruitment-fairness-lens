"""One-shot locked-test runner (docs_v2/LOCKED_TEST_PROTOCOL.md). Never reads labels.

  python3 scripts/run_locked_test.py --inputs /path/locked_inputs.jsonl --registered-sha <hex from 出题人>

Input rows may use `case_id` or `id` plus `text`, nothing else (v1.1, 2026-10-30). CSV (header case_id,text) or JSONL (v1.2, 2026-10-31).
Before running it reports exact / whitespace-normalised duplicates against the 86-case development set.
After the run it writes outputs_locked/PREDICTIONS_SEALED.json (SHA-256 of every prediction file) BEFORE any label
is opened; evaluation afterwards must verify that seal.

Refuses to run if: any frozen file changed since docs_v3/FREEZE_v2.1_pp2.3.json (UI-only index.html change is
allowed when listed with the same hash in docs_v4/FREEZE_ADDENDA.json); the inputs hash differs from the registered hash;
inputs contain fields other than id/text; or outputs_locked/ already holds a run (one shot only).
Then runs Spark (xfyun_maas, frozen prompt v2.1 + postprocess v2.3) and baselines A and B on the inputs.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_locked"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--registered-sha", required=True)
    a = ap.parse_args()
    freeze = json.loads((ROOT / "docs_v3/FREEZE_v2.1_pp2.3.json").read_text(encoding="utf-8"))
    addenda = json.loads((ROOT / "docs_v4/FREEZE_ADDENDA.json").read_text(encoding="utf-8"))["entries"]
    allowed = {e["file"]: e["sha256"] for e in addenda}  # latest entry per file wins
    changed = [f for f, h in freeze["files_sha256"].items() if sha(ROOT / f) != h and allowed.get(f) != sha(ROOT / f)]
    if changed or sha(ROOT / "rfl/prompt_v2_1.py") != freeze["prompt_file_sha256"]:
        sys.exit(f"REFUSED: frozen files changed: {changed}")
    if sha(a.inputs) != a.registered_sha:
        sys.exit("REFUSED: inputs hash does not match the registered hash")
    if a.inputs.lower().endswith(".csv"):
        import csv
        with open(a.inputs, encoding="utf-8-sig", newline="") as fh:
            rows = [dict(r) for r in csv.DictReader(fh)]
    else:
        rows = [json.loads(x) for x in Path(a.inputs).read_text(encoding="utf-8").splitlines() if x.strip()]
    extra = {k for r in rows for k in r} - {"id", "case_id", "text"}
    if extra:
        sys.exit(f"REFUSED: inputs contain non-input fields {sorted(extra)} (labels must stay with the 出题人)")
    norm = [{"id": r.get("case_id", r.get("id")), "text": r["text"]} for r in rows]
    if any(not x["id"] or not isinstance(x["text"], str) for x in norm) or len({x["id"] for x in norm}) != len(norm):
        sys.exit("REFUSED: every row needs a unique case_id/id and a text")
    dev = [json.loads(x)["text"] for x in (ROOT / "data_v2/dev_inputs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    ws = lambda t: "".join(t.split())  # noqa: E731
    dup = {"checked_against": "data_v2/dev_inputs.jsonl (86 dev cases; public package holds 70 of them)",
           "exact": [x["id"] for x in norm if x["text"] in dev],
           "whitespace_normalised": [x["id"] for x in norm if ws(x["text"]) in {ws(d) for d in dev}]}
    print("duplicate check vs dev set:", json.dumps(dup, ensure_ascii=False))
    if OUT.exists() and any(OUT.iterdir()):
        sys.exit("REFUSED: outputs_locked/ already contains a run; the locked test is one-shot")
    OUT.mkdir(exist_ok=True)
    norm_path = OUT / "locked_inputs_normalised.jsonl"
    norm_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in norm), encoding="utf-8")
    (OUT / "LOCKED_RUN_META.json").write_text(json.dumps({"inputs_sha256": a.registered_sha, "n": len(rows), "duplicate_check": dup,
                                                           "freeze": "docs_v3/FREEZE_v2.1_pp2.3.json"}, indent=1), encoding="utf-8")
    py = sys.executable
    subprocess.run([py, "scripts/run_provider.py", "--provider", "xfyun_maas", "--prompt-module", "rfl.prompt_v2_1",
                    "--postprocess", "v2.3", "--input", str(norm_path), "--out-dir", str(OUT / "spark_maas")], cwd=ROOT, check=True,
                   env={**__import__("os").environ, "XFYUN_MAX_CALLS": str(len(rows) * 3 + 5)})
    (OUT / "baselineA").mkdir()
    subprocess.run([py, "baseline/baseline.py", "--input", str(norm_path), "--output", str(OUT / "baselineA/predictions.jsonl")], cwd=ROOT, check=True)
    subprocess.run([py, "baseline/rules_v2.py", "--input", str(norm_path), "--out-dir", str(OUT / "baselineB")], cwd=ROOT, check=True)
    seal = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*.json*")) if p.name != "PREDICTIONS_SEALED.json"}
    (OUT / "PREDICTIONS_SEALED.json").write_text(json.dumps({"sealed_utc": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(), "files_sha256": seal}, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in OUT.rglob("*"):
        if p.is_file():
            p.chmod(0o444)
    print("done. Predictions sealed in outputs_locked/PREDICTIONS_SEALED.json. Labels are applied afterwards by the PI with scripts/evaluate_v2.py --label-source human_frozen")


if __name__ == "__main__":
    main()
