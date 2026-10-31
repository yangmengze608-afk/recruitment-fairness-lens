"""Compare a smoke run with engineering expectations written by the AI engineer.

Expectations are sanity probes for the 7 smoke capabilities, NOT legal labels.
"""
import argparse
import json
from pathlib import Path


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--expectations", required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    preds = {r["id"]: r for r in read_jsonl(run / "predictions.jsonl")}
    raws = {r["id"]: r for r in read_jsonl(run / "raw.jsonl")}
    rows = []
    for e in read_jsonl(a.expectations):
        p = preds.get(e["id"], {})
        obj = p.get("prediction") or {}
        ev = obj.get("evidence") or ""
        status_ok = obj.get("status") in e["expected_status"]
        ev_ok = all(x in ev for x in e["expected_evidence_contains"]) if e["expected_evidence_contains"] else True
        rows.append({"id": e["id"], "probe": e["probe"], "expected": e["expected_status"], "got": obj.get("status"),
                     "issue_type": obj.get("issue_type"), "evidence": ev, "reason": obj.get("reason"),
                     "status_ok": status_ok, "evidence_ok": ev_ok, "contract_ok": not p.get("violations"),
                     "violations": p.get("violations"), "latency_s": raws.get(e["id"], {}).get("latency_s"),
                     "output_tokens": raws.get(e["id"], {}).get("output_tokens")})
    n = len(rows)
    summary = {"n": n,
               "contract_pass": sum(r["contract_ok"] for r in rows),
               "status_as_expected": sum(r["status_ok"] for r in rows),
               "evidence_as_expected": sum(r["evidence_ok"] for r in rows),
               "warning": "Engineering smoke probes written by AI engineer; not legal labels; n is tiny."}
    (run / "smoke_check.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        mark = "OK " if r["status_ok"] and r["evidence_ok"] and r["contract_ok"] else "XX "
        print(mark, r["id"], r["probe"], r["expected"], "->", r["got"], repr(r["evidence"]), r["violations"])


if __name__ == "__main__":
    main()
