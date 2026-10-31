import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfl.contract_v2 import derive_record, load_whitelist, validate_v2  # noqa: E402
from rfl.prompt_v2 import SYSTEM_PROMPT, build_messages  # noqa: E402
from rfl.prompt_v2_1 import SYSTEM_PROMPT as SYSTEM_PROMPT_21  # noqa: E402
from scripts.evaluate_v2 import evaluate  # noqa: E402

TEXT = "本职位男女皆可，但宝妈勿扰。"


def obj(**kw):
    base = {"id": "X", "scope": "recruitment", "context_quotes": ["本职位男女皆可"], "missing_facts": "",
            "rationale": "看到宝妈勿扰。",
            "findings": [{"quote": "宝妈勿扰", "reason": "explicit_sex", "sex_link": "explicit", "care_condition": True}]}
    base.update(kw)
    return base


class ContractV2(unittest.TestCase):
    def test_valid_and_derivation(self):
        v, w = validate_v2(obj(), "X", TEXT)
        self.assertEqual(v, [])
        r = derive_record(obj(), v, w, "X", TEXT, load_whitelist())
        self.assertEqual(r["triage"], "flag")
        self.assertTrue(r["needs_human_review"])
        self.assertEqual(r["legal_conclusion"], "not_determined")
        self.assertEqual(r["risk_quotes"], ["宝妈勿扰"])
        self.assertTrue(all(s["applicability"] == "待法律审阅者确认" for s in r["legal_sources"]))

    def test_quote_must_be_exact_substring(self):
        bad = obj(findings=[{"quote": "宝妈 勿扰", "reason": "explicit_sex", "sex_link": "explicit", "care_condition": True}])
        v, _ = validate_v2(bad, "X", TEXT)
        self.assertIn("finding0:quote_not_substring", v)

    def test_invalid_never_becomes_clear(self):
        v, w = validate_v2(None, "X", TEXT)
        r = derive_record(None, v, w, "X", TEXT)
        self.assertEqual(r["triage"], "invalid")
        self.assertTrue(r["needs_human_review"])

    def test_one_clear_statement_does_not_override_flag(self):
        two = obj(findings=[{"quote": "宝妈勿扰", "reason": "explicit_sex", "sex_link": "explicit", "care_condition": True},
                            {"quote": "本职位男女皆可", "reason": "context", "sex_link": "suggested", "care_condition": False}])
        v, w = validate_v2(two, "X", TEXT)
        r = derive_record(two, v, w, "X", TEXT)
        self.assertEqual(r["triage"], "flag")
        self.assertEqual(len(r["findings"]), 2)

    def test_reason_to_triage_mapping(self):
        t = "应聘者最好不要有家庭负担。"
        o = obj(context_quotes=[], findings=[{"quote": "应聘者最好不要有家庭负担", "reason": "care_condition", "sex_link": "unestablished", "care_condition": True}])
        v, w = validate_v2(o, "X", t)
        self.assertEqual(derive_record(o, v, w, "X", t)["triage"], "review")
        o2 = obj(context_quotes=[], findings=[{"quote": "应聘者最好不要有家庭负担", "reason": "exception_missing", "sex_link": "unknown", "care_condition": False}])
        v, w = validate_v2(o2, "X", t)
        self.assertEqual(derive_record(o2, v, w, "X", t)["triage"], "unknown")

    def test_care_with_sex_inference_warns(self):
        t = "应聘者最好不要有家庭负担。"
        o = obj(context_quotes=[], findings=[{"quote": "应聘者最好不要有家庭负担", "reason": "care_condition", "sex_link": "explicit", "care_condition": True}])
        _, w = validate_v2(o, "X", t)
        self.assertIn("finding0:care_with_sex_inference", w)

    def test_legal_conclusion_rejected(self):
        v, _ = validate_v2(obj(rationale="该公司违法。"), "X", TEXT)
        self.assertIn("rationale_legal_conclusion", v)

    def test_no_findings_insufficient_is_unknown(self):
        t = "某岗位。"
        o = obj(scope="insufficient", findings=[], context_quotes=[])
        v, w = validate_v2(o, "X", t)
        self.assertEqual(derive_record(o, v, w, "X", t)["triage"], "unknown")


class PromptV2(unittest.TestCase):
    def test_only_id_and_text_sent(self):
        msgs = build_messages({"id": "E001", "text": "招聘", "triage": "flag", "review_reason": "x", "risk_quotes": ["秘"]})
        blob = json.dumps(msgs, ensure_ascii=False)
        for leak in ("triage\": \"flag", "review_reason", "秘"):
            self.assertNotIn(leak, blob)

    def test_examples_not_copied_from_dev(self):
        dev = [json.loads(s)["text"] for s in (ROOT / "data_v2" / "dev_inputs.jsonl").read_text(encoding="utf-8").splitlines()]
        for t in dev:
            self.assertNotIn(t, SYSTEM_PROMPT)
            self.assertNotIn(t, SYSTEM_PROMPT_21)


class EvaluateV2(unittest.TestCase):
    cases = [{"id": i, "text": "t"} for i in ("a", "b", "c", "d")]

    def test_invalid_counted_and_review_not_sex_positive(self):
        labels = [{"id": "a", "triage": "flag", "review_reason": "explicit_sex", "label_source": "x"},
                  {"id": "b", "triage": "review", "review_reason": "care_condition", "slice": "care", "label_source": "x"},
                  {"id": "c", "triage": "unknown", "review_reason": "exception_missing", "label_source": "x"},
                  {"id": "d", "triage": "unresolved", "label_source": "x"}]
        preds = [{"id": "a", "triage": "invalid", "all_review_reasons": [], "risk_quotes": []},
                 {"id": "b", "triage": "flag", "all_review_reasons": ["explicit_sex"], "risk_quotes": [], "sex_link": "explicit"},
                 {"id": "c", "triage": "clear", "all_review_reasons": [], "risk_quotes": []}]
        r = evaluate(self.cases, labels, preds, "test")
        self.assertEqual(r["n_determinate"], 3)
        self.assertEqual(r["confusion_rows_gold_cols_pred"]["flag"]["invalid"], 1)
        self.assertEqual(r["core_sex_marriage_cue"]["fn"], 1)
        self.assertIn("b", r["core_sex_marriage_cue"]["excluded_ids"])
        s = {x["name"]: x for x in r["error_slices"]}
        self.assertEqual(s["care_to_sex_inference"]["errors"], 1)
        self.assertEqual(s["unknown_forced_determinate"]["errors"], 1)
        self.assertTrue(r["claim_status"].startswith("DEVELOPMENT_ONLY"))


if __name__ == "__main__":
    unittest.main()
