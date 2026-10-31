"""Output contract from SPARK_INTERFACE.md and its programmatic checks.

These checks validate *structure and evidence provenance* only. They say
nothing about legal correctness.
"""
import json
import re

STATUSES = ("flag", "review", "clear")
ISSUE_TYPES = ("sex_preference", "marital_reproductive", "contextual_bias", "special_context", "none")
REQUIRED_KEYS = ("id", "status", "issue_type", "evidence", "reason", "needs_human_review")

# Definitive legal conclusions the model must not emit (SPARK_INTERFACE.md).
# Matching is deliberately simple; hits are reported, not silently repaired.
LEGAL_CONCLUSION_PATTERNS = [r"(?<!是否)(?<!涉嫌)违法", r"(?<!是否)合法", r"无需审核", r"构成歧视", r"已证明"]


def extract_json(raw):
    """Return (obj, error). Strips an optional <think>...</think> block and code fences,
    then parses the first top-level JSON object. Never invents fields."""
    text = raw
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return None, "no_json_object"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    return None, f"json_decode_error: {e}"
                if not isinstance(obj, dict):
                    return None, "not_an_object"
                trailing = text[i + 1 :].strip()
                return obj, ("trailing_text" if trailing else None)
    return None, "unterminated_json"


def validate(obj, source_id, source_text):
    """Return a list of violation codes (empty == contract satisfied)."""
    v = []
    if obj is None:
        return ["unparseable"]
    for k in REQUIRED_KEYS:
        if k not in obj:
            v.append(f"missing_key:{k}")
    extra = set(obj) - set(REQUIRED_KEYS)
    if extra:
        v.append("extra_keys:" + ",".join(sorted(extra)))
    if obj.get("id") != source_id:
        v.append("id_mismatch")
    if obj.get("status") not in STATUSES:
        v.append("bad_status")
    if obj.get("issue_type") not in ISSUE_TYPES:
        v.append("bad_issue_type")
    ev = obj.get("evidence")
    if not isinstance(ev, str):
        v.append("evidence_not_string")
    elif ev and ev not in source_text:
        # Exact, un-normalised substring: full-width punctuation must match too.
        v.append("evidence_not_substring")
    elif not ev and obj.get("status") in ("flag", "review"):
        v.append("evidence_empty_for_nonclear")
    if not isinstance(obj.get("needs_human_review"), bool):
        v.append("needs_human_review_not_bool")
    if obj.get("status") in ("flag", "review") and obj.get("needs_human_review") is False:
        v.append("nonclear_without_human_review")
    if obj.get("status") == "clear" and obj.get("issue_type") not in (None, "none"):
        v.append("clear_with_issue_type")
    if obj.get("status") in ("flag", "review") and obj.get("issue_type") == "none":
        v.append("nonclear_with_issue_none")
    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        v.append("reason_empty")
    else:
        for p in LEGAL_CONCLUSION_PATTERNS:
            if re.search(p, reason):
                v.append("reason_legal_conclusion")
                break
    return v
