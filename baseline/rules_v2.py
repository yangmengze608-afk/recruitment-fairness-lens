"""Baseline B: transparent rules revised for ANNOTATION_RULES v1.0 (version rules-v2.0-2026-10-29).

Baseline A (baseline/baseline.py) stays byte-identical to the starter kit. This file is a NEW rule set,
written by the AI engineer after reading the legal pack AND with the development set visible, so its
development-set numbers are optimistic. It emits the same model-side shape as Spark v2 and goes through
the same contract_v2 validation and derivation.

Pipeline: split into sentences -> clauses; drop cue words inside quotation marks; mark clauses that are
negated / historical / reported / educational; match cue patterns per reason; one finding per matched clause.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rfl.contract_v2 import derive_record, load_whitelist, validate_v2  # noqa: E402

RULES_VERSION = "rules-v2.0-2026-10-29"

QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|「[^」]*」")
SENT_SPLIT = re.compile(r"(?<=[。；;！!？?])")
CLAUSE_SPLIT = re.compile(r"(?<=[，,：:])")

DOC_CONTEXT = re.compile(r"^(新闻|报道|记者|培训|内训|讲义|公开课|调查问卷|问卷|公司官网文章|文章|请解释|我们反对|HR内训|招聘经理培训|培训案例)")
CLAUSE_NEGATED = re.compile(r"不限|不限制|均可|无需|不询问|不以|不得|反对|禁止|请勿|不要在|不应|已删除|已经作废|作废|已撤下|旧版|旧公告|以前|过去|曾写|均同|一样|欢迎")
TRAINING = re.compile(r"培训.{0,6}(招募|参与者|学员)|(招募|招收).{0,6}(学员|参与者)")

SEX = r"(男|女)(性|士|生|同志|的)?"
EXPLICIT_SEX = [
    re.compile(r"(限|仅限|只限|只招|仅招|只收|只要|仅面向|只考虑|仅考虑|需为|须为)" + SEX),
    re.compile(SEX + r"(应聘者)?(优先|慎投|慎重投递|勿扰|不考虑)"),
    re.compile(r"优先(录用|考虑)?" + SEX),
    re.compile(r"(更适合|比较合适|更合适)(小伙子|男|女)"),
    re.compile(r"(男|女)同志.{0,6}(合适|扛不住|慎)"),
    re.compile(r"(宝妈|妈妈|母亲|孕妇).{0,8}(勿扰|不考虑|不太合适|慎|不要|不招)"),
]
MARRIAGE_BIRTH = re.compile(r"已婚|未婚|已育|未育|婚育|生育|怀孕|妊娠|孕检|生孩子|育龄")
CARE = re.compile(r"(没有|无|不要有?)(家庭|育儿|照护|照顾|家里)[^，。]{0,4}(负担|牵挂|拖累)|家里没人需要照顾")
CONTEXT_HINT = re.compile(r"团队(都是|全是|清一色)(男|女)")
EXCEPTION = re.compile(r"国家规定|国家有关|特殊工种|禁忌作业|劳动保护规定|特殊岗位")


def strip_quotes(s):
    return QUOTED.sub(lambda m: "□" * len(m.group(0)), s)


def predict(rec):
    text = rec["text"]
    findings, context = [], []
    doc_context = bool(DOC_CONTEXT.search(text))
    scope = "context_only" if doc_context else "recruitment"
    if TRAINING.search(text) and "岗位" not in text:
        scope = "training"
    for sent in [s for s in SENT_SPLIT.split(text) if s]:
        sent_exception = bool(EXCEPTION.search(sent))
        if sent_exception and scope == "recruitment":
            q = sent.rstrip("。；;！!？?")
            sex = "explicit" if re.search(r"男|女", strip_quotes(q)) and "女职工" not in q else "unknown"
            findings.append({"quote": q, "reason": "exception_missing", "sex_link": sex, "care_condition": False})
            continue
        for clause in [c for c in CLAUSE_SPLIT.split(sent) if c]:
            q = clause.rstrip("，,：:。；;！!？?")
            if not q:
                continue
            visible = strip_quotes(q)
            if doc_context or scope != "recruitment" or CLAUSE_NEGATED.search(visible):
                if re.search(r"男|女|婚|育|孕|家庭|性别", q):
                    context.append(q)
                continue
            hit = None
            if any(p.search(visible) for p in EXPLICIT_SEX):
                hit = ("explicit_sex", "explicit", bool(re.search(r"妈妈|宝妈|母亲|孩子", visible)))
            elif MARRIAGE_BIRTH.search(visible):
                hit = ("marriage_birth", "explicit" if re.search(r"女|男", visible) else "none", False)
            elif CARE.search(visible):
                hit = ("care_condition", "unestablished", True)
            elif CONTEXT_HINT.search(visible):
                q = sent.rstrip("。；;！!？?")
                hit = ("context", "suggested", False)
            if hit:
                findings.append({"quote": q, "reason": hit[0], "sex_link": hit[1], "care_condition": hit[2]})
    return {"id": rec["id"], "scope": scope, "findings": findings, "context_quotes": context,
            "missing_facts": "规则基线不生成待核事实，请人工补充。" if findings else "",
            "rationale": f"{RULES_VERSION} 关键词与语境规则匹配结果。"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wl = load_whitelist()
    rows = [json.loads(s) for s in Path(a.input).read_text(encoding="utf-8").splitlines() if s.strip()]
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as pf, (out / "records.jsonl").open("w", encoding="utf-8") as rf:
        for r in rows:
            rec = {"id": r["id"], "text": r["text"]}
            obj = predict(rec)
            v, w = validate_v2(obj, rec["id"], rec["text"])
            pf.write(json.dumps({"id": rec["id"], "prediction": obj, "violations": v, "warnings": w}, ensure_ascii=False) + "\n")
            rf.write(json.dumps(derive_record(obj, v, w, rec["id"], rec["text"], wl), ensure_ascii=False) + "\n")
    (out / "run_meta.json").write_text(json.dumps({"baseline": "B", "rules_version": RULES_VERSION, "input": a.input,
                                                   "n": len(rows)}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
