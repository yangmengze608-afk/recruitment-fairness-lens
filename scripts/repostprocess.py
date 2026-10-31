"""Re-derive records from a saved run's raw.jsonl with postprocess v2.2. No model call; source run untouched."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import importlib  # noqa: E402
from rfl.contract import extract_json  # noqa: E402
from rfl.contract_v2 import derive_record, load_whitelist, validate_v2  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--run-dir", required=True)
ap.add_argument("--out-dir", required=True)
ap.add_argument("--pp", default="v2.2", choices=["v2.2", "v2.3"])
a = ap.parse_args()
pp = importlib.import_module("rfl.postprocess_" + a.pp.replace(".", "_"))
out = Path(a.out_dir)
out.mkdir(parents=True, exist_ok=False)
wl = load_whitelist()
with (out / "records.jsonl").open("w", encoding="utf-8") as df, (out / "predictions.jsonl").open("w", encoding="utf-8") as pf:
    for s in (Path(a.run_dir) / "raw.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(s)
        rec = {"id": r["id"], "text": r["input_text"]}
        obj, perr = extract_json(r.get("raw_output_clean") or "")
        v, w = validate_v2(obj, rec["id"], rec["text"])
        rep0 = []
        if perr and hasattr(pp, "repair_text"):
            fixed, rep0 = pp.repair_text(r.get("raw_output_clean") or "", perr)
            if rep0:
                obj, perr = extract_json(fixed)
                v, w = validate_v2(obj, rec["id"], rec["text"])
        if perr and perr != "trailing_text":
            v = [f"parse:{perr}"] + [x for x in v if x != "unparseable"]
        obj, v, w, rep = pp.apply(obj, v, w, rec)
        rep = rep0 + rep
        d = pp.annotate(derive_record(obj, v, w, rec["id"], rec["text"], wl), rec)
        d["repairs"] = rep
        pf.write(json.dumps({"id": rec["id"], "prediction": obj, "violations": v, "warnings": w, "repairs": rep}, ensure_ascii=False) + "\n")
        df.write(json.dumps(d, ensure_ascii=False) + "\n")
(out / "NOTE.txt").write_text(f"Postprocess {pp.POSTPROCESS_VERSION} applied offline to {a.run_dir}/raw.jsonl (no new model calls).\n", encoding="utf-8")
