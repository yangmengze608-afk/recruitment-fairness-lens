"""Score the sealed locked-test predictions (protocol docs_v5/LOCKED_TEST_SCORING_PROTOCOL.md v1.1). No model is called.

Inputs: outputs_locked/ (sealed, verified first), docs_v5/private/gold/ (reference labels, private).
Outputs: docs_v5/private/locked_eval/. Labels are copied without change; the frozen evaluator is reused as is.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_v2 import evaluate, read_jsonl  # noqa: E402

GOLD = ROOT / "docs_v5/private/gold"
OUT = ROOT / "docs_v5/private/locked_eval"
LOCKED = ROOT / "outputs_locked"
SRC = "single_undergraduate_law_researcher_reference_supporting_fields_gpt_assisted"
DISPUTED = {f"S4-{n:03d}" for n in (1, 3, 10, 11, 13, 17, 20, 22, 25, 26, 28, 29)}  # EVALUATION_POLICY.md


def main():
    subprocess.run([sys.executable, str(ROOT / "scripts/verify_seal.py")], check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    gold = list(csv.DictReader(open(GOLD / "locked_gold.csv", encoding="utf-8-sig", newline="")))
    prov = {p["case_id"]: p for p in json.loads((GOLD / "LABEL_PROVENANCE.json").read_text(encoding="utf-8"))}
    cases = read_jsonl(LOCKED / "locked_inputs_normalised.jsonl")
    ids = {c["id"] for c in cases}
    assert {g["case_id"] for g in gold} == ids and len(gold) == 30, "case_id mismatch"
    assert {k for k, p in prov.items() if p["disputed"]} == DISPUTED, "policy vs provenance disagree on disputed ids"
    labels = []
    for g in gold:
        care, sex = g["care_condition"] == "true", g["sex_link"]
        labels.append({"id": g["case_id"], "triage": g["triage"], "review_reason": g["review_reason"], "scope": g["scope"],
                       "sex_link": sex, "care_condition": care, "risk_quotes": json.loads(g["risk_quotes"]),
                       "slice": "care" if care and sex == "unestablished" else None,
                       "disputed": g["case_id"] in DISPUTED, "original_human_triage": prov[g["case_id"]]["original_human_triage"],
                       "label_source": SRC})
    (OUT / "labels_converted.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels), encoding="utf-8")
    systems = {"spark": (read_jsonl(LOCKED / "spark_maas/records.jsonl"), False),
               "baselineA": (read_jsonl(LOCKED / "baselineA/predictions.jsonl"), True),
               "baselineB": (read_jsonl(LOCKED / "baselineB/records.jsonl"), False)}
    lat = [r["end_to_end_s"] for r in read_jsonl(LOCKED / "spark_maas/raw.jsonl") if r.get("end_to_end_s") is not None]
    groups = {"all30": lambda l: True, "disputed12": lambda l: l["disputed"], "other18": lambda l: not l["disputed"]}
    res = {}
    for sysname, (preds, legacy) in systems.items():
        for gname, sel in groups.items():
            sub = [l for l in labels if sel(l)]
            ids_sub = {l["id"] for l in sub}
            rep = evaluate([c for c in cases if c["id"] in ids_sub], sub, [p for p in preds if p["id"] in ids_sub], SRC, legacy,
                           lat if sysname == "spark" and gname == "all30" else None)
            res[(sysname, gname)] = rep
            (OUT / f"eval_{sysname}_{gname}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    # case table: separates agreement, network failure, invalid JSON, and disagreement on disputed / undisputed items
    raw = {r["id"]: r for r in read_jsonl(LOCKED / "spark_maas/raw.jsonl")}
    pred = {r["id"]: r for r in read_jsonl(LOCKED / "spark_maas/predictions.jsonl")}
    rec = {r["id"]: r for r in systems["spark"][0]}
    a = {r["id"]: r.get("status") for r in systems["baselineA"][0]}
    b = {r["id"]: r["triage"] for r in systems["baselineB"][0]}
    rows = []
    for l in labels:
        i, d = l["id"], rec[l["id"]]
        if raw[i].get("error"):
            cat = "network_failure"
        elif d["triage"] == "invalid":
            cat = "invalid_output"
        elif d["triage"] == l["triage"]:
            cat = "agree"
        else:
            cat = "disagree_disputed" if l["disputed"] else "disagree_undisputed"
        rows.append({"id": i, "disputed": l["disputed"], "reference": l["triage"], "original_human": l["original_human_triage"],
                     "reference_reason": l["review_reason"], "spark": d["triage"], "spark_reasons": d.get("all_review_reasons"),
                     "spark_scope": d.get("scope"), "reference_scope": l["scope"], "category": cat, "repairs": pred[i].get("repairs"),
                     "scope_checks": d.get("scope_checks"), "baselineA": a.get(i), "baselineB": b.get(i), "text": next(c["text"] for c in cases if c["id"] == i),
                     "spark_quotes": d.get("risk_quotes"), "spark_rationale": d.get("rationale"), "reference_note": prov[i]["note"]})
    (OUT / "case_table.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob("*")) if p.suffix in (".json", ".jsonl")}
    (OUT / "SHA256SUMS.json").write_text(json.dumps(sums, indent=1), encoding="utf-8")
    # brief
    for (s, g), r in res.items():
        m = r["confusion_rows_gold_cols_pred"]
        agree = sum(m[t][t] for t in ("flag", "review", "clear", "unknown"))
        q = r["human_review_queue"]
        print(s, g, f"agree {agree}/{r['n_determinate']}", "valid", round(r["contract_pass_rate"] * r["n_determinate"]), "queue P/R", q["precision"], q["recall"])


if __name__ == "__main__":
    main()
