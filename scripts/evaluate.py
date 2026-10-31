"""Independent evaluator: predictions vs. a separately supplied label file.

Label file (JSONL): {"id", "status": flag|review|clear|unresolved, optional "slice"}
  - `unresolved` items are excluded from determinate scoring and listed separately.
  - `--label-source` is mandatory and is copied into the report. Anything other than
    `human_frozen` is stamped INTERNAL_DEV_ONLY and must not be used for performance claims.
Predictions: either flat contract objects (baseline) or run_spark.py rows {"id","prediction","violations"}.
A missing / unparseable / contract-violating prediction counts as `invalid` (never as clear).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rfl.contract import STATUSES, validate  # noqa: E402

PRED_COLS = STATUSES + ("invalid",)


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def normalise_predictions(rows, texts):
    out = {}
    for r in rows:
        if "prediction" in r:
            obj, viol = r["prediction"], r.get("violations", [])
        else:
            obj = r
            viol = validate(obj, r.get("id"), texts.get(r.get("id"), ""))
        if r["id"] in out:
            raise ValueError(f"duplicate prediction id {r['id']}")
        out[r["id"]] = (obj, viol)
    return out


def prf(mat, tag):
    tp = mat[tag][tag]
    fp = sum(mat[g][tag] for g in STATUSES if g != tag)
    fn = sum(mat[tag][c] for c in PRED_COLS if c != tag)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else 0.0
    return {"precision": p, "recall": r, "f1": f, "support": sum(mat[tag].values())}


def evaluate(cases, labels, preds_rows, label_source):
    texts = {c["id"]: c["text"] for c in cases}
    preds = normalise_predictions(preds_rows, texts)
    lab = {l["id"]: l for l in labels}
    if len(lab) != len(labels):
        raise ValueError("duplicate label ids")
    unknown = sorted(set(lab) - set(texts))
    if unknown:
        raise ValueError(f"labels reference ids not in cases: {unknown}")
    mat = {g: {c: 0 for c in PRED_COLS} for g in STATUSES}
    unresolved, invalid, rows = [], [], []
    ev_total = ev_ok = json_ok = 0
    for cid, l in lab.items():
        obj, viol = preds.get(cid, (None, ["missing_prediction"]))
        valid = obj is not None and not any(v.startswith(("parse:", "unparseable", "missing", "bad_", "id_mismatch")) for v in viol)
        json_ok += valid
        y = obj.get("status") if valid else "invalid"
        ev = (obj or {}).get("evidence") or ""
        if ev:
            ev_total += 1
            ev_ok += ev in texts[cid]
        row = {"id": cid, "gold": l["status"], "pred": y, "slice": l.get("slice"), "violations": viol}
        rows.append(row)
        if l["status"] == "unresolved":
            unresolved.append(row)
            continue
        if l["status"] not in STATUSES:
            raise ValueError(f"bad gold label {l['status']} for {cid}")
        mat[l["status"]][y] += 1
        if y == "invalid":
            invalid.append(row)
    det = [r for r in rows if r["gold"] != "unresolved"]
    per = {t: prf(mat, t) for t in STATUSES}

    def rate(sel, cond):
        s = [r for r in det if sel(r)]
        return {"n": len(s), "rate": (sum(cond(r) for r in s) / len(s)) if s else None, "ids": [r["id"] for r in s if cond(r)]}

    return {
        "label_source": label_source,
        "claim_status": "ELIGIBLE_FOR_REPORTING" if label_source == "human_frozen" else "INTERNAL_DEV_ONLY — not a legal or model-performance claim",
        "n_labels": len(lab), "n_determinate": len(det), "n_unresolved": len(unresolved),
        "confusion_rows_gold_cols_pred": mat,
        "per_class": per,
        "macro_f1": sum(per[t]["f1"] for t in STATUSES) / 3,
        "accuracy_determinate": (sum(mat[t][t] for t in STATUSES) / len(det)) if det else None,
        "json_contract_pass_rate": json_ok / len(lab) if lab else None,
        "evidence_substring_rate": (ev_ok / ev_total) if ev_total else None,
        "invalid_predictions": invalid,
        # Slice metrics need a PI-assigned `slice` in the label file (never derived from model input).
        "negation_or_quote_false_alarm": rate(lambda r: r["slice"] in ("negation", "quotation"), lambda r: r["pred"] in ("flag", "review")),
        "implicit_miss": rate(lambda r: r["slice"] == "implicit", lambda r: r["pred"] in ("clear", "invalid")),
        "unresolved_items": unresolved,
        "mismatches": [r for r in det if r["gold"] != r["pred"]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--label-source", required=True, help="e.g. human_frozen | draft_internal")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    rep = evaluate(read_jsonl(a.cases), read_jsonl(a.labels), read_jsonl(a.predictions), a.label_source)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("claim_status", "n_determinate", "n_unresolved", "macro_f1",
                                          "json_contract_pass_rate", "evidence_substring_rate")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
