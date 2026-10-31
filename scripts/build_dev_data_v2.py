"""Build the Stage-2 development set (inputs and labels kept in separate files).

All items here are DEVELOPMENT data (already exposed to the R&D loop). Never use them for
independent performance claims. Label provenance is stored per row in `label_source`.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data_v2" / "legal_pack"
OUT = ROOT / "data_v2"

SRC_RESEARCH = "ai_assisted_legal_research_v1.0 (法学交接包 reviewed_cases.json；AI辅助初审，规则经法学联合研究者讨论，未逐条人工确认)"
SRC_REGRESSION = "legal_pack_regression_expected (法学交接包 regression_cases.json；开发回归，仅 triage+review_reason)"
SRC_ENGINEER = "ai_engineer_probe_v2 (Claude 按 ANNOTATION_RULES 写的工程探针，不是法律标签)"


def read_jsonl(p):
    return [json.loads(s) for s in Path(p).read_text(encoding="utf-8").splitlines() if s.strip()]


def regression_slice(c):
    t, rr = c["expected_triage"], c["expected_review_reason"]
    chk = c["check"]
    if rr == "care_condition":
        return "care"
    if rr == "exception_missing":
        return "exception"
    if "声部" in chk or "角色" in chk:
        return "role_voice" if t == "clear" else "role_voice_with_sex"
    if "指令" in chk:
        return "injection"
    if "覆盖" in chk:
        return "multi_condition"
    if "否定" in chk or "历史" in chk or "咨询" in chk:
        return "quote_history"
    if "福利" in chk:
        return "welfare"
    if rr == "explicit_sex":
        return "core_sex"
    if rr == "marriage_birth":
        return "core_marriage"
    return "normal_condition"


def research_slice(c):
    b = c["evaluation_bucket"]
    if b == "core_signal":
        return "core_marriage" if c["review_reason"] == "marriage_birth" else "core_sex"
    if b == "care_auxiliary":
        return "care"
    if b == "exception_unknown":
        return "exception"
    if b == "context_review":
        return "context"
    if b == "outside_scope":
        return "training"
    if c["scope"] == "context_only":
        return "quote_history"
    if c["id"] in ("E045", "E047"):
        return "role_voice"
    if c["id"] == "E033":
        return "welcome"
    if any(k in c["text"] for k in ("不限", "不以", "无需", "均按")):
        return "negation"
    return "normal_condition"


def main():
    inputs, labels = [], []
    research = json.loads((PACK / "data" / "reviewed_cases.json").read_text(encoding="utf-8"))["cases"]
    for c in research:
        inputs.append({"id": c["id"], "text": c["text"], "set": "seed50"})
        labels.append({"id": c["id"], "set": "seed50", "label_source": SRC_RESEARCH,
                       "triage": c["triage"], "review_reason": c["review_reason"], "scope": c["scope"],
                       "sex_link": c["sex_link"], "care_condition": c["care_condition"],
                       "risk_quotes": c["risk_quotes"], "context_quotes": c["context_quotes"],
                       "evaluation_bucket": c["evaluation_bucket"], "slice": research_slice(c)})
    reg = json.loads((PACK / "data" / "regression_cases.json").read_text(encoding="utf-8"))["cases"]
    for c in reg:
        inputs.append({"id": c["id"], "text": c["text"], "set": "regression16"})
        labels.append({"id": c["id"], "set": "regression16", "label_source": SRC_REGRESSION,
                       "triage": c["expected_triage"], "review_reason": c["expected_review_reason"],
                       "check": c["check"], "slice": regression_slice(c)})
    smoke_text = {r["id"]: r["text"] for r in read_jsonl(ROOT / "data" / "smoke" / "smoke_inputs.jsonl")}
    for p in read_jsonl(OUT / "engineer_probes_v2.jsonl"):
        text = p.get("text") or smoke_text[p["id"]]
        inputs.append({"id": p["id"], "text": text, "set": p["set"]})
        lab = {k: v for k, v in p.items() if k not in ("text",)}
        lab["label_source"] = SRC_ENGINEER
        labels.append(lab)
    ids = [r["id"] for r in inputs]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for l in labels:
        for q in l.get("risk_quotes", []) + l.get("context_quotes", []):
            assert q in next(i["text"] for i in inputs if i["id"] == l["id"]), (l["id"], q)
    (OUT / "dev_inputs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in inputs), encoding="utf-8")
    (OUT / "dev_labels.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in labels), encoding="utf-8")
    build_whitelist()
    print(len(inputs), "dev items")


def build_whitelist():
    """Parse LEGAL_SOURCE_INDEX.md table verbatim; no law text is generated here."""
    md = (PACK / "LEGAL_SOURCE_INDEX.md").read_text(encoding="utf-8")
    rows = {}
    for line in md.splitlines():
        m = re.match(r"^\| (S\d\d) \| (.+) \|$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split(" | ")]
        doc, use, limit, link = cells[0], cells[1], cells[2], cells[3]
        urls = re.findall(r"\((https?://[^)]+)\)", link)
        rows[m.group(1)] = {"id": m.group(1), "document_level_date": doc, "articles_and_use": use,
                            "limits": limit, "urls": urls}
    assert len(rows) == 20, len(rows)
    meta = {"source_file": "data_v2/legal_pack/LEGAL_SOURCE_INDEX.md", "verified_as_of": "2026-10-28",
            "note": "逐字摘自法学交接包法源索引；程序与模型均不得新增法条。具体条款是否适用于个案须由法律审阅者确认。",
            "sources": rows}
    (OUT / "legal_sources_whitelist.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
