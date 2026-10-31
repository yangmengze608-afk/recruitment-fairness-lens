import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from rfl.contract import extract_json, validate  # noqa: E402
from rfl.prompt import SYSTEM_PROMPT, build_messages  # noqa: E402
import evaluate  # noqa: E402

GOOD = {"id": "T1", "status": "flag", "issue_type": "sex_preference", "evidence": "限男性",
        "reason": "出现性别限定表述，需人工复核", "needs_human_review": True}


class ContractTests(unittest.TestCase):
    def test_good(self):
        self.assertEqual(validate(GOOD, "T1", "招聘司机，限男性。"), [])

    def test_evidence_must_be_exact_substring(self):
        bad = dict(GOOD, evidence="限男")  # substring -> fine
        self.assertEqual(validate(bad, "T1", "招聘司机，限男性。"), [])
        bad = dict(GOOD, evidence="仅限男性")
        self.assertIn("evidence_not_substring", validate(bad, "T1", "招聘司机，限男性。"))

    def test_fullwidth_punctuation_not_normalised(self):
        bad = dict(GOOD, evidence="司机,限男性")  # half-width comma
        self.assertIn("evidence_not_substring", validate(bad, "T1", "招聘司机，限男性。"))

    def test_enum_and_id(self):
        v = validate(dict(GOOD, status="illegal", id="X"), "T1", "限男性")
        self.assertIn("bad_status", v)
        self.assertIn("id_mismatch", v)

    def test_legal_conclusion_in_reason(self):
        self.assertIn("reason_legal_conclusion", validate(dict(GOOD, reason="该表述违法"), "T1", "限男性"))
        self.assertNotIn("reason_legal_conclusion", validate(dict(GOOD, reason="可能涉嫌违法，需人工核查"), "T1", "限男性"))

    def test_extract_json_with_thinking_and_fence(self):
        raw = "<think>想一想 {不是json}</think>\n```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"
        obj, err = extract_json(raw)
        self.assertEqual(obj, GOOD)
        self.assertIsNone(err)

    def test_extract_json_failure_not_repaired(self):
        obj, err = extract_json('{"id": "T1", "status": "flag"')
        self.assertIsNone(obj)
        self.assertEqual(err, "unterminated_json")
        self.assertEqual(validate(None, "T1", "x"), ["unparseable"])


class PromptLeakTests(unittest.TestCase):
    def test_draft_fields_never_sent(self):
        rec = {"id": "E001", "text": "招聘客服专员，仅限男性。", "draft_status": "flag",
               "draft_issue_type": "sex_preference", "challenge": "explicit-sex", "review_notes": "SECRET"}
        blob = json.dumps(build_messages(rec), ensure_ascii=False)
        for leaked in ("draft", "explicit-sex", "SECRET", '"flag"'):
            self.assertNotIn(leaked, blob)
        self.assertIn("招聘客服专员，仅限男性。", blob)

    def test_system_prompt_has_no_case_text(self):
        seed = (ROOT / "data" / "seed_cases.jsonl").read_text(encoding="utf-8").splitlines()
        for line in seed:
            self.assertNotIn(json.loads(line)["text"], SYSTEM_PROMPT)


class EvaluatorTests(unittest.TestCase):
    cases = [{"id": "A", "text": "限男性"}, {"id": "B", "text": "男女不限"}, {"id": "C", "text": "不确定"}]

    def test_unresolved_excluded_and_invalid_counted(self):
        labels = [{"id": "A", "status": "flag"}, {"id": "B", "status": "clear", "slice": "negation"},
                  {"id": "C", "status": "unresolved"}]
        preds = [{"id": "A", "prediction": None, "violations": ["parse:no_json_object"]},
                 {"id": "B", "prediction": dict(GOOD, id="B", status="flag", evidence="男女不限"), "violations": []}]
        rep = evaluate.evaluate(self.cases, labels, preds, "test")
        self.assertEqual(rep["n_unresolved"], 1)
        self.assertEqual(rep["confusion_rows_gold_cols_pred"]["flag"]["invalid"], 1)
        self.assertEqual(rep["negation_or_quote_false_alarm"]["rate"], 1.0)
        self.assertTrue(rep["claim_status"].startswith("INTERNAL_DEV_ONLY"))

    def test_only_human_frozen_is_reportable(self):
        rep = evaluate.evaluate(self.cases, [{"id": "B", "status": "clear"}],
                                [dict(GOOD, id="B", status="clear", issue_type="none", evidence="", needs_human_review=False)],
                                "human_frozen")
        self.assertEqual(rep["claim_status"], "ELIGIBLE_FOR_REPORTING")


if __name__ == "__main__":
    unittest.main()
