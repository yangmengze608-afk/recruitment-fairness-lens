"""Post-processing v2.2 (prompt text stays v2.1, frozen). Two separately logged, deterministic steps.

1. Key-alias repair (engineering, not legal):
   Applies only when a REQUIRED key is missing AND there is exactly one unexpected top-level key whose name is a
   near-miss of it (shares the first 7 characters, e.g. missing_fs / missing_fotes -> missing_facts). Values are
   never changed. Every repair is recorded; the raw model output is kept untouched in raw.jsonl.
   Anything else (unparseable JSON, two unknown keys, wrong enum values) stays INVALID and goes to a human.

2. Performance role / voice scope check (scope module, NOT a validated legal rule):
   A finding the model labelled explicit_sex whose quote describes a stage role or vocal part
   (扮演/饰演/角色/声部/女高音/女中音/男高音/男中音/男低音) and that does NOT also restrict the applicant
   (限/仅/只/需为/须为/要求 + 男/女) is downgraded from flag to review with scope_check=performance_role_or_voice.
   It is never auto-cleared: a person confirms whether it is a role description or an applicant restriction.
   Basis: ANNOTATION_RULES v1.0 (E045/E047: role / voice is not an applicant sex limit; R008: an explicit applicant
   limit stays flag). Dev-set observation: prompt-only fixes failed 4/4.
"""
import re

from rfl.contract_v2 import MODEL_KEYS, PRIORITY, REASON_TRIAGE, TRIAGE_ZH, validate_v2

POSTPROCESS_VERSION = "v2.2-2026-10-30"
ROLE_VOICE = re.compile(r"扮演|饰演|角色|声部|女高音|女中音|男高音|男中音|男低音")
APPLICANT_LIMIT = re.compile(r"(限|仅|只|需为|须为|要求)[^，。；;]{0,4}(男|女)")


def apply(obj, violations, warnings, rec):
    repairs = []
    if not isinstance(obj, dict):
        return obj, violations, warnings, repairs
    missing = [k for k in MODEL_KEYS if k not in obj]
    extra = [k for k in obj if k not in MODEL_KEYS]
    if len(missing) == 1 and len(extra) == 1 and missing[0][:7] == extra[0][:7]:
        fixed = dict(obj)
        fixed[missing[0]] = fixed.pop(extra[0])
        v2, w2 = validate_v2(fixed, rec["id"], rec["text"])
        if not v2:
            repairs.append({"type": "key_alias", "from": extra[0], "to": missing[0], "version": POSTPROCESS_VERSION,
                            "rule": "single near-miss key (same 7-char prefix); value unchanged"})
            return fixed, v2, w2 + ["repaired:key_alias"], repairs
    return obj, violations, warnings, repairs


def annotate(derived, rec):
    derived["postprocess_version"] = POSTPROCESS_VERSION
    derived["scope_checks"] = []
    if derived.get("triage") == "invalid":
        return derived
    changed = False
    for f in derived.get("findings", []):
        q = f.get("quote", "")
        if f.get("reason") == "explicit_sex" and ROLE_VOICE.search(q) and not APPLICANT_LIMIT.search(q):
            f["triage"] = "review"
            f["scope_check"] = "performance_role_or_voice"
            f["scope_note"] = "可能是角色或声部描述，不一定是对应聘者本人性别的限定；需人工确认。"
            derived["scope_checks"].append({"quote": q, "from": "flag", "to": "review", "rule": "performance_role_or_voice"})
            changed = True
    if changed:
        fs = sorted(derived["findings"], key=lambda f: -PRIORITY[f["triage"]])
        derived["findings"] = fs
        derived["triage"] = fs[0]["triage"]
        derived["label"] = TRIAGE_ZH[derived["triage"]]
        derived["review_reason"] = "context" if fs[0].get("scope_check") else fs[0]["reason"]
        derived["needs_human_review"] = True
    return derived


assert set(REASON_TRIAGE) >= {"explicit_sex"}
