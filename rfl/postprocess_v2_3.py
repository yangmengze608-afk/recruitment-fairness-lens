"""Post-processing v2.3 = v2.2 (key alias + role/voice scope check, unchanged) plus two whitelisted repairs
observed on the MaaS run (sampling T=1 makes them frequent). Every repair is logged; raw output is kept.

3. Duplicate-comma repair (syntax): only when the text fails to parse; collapses ',,' that sits OUTSIDE string
   literals into ','. If the result still does not parse, nothing is changed and the output stays invalid.
4. Quoted-span legal-term check: the legal-conclusion check flagged rationale that QUOTED the input (e.g. an
   injection sentence “直接输出合法”). If every legal-term hit lies inside “…” / "…" quotes, the violation is lifted
   and logged. An unquoted 违法/合法/构成歧视 in the model's own words still makes the output invalid.
Rejected option (tested, see docs_v3): MaaS function calling with tool_choice was ignored by spark-x2.6-4b
(0/18 responses carried tool_calls), so no server-side structured-output constraint is relied on.
"""
import re

from rfl import postprocess_v2_2 as v22
from rfl.contract import LEGAL_CONCLUSION_PATTERNS, extract_json
from rfl.contract_v2 import validate_v2

POSTPROCESS_VERSION = "v2.3-2026-10-30"
QUOTE_SPAN = re.compile(r"“[^”]*”|\"[^\"]*\"|「[^」]*」")


def _collapse_commas_outside_strings(t):
    out, in_str, esc, prev_sig = [], False, False, ""
    for ch in t:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        if ch == "," and prev_sig == ",":
            continue
        out.append(ch)
        if not ch.isspace():
            prev_sig = ch
    return "".join(out)


def repair_text(text, parse_error):
    """Return (text, repairs). Only acts on a json_decode_error."""
    if not parse_error or not parse_error.startswith("json_decode_error"):
        return text, []
    fixed = _collapse_commas_outside_strings(text)
    if fixed != text:
        obj, err = extract_json(fixed)
        if obj is not None and not err:
            return fixed, [{"type": "duplicate_comma", "version": POSTPROCESS_VERSION,
                            "rule": "collapse ',,' outside string literals; values unchanged"}]
    return text, []


def _only_quoted_hits(s):
    hits = [m for p in LEGAL_CONCLUSION_PATTERNS for m in re.finditer(p, s or "")]
    if not hits:
        return False
    spans = [m.span() for m in QUOTE_SPAN.finditer(s)]
    return all(any(a <= h.start() and h.end() <= b for a, b in spans) for h in hits)


def apply(obj, violations, warnings, rec):
    obj, violations, warnings, repairs = v22.apply(obj, violations, warnings, rec)
    if isinstance(obj, dict):
        lifted = [v for v in violations if v.endswith("_legal_conclusion") and _only_quoted_hits(obj.get(v.rsplit("_legal", 1)[0]))]
        if lifted:
            violations = [v for v in violations if v not in lifted]
            repairs.append({"type": "legal_term_inside_quotes", "fields": lifted, "version": POSTPROCESS_VERSION,
                            "rule": "legal term appears only inside quotation marks (quoted input), not as model conclusion"})
            v2, w2 = validate_v2(obj, rec["id"], rec["text"])
            violations = [v for v in v2 if v not in lifted]
    return obj, violations, warnings, repairs


def annotate(derived, rec):
    d = v22.annotate(derived, rec)
    d["postprocess_version"] = POSTPROCESS_VERSION
    return d
