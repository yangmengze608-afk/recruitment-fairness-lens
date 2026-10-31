import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mvp import review_flow as rf  # noqa: E402

BASE = {"reviewer": "审核员A", "finding_decisions": [{"finding_index": 0, "decision": "accept"}]}
EV_OK = [{"description": "岗位说明书", "source": "发布方邮件", "verification": "self_reported"}]
EV_NONE = [{"description": "岗位说明书", "source": "", "verification": "not_obtained"}]


def v(**kw):
    return rf.validate_review({**BASE, **kw}, 1)


class ReviewFlowTests(unittest.TestCase):
    def test_closing_without_evidence_is_refused(self):
        for st in ("concern_supported", "exception_review", "job_requirement_supported"):
            self.assertTrue(v(human_outcome=st, next_step="交法律审阅", rationale="r"), st)
            self.assertTrue(v(human_outcome=st, next_step="交法律审阅", rationale="r", evidence=EV_NONE), st)
            self.assertEqual(v(human_outcome=st, next_step="交法律审阅", rationale="r", evidence=EV_OK), [], st)

    def test_pending_needs_missing_materials_and_next_step(self):
        self.assertTrue(v(human_outcome="pending_evidence"))
        self.assertTrue(v(human_outcome="pending_evidence", missing_materials="岗位说明书"))
        self.assertEqual(v(human_outcome="pending_evidence", missing_materials="岗位说明书", next_step="联系发布方"), [])

    def test_text_revised_needs_before_after_author_and_recheck(self):
        self.assertTrue(v(human_outcome="text_revised", revised_text="按能力评估", revised_by="审核员A"))
        self.assertEqual(v(human_outcome="text_revised", revised_text="按能力评估", revised_by="审核员A",
                           recheck_analysis_id="abc123"), [])

    def test_reviewer_required_and_unknown_status(self):
        self.assertTrue(rf.validate_review({"human_outcome": "unresolved", "rationale": "意见不一"}, 1))
        self.assertTrue(v(human_outcome="closed_ok"))
        self.assertEqual(v(human_outcome="unresolved", rationale="意见不一"), [])

    def test_cards_have_at_most_three_questions_and_keep_original(self):
        rec = {"triage": "flag", "findings": [
            {"quote": "限男性", "reason": "explicit_sex", "triage": "flag"},
            {"quote": "招聘女高音声部", "reason": "explicit_sex", "triage": "review", "scope_check": "performance_role_or_voice"},
            {"quote": "没有家庭负担", "reason": "care_condition", "triage": "review"}]}
        c = rf.build_cards(rec)["cards"]
        self.assertEqual([x["channel"] for x in c], ["explicit_sex", "role_voice", "care_condition"])
        self.assertTrue(all(len(x["questions"]) <= 3 and x["materials"] and x["role"] and x["basis"] for x in c))
        self.assertIn("限男性", c[0]["suggestion_template"])
        self.assertNotEqual(c[0]["lane_task"], c[2]["lane_task"])  # flag and review get different tasks


if __name__ == "__main__":
    unittest.main()
