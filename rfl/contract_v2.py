"""Four-way triage contract v2 (follows data_v2/legal_pack/ANNOTATION_RULES.md v1.0).

Split of responsibility:
  model   -> scope, findings[{quote, reason, sex_link, care_condition}], context_quotes, missing_facts, rationale
  program -> per-finding triage, document triage, review_reason, sex_link, care_condition, risk_quotes,
             needs_human_review, source_ids / legal sources (whitelist only), legal_conclusion
Nothing the model returns is repaired. A hard violation makes the prediction `invalid`; invalid output is
routed to human review and stays in every evaluation denominator (never converted to clear).
"""
import json
import re
from pathlib import Path

from rfl.contract import LEGAL_CONCLUSION_PATTERNS, extract_json  # noqa: F401  (re-exported)

CONTRACT_VERSION = "v2-2026-10-29"
TRIAGES = ("flag", "review", "clear", "unknown")
TRIAGE_ZH = {"flag": "明确需要复核", "review": "语境不明需复核", "clear": "未见此类风险线索", "unknown": "暂无法判断"}
SCOPES = ("recruitment", "context_only", "training", "insufficient")
REASONS = ("explicit_sex", "marriage_birth", "care_condition", "context", "exception_missing")
SEX_LINKS = ("explicit", "suggested", "unestablished", "none", "unknown")
MODEL_KEYS = {"id", "scope", "findings", "context_quotes", "missing_facts", "rationale"}
FINDING_KEYS = {"quote", "reason", "sex_link", "care_condition"}

# ANNOTATION_RULES 分流顺序第4、5条：reason -> triage。界面汇总优先级 flag > unknown > review > clear（不是法律严重程度）。
REASON_TRIAGE = {"explicit_sex": "flag", "marriage_birth": "flag", "exception_missing": "unknown",
                 "care_condition": "review", "context": "review"}
PRIORITY = {"flag": 3, "unknown": 2, "review": 1, "clear": 0}

# reason -> 白名单法源ID（取自 reviewed_cases.json 中同类 review_reason 的 source_ids 并集）。
# 只显示 LEGAL_SOURCE_INDEX 的原文条目；个案具体条款适用一律“待法律审阅者确认”。
REASON_SOURCES = {"explicit_sex": ["S01", "S02", "S03", "S04"], "marriage_birth": ["S01", "S02"],
                  "care_condition": ["S02", "S04", "S07", "S08"], "context": ["S02", "S04"],
                  "exception_missing": ["S01", "S05"]}

WHITELIST_PATH = Path(__file__).resolve().parents[1] / "data_v2" / "legal_sources_whitelist.json"


def _legal_hits(s):
    return [p for p in LEGAL_CONCLUSION_PATTERNS if re.search(p, s or "")]


def validate_v2(obj, source_id, text):
    """Return (violations, warnings). violations => invalid prediction."""
    v, w = [], []
    if not isinstance(obj, dict):
        return ["unparseable"], w
    missing = MODEL_KEYS - obj.keys()
    extra = obj.keys() - MODEL_KEYS
    v += [f"missing_key:{k}" for k in sorted(missing)]
    if extra:
        v.append("extra_keys:" + ",".join(sorted(extra)))
    if obj.get("id") != source_id:
        v.append("id_mismatch")
    if obj.get("scope") not in SCOPES:
        v.append("bad_scope")
    findings = obj.get("findings")
    if not isinstance(findings, list):
        v.append("findings_not_list")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            v.append(f"finding{i}:not_object")
            continue
        if set(f) != FINDING_KEYS:
            v.append(f"finding{i}:bad_keys")
        q = f.get("quote")
        if not isinstance(q, str) or not q.strip():
            v.append(f"finding{i}:quote_empty")
        elif q not in text:
            v.append(f"finding{i}:quote_not_substring")
        if f.get("reason") not in REASONS:
            v.append(f"finding{i}:bad_reason")
        if f.get("sex_link") not in SEX_LINKS:
            v.append(f"finding{i}:bad_sex_link")
        if not isinstance(f.get("care_condition"), bool):
            v.append(f"finding{i}:care_not_bool")
        if f.get("reason") == "care_condition" and f.get("sex_link") in ("explicit", "suggested"):
            w.append(f"finding{i}:care_with_sex_inference")
    cq = obj.get("context_quotes")
    if not isinstance(cq, list) or not all(isinstance(x, str) for x in cq):
        v.append("context_quotes_not_str_list")
    else:
        for j, q in enumerate(cq):
            if q and q not in text:
                v.append(f"context{j}:quote_not_substring")
    for k in ("missing_facts", "rationale"):
        if k in obj and not isinstance(obj[k], str):
            v.append(f"{k}_not_string")
        elif _legal_hits(obj.get(k)):
            v.append(f"{k}_legal_conclusion")
    if not isinstance(obj.get("rationale"), str) or not obj.get("rationale", "").strip():
        v.append("rationale_empty")
    if obj.get("scope") in ("context_only", "training") and findings:
        w.append("findings_outside_recruitment_scope")
    return v, w


def load_whitelist():
    return json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))["sources"]


def derive_record(obj, violations, warnings, source_id, text, whitelist=None):
    """Program-side derivation of the full v2 record. Never invents content for invalid output."""
    rec = {"id": source_id, "text": text, "contract_version": CONTRACT_VERSION,
           "legal_conclusion": "not_determined", "confidence": "not_provided（模型不输出置信度；未做统计校准）",
           "model_violations": violations, "model_warnings": warnings, "human_status": "pending_human_review"}
    if violations:
        rec.update(triage="invalid", label="模型输出未通过校验，需人工处理", scope=None, findings=[], risk_quotes=[],
                   context_quotes=[], review_reason="model_output_invalid", sex_link=None, care_condition=None,
                   missing_facts="", rationale="", source_ids=[], legal_sources=[], needs_human_review=True)
        return rec
    findings = []
    for f in obj["findings"]:
        findings.append({**f, "triage": REASON_TRIAGE[f["reason"]]})
    findings.sort(key=lambda f: -PRIORITY[f["triage"]])
    if findings:
        triage = findings[0]["triage"]
    else:
        triage = "unknown" if obj["scope"] == "insufficient" else "clear"
    top = findings[0] if findings else None
    source_ids = []
    for f in findings:
        for s in REASON_SOURCES[f["reason"]]:
            if s not in source_ids:
                source_ids.append(s)
    wl = whitelist or {}
    rec.update(
        triage=triage, label=TRIAGE_ZH[triage], scope=obj["scope"], findings=findings,
        risk_quotes=[f["quote"] for f in findings], context_quotes=obj["context_quotes"],
        review_reason=top["reason"] if top else ("exception_missing" if triage == "unknown" else "none"),
        all_review_reasons=sorted({f["reason"] for f in findings}),
        sex_link=top["sex_link"] if top else "none",
        care_condition=any(f["care_condition"] for f in findings),
        missing_facts=obj["missing_facts"], rationale=obj["rationale"],
        source_ids=source_ids,
        legal_sources=[{**wl[s], "applicability": "待法律审阅者确认"} for s in source_ids if s in wl],
        needs_human_review=triage != "clear",
    )
    return rec
