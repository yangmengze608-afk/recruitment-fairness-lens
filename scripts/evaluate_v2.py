"""Independent four-way evaluator (contract v2). Labels and predictions are separate files.

Labels (JSONL): {"id","triage": flag|review|clear|unknown|unresolved, "review_reason", "label_source", optional
  "slice", "scope", "sex_link", "care_condition", "risk_quotes"}.  `unresolved` = human could not decide; excluded
  from determinate scoring and listed.
Predictions: records.jsonl rows from run_spark_v2.py / rules_v2.py, or `--legacy-v1` rows (3-class contract v1,
  i.e. Baseline A and Round-1 Spark), which are adapted without changing them.
Invalid / missing predictions are a 5th prediction column and stay in every denominator.

Reported (all on the given label file only):
  4x5 confusion matrix; per-class P/R/F1; accuracy; JSON/contract pass rate; quote substring validity;
  error slices: review<->flag confusion, unknown forced to a determinate class, spurious unknown,
  normal-condition false alarms, care->sex inference errors, quote/history/negation false alarms,
  role/voice false alarms, welcome-statement false alarms, multi-condition misses;
  core sex/marriage cue P/R (positives = gold flag with reason explicit_sex|marriage_birth; care/context/unknown
  items reported separately, never counted as sex-positive); human-review-queue metrics (separate);
  latency if a run_meta / raw file is supplied.
`claim_status` is ELIGIBLE_FOR_REPORTING only when every label row has label_source == "human_frozen".
"""
import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRIAGES = ("flag", "review", "clear", "unknown")
PRED_COLS = TRIAGES + ("invalid",)
CORE = ("explicit_sex", "marriage_birth")
V1_REASON = {"sex_preference": "explicit_sex", "marital_reproductive": "marriage_birth",
             "contextual_bias": "context", "special_context": "exception_missing", "none": "none"}


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def adapt_v1(row, text):
    """Round-1 / Baseline A 3-class output -> comparable view. No unknown class exists in v1."""
    from rfl.contract import validate
    if "prediction" in row:
        obj, viol = row["prediction"], row.get("violations", [])
    else:
        obj, viol = row, validate(row, row.get("id"), text)
    hard = [v for v in viol if v.startswith(("parse:", "unparseable", "missing", "bad_", "id_mismatch", "evidence_not_substring"))]
    if obj is None or hard:
        return {"id": row["id"], "triage": "invalid", "findings": [], "risk_quotes": [], "sex_link": None, "all_review_reasons": []}
    reason = V1_REASON.get(obj.get("issue_type"), "none")
    ev = obj.get("evidence") or ""
    t = obj.get("status")
    findings = [{"quote": ev, "reason": reason, "triage": t}] if t != "clear" and ev else []
    return {"id": row["id"], "triage": t, "findings": findings, "risk_quotes": [ev] if findings else [],
            "sex_link": None, "all_review_reasons": [reason] if findings else [], "scope": None}


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def _overlap(a, b):
    return bool(a) and bool(b) and (a in b or b in a)


def evaluate(cases, labels, preds, label_source_note, legacy_v1=False, latencies=None):
    texts = {c["id"]: c["text"] for c in cases}
    lab = {l["id"]: l for l in labels}
    if len(lab) != len(labels):
        raise ValueError("duplicate label ids")
    unknown_ids = sorted(set(lab) - set(texts))
    if unknown_ids:
        raise ValueError(f"labels reference ids not in cases: {unknown_ids}")
    pmap = {}
    for r in preds:
        if r["id"] in pmap:
            raise ValueError(f"duplicate prediction id {r['id']}")
        pmap[r["id"]] = adapt_v1(r, texts.get(r["id"], "")) if legacy_v1 else r
    mat = {g: {c: 0 for c in PRED_COLS} for g in TRIAGES}
    rows, unresolved = [], []
    q_total = q_ok = 0
    for cid, l in lab.items():
        p = pmap.get(cid) or {"triage": "invalid", "findings": [], "risk_quotes": [], "all_review_reasons": [],
                              "model_violations": ["missing_prediction"]}
        y = p["triage"] if p["triage"] in PRED_COLS else "invalid"
        for q in p.get("risk_quotes", []) + (p.get("context_quotes") or []):
            q_total += 1
            q_ok += q in texts[cid]
        pr = set(p.get("all_review_reasons") or [])
        row = {"id": cid, "set": l.get("set"), "slice": l.get("slice"), "gold": l["triage"],
               "gold_reason": l.get("review_reason"), "pred": y, "pred_reasons": sorted(pr),
               "pred_sex_link": p.get("sex_link"), "pred_scope": p.get("scope"), "gold_scope": l.get("scope"),
               "pred_risk_quotes": p.get("risk_quotes", []), "gold_risk_quotes": l.get("risk_quotes"),
               "violations": p.get("model_violations", [])}
        rows.append(row)
        if l["triage"] == "unresolved":
            unresolved.append(row)
            continue
        if l["triage"] not in TRIAGES:
            raise ValueError(f"bad gold triage {l['triage']} for {cid}")
        mat[l["triage"]][y] += 1
    det = [r for r in rows if r["gold"] != "unresolved"]
    n = len(det)

    def per_class(t):
        tp = mat[t][t]
        fp = sum(mat[g][t] for g in TRIAGES if g != t)
        fn = sum(mat[t][c] for c in PRED_COLS if c != t)
        return {**prf(tp, fp, fn), "support": sum(mat[t].values())}

    per = {t: per_class(t) for t in TRIAGES}

    def sl(name, sel, bad):
        s = [r for r in det if sel(r)]
        hits = [r["id"] for r in s if bad(r)]
        return {"name": name, "n": len(s), "errors": len(hits), "rate": len(hits) / len(s) if s else None, "ids": hits}

    nonclear = ("flag", "review", "unknown")
    slices = [
        sl("review_predicted_as_flag", lambda r: r["gold"] == "review", lambda r: r["pred"] == "flag"),
        sl("flag_predicted_as_review", lambda r: r["gold"] == "flag", lambda r: r["pred"] == "review"),
        sl("unknown_forced_determinate", lambda r: r["gold"] == "unknown", lambda r: r["pred"] in ("flag", "review", "clear")),
        sl("spurious_unknown", lambda r: r["gold"] != "unknown", lambda r: r["pred"] == "unknown"),
        sl("normal_condition_false_alarm", lambda r: r["slice"] == "normal_condition", lambda r: r["pred"] in nonclear),
        sl("care_to_sex_inference", lambda r: r["slice"] == "care",
           lambda r: bool(set(r["pred_reasons"]) & set(CORE)) or r["pred_sex_link"] in ("explicit", "suggested")),
        sl("care_dropped_to_clear", lambda r: r["slice"] == "care", lambda r: r["pred"] == "clear"),
        sl("quote_history_negation_false_alarm", lambda r: r["slice"] in ("quote_history", "negation"), lambda r: r["pred"] in nonclear),
        sl("role_voice_false_alarm", lambda r: r["slice"] == "role_voice", lambda r: r["pred"] in nonclear),
        sl("welcome_or_welfare_false_alarm", lambda r: r["slice"] in ("welcome", "welfare"), lambda r: r["pred"] in nonclear),
        sl("training_scope_false_alarm", lambda r: r["slice"] == "training", lambda r: r["pred"] in nonclear),
        sl("multi_condition_or_history_plus_current_miss", lambda r: r["slice"] in ("multi_condition", "history_plus_current"),
           lambda r: r["pred"] != "flag"),
        sl("injection_followed", lambda r: r["slice"] == "injection", lambda r: r["pred"] != "flag"),
        sl("invalid_output", lambda r: True, lambda r: r["pred"] == "invalid"),
    ]

    # Core sex/marriage cue detection. Gold positive: flag with core reason. Excluded from this metric
    # (reported separately): gold care / context / unknown items.
    core_pool = [r for r in det if r["gold"] in ("flag", "clear")]
    gpos = lambda r: r["gold"] == "flag" and r["gold_reason"] in CORE  # noqa: E731
    ppos = lambda r: r["pred"] == "flag" and bool(set(r["pred_reasons"]) & set(CORE))  # noqa: E731
    core = prf(sum(gpos(r) and ppos(r) for r in core_pool), sum((not gpos(r)) and ppos(r) for r in core_pool),
               sum(gpos(r) and not ppos(r) for r in core_pool))
    core.update(n=len(core_pool), excluded_ids=[r["id"] for r in det if r["gold"] in ("review", "unknown")],
                definition="gold flag with reason explicit_sex|marriage_birth vs pred flag carrying such a reason; "
                           "gold review/unknown excluded and reported in slices")
    # Human-review queue: anything not clear goes to a person (invalid output also goes to a person).
    qpos = lambda r: r["gold"] != "clear"  # noqa: E731
    qpred = lambda r: r["pred"] != "clear"  # noqa: E731
    queue = prf(sum(qpos(r) and qpred(r) for r in det), sum((not qpos(r)) and qpred(r) for r in det),
                sum(qpos(r) and not qpred(r) for r in det))
    queue.update(n=n, note="queue contains care-condition, context, exception and invalid items; NOT a discrimination-detection metric")
    # Risk-quote recall for gold items that carry risk_quotes (seed50 research labels only).
    with_q = [r for r in det if r["gold_risk_quotes"]]
    quote_recall = {"n_items": len(with_q),
                    "items_all_gold_quotes_overlapped": sum(all(any(_overlap(g, p) for p in r["pred_risk_quotes"]) for g in r["gold_risk_quotes"]) for r in with_q)}
    scope_rows = [r for r in det if r["gold_scope"] and r["pred_scope"] is not None]
    rep = {
        "label_source": label_source_note,
        "label_sources_in_file": dict(Counter(l.get("label_source", "?") for l in labels)),
        "claim_status": "ELIGIBLE_FOR_REPORTING" if all(l.get("label_source") == "human_frozen" for l in labels)
        else "DEVELOPMENT_ONLY — labels are AI-assisted research opinions / engineer probes, not human gold",
        "n_labels": len(lab), "n_determinate": n, "n_unresolved": len(unresolved),
        "confusion_rows_gold_cols_pred": mat,
        "per_class": per,
        "macro_f1_4class": sum(per[t]["f1"] for t in TRIAGES) / 4,
        "accuracy": sum(mat[t][t] for t in TRIAGES) / n if n else None,
        "contract_pass_rate": sum(r["pred"] != "invalid" for r in det) / n if n else None,
        "quote_substring_rate": q_ok / q_total if q_total else None,
        "core_sex_marriage_cue": core,
        "human_review_queue": queue,
        "risk_quote_overlap": quote_recall,
        "scope_agreement": {"n": len(scope_rows), "agree": sum(r["gold_scope"] == r["pred_scope"] for r in scope_rows)},
        "error_slices": slices,
        "unresolved_items": unresolved,
        "mismatches": [r for r in det if r["gold"] != r["pred"]],
    }
    if latencies:
        s = sorted(latencies)
        rep["latency_s"] = {"n": len(s), "mean": statistics.mean(s), "median": statistics.median(s),
                            "p90": s[int(0.9 * (len(s) - 1))], "max": s[-1]}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--predictions", required=True, help="records.jsonl (v2) or v1 predictions with --legacy-v1")
    ap.add_argument("--legacy-v1", action="store_true")
    ap.add_argument("--raw", help="raw.jsonl for latency")
    ap.add_argument("--only-ids-in-predictions", action="store_true",
                    help="restrict labels to ids present in predictions (for historical runs on a subset)")
    ap.add_argument("--label-source", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    labels = read_jsonl(a.labels)
    preds = read_jsonl(a.predictions)
    if a.only_ids_in_predictions:
        ids = {p["id"] for p in preds}
        labels = [l for l in labels if l["id"] in ids]
    lat = [r["latency_s"] for r in read_jsonl(a.raw) if r.get("latency_s") is not None] if a.raw else None
    rep = evaluate(read_jsonl(a.cases), labels, preds, a.label_source, a.legacy_v1, lat)
    rep["inputs"] = {"cases": a.cases, "labels": a.labels, "predictions": a.predictions, "legacy_v1": a.legacy_v1}
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    brief = {k: rep[k] for k in ("claim_status", "n_determinate", "accuracy", "macro_f1_4class", "contract_pass_rate", "quote_substring_rate")}
    brief["core_PR"] = (rep["core_sex_marriage_cue"]["precision"], rep["core_sex_marriage_cue"]["recall"])
    brief["slices"] = {s["name"]: f"{s['errors']}/{s['n']}" for s in rep["error_slices"]}
    print(json.dumps(brief, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
