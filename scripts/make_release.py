"""Build the public source package (policy v2, 2026-10-31). Original files are never modified.

  python3 scripts/make_release.py

Authorisation (法学联合研究者, public name "608", via the project lead on 2026-10-31):
  AUTHORISED   frozen Prompt v2.1 verbatim (incl. its examples), annotation rules / triage principles, the SOP review
               questions and status names used by the product, the verified legal-source whitelist with scope notes.
  NOT YET      the 50 AI-assisted research labels, the 16 regression cases R001-R016, research memos
               (LEGAL_REVIEW_NOTES, FAMILY_RESPONSIBILITY_RESEARCH, CASE_ANALYSIS, SEARCH_LOG, DECISION_RECORD, ...),
               the original pack itself, any locked-test material.
Policy:
  - excluded: .venv, caches, weights, mvp/logs, data_v2/legal_pack, research labels, gold-label eval reports,
    docs quoting labels / regression texts, internal drafts and checklists, hidden files
  - filtered: JSONL / log rows of R001-R016 are dropped (the public logs are therefore FILTERED copies, otherwise verbatim)
  - sanitised: home / scratch paths
  - verified: frozen prompt byte-identical to the freeze record; no regression text; no CJK run (>=10 chars) shared with
    the still-unauthorised research files unless it is a starter-kit case text; no key/token/home path; no hidden file
"""
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data_v2" / "legal_pack"
SECRET = re.compile(r"ak-[0-9a-f]{20,}|gho_\w{10,}|ghp_\w{10,}|hf_[A-Za-z0-9]{20,}|Bearer\s+ak-")
EXCLUDE_DIRS = {".venv", "__pycache__", "release", "logs"}
EXCLUDE_PREFIX = ["data_v2/legal_pack/", "outputs_v2/eval/", "outputs/internal_dev/", "outputs_locked/", "docs_v5/private/", "docs_v5/SHAREABLE_RULES/"]
EXCLUDE_FILES = {"data_v2/dev_labels.jsonl", "docs_v2/LEGAL_PACK_INTEGRATION.md", "docs_v2/FAILURES_V2.md",
                 "docs_v4/demo/analyses.jsonl", "docs_v4/demo/reviews.jsonl",
                 "docs_v4/FINAL_HF_DISCUSSION.md", "docs_v4/FINAL_GITHUB_ISSUE_REPLY.md",
                 "docs_v3/HF_SUBMISSION_DRAFT.md", "docs_v4/HF_DISCUSSION_DRAFT.md", "docs_v4/SUBMISSION_CHECKLIST.md",
                 "docs_v4/SUBMISSION_READY_CHECKLIST.md", "docs_v4/DEMO_WALKTHROUGH.md", "docs_v4/GITHUB_ISSUE_REPLY_DRAFT.md",
                 "docs_v3/ORGANIZER_QUERY_DRAFT.md", "docs_v4/PUBLIC_README.md", "docs_v4/PUBLIC_REPO_RECORD.md",
                 "docs_v4/RELEASE_NOTE_v2.txt"}
EXCLUDE_RE = [re.compile(r"^outputs_v3/eval_.*\.json$"), re.compile(r"^outputs_v2/.*/eval.*\.json$"),
              re.compile(r"^docs_v[34]/demo/.*\.png$"), re.compile(r".*/smoke_check\.json$")]
R_ID = re.compile(r'"id":\s*"R\d{3}"')
# still-unauthorised research files used for the overlap check (rules, SOP and source index are authorised)
UNAUTHORISED = ["LEGAL_REVIEW_NOTES.md", "START_HERE_FOR_GPT.md", "DECISION_RECORD.md", "VALIDATION.md",
                "research/FAMILY_RESPONSIBILITY_RESEARCH.md", "research/CASE_ANALYSIS.md", "research/SEARCH_LOG.md",
                "data/reviewed_cases.json", "data/regression_cases.json"]
AUTHORISED_PACK_FILES = ["ANNOTATION_RULES.md", "HUMAN_REVIEW_SOP.md", "LEGAL_SOURCE_INDEX.md"]
# product wording that came from the unauthorised family-responsibility memo; replaced in the live UI since 10-31
REWRITES = [("岗位条件待核实。现有文字不能确定其与性别或婚育状态有关。", "这是岗位条件，需结合实际职责核实；单凭这段文字，看不出它与应聘者的性别或婚育有关。")]


def main():
    freeze = json.loads((ROOT / "docs_v3/FREEZE_v2.1_pp2.3.json").read_text(encoding="utf-8"))
    reg_texts = [c["text"] for c in json.loads((PACK / "data/regression_cases.json").read_text(encoding="utf-8"))["cases"]]
    seeds = [json.loads(x)["text"] for x in (ROOT / "data/seed_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    home = str(Path.home())
    tmp = Path(tempfile.mkdtemp()) / "recruitment-fairness-lens"
    stats = {"files": 0, "excluded": 0, "rows_dropped": 0, "sanitised": 0, "rewrites": 0}
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if not p.is_file() or any(part in EXCLUDE_DIRS or part.startswith(".") for part in Path(rel).parts):
            continue
        if rel in EXCLUDE_FILES or any(rel.startswith(x) for x in EXCLUDE_PREFIX) or any(r.match(rel) for r in EXCLUDE_RE):
            stats["excluded"] += 1
            continue
        dst = tmp / ("docs/DEV_LOG_README.md" if rel == "README.md" else rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        stats["files"] += 1
        if p.suffix in (".png", ".xlsx", ".gz", ".zip") or rel == "rfl/prompt_v2_1.py":  # prompt stays byte-identical
            shutil.copy2(p, dst)
            continue
        t = p.read_text(encoding="utf-8")
        for a_, b_ in REWRITES:
            if rel != "scripts/make_release.py":
                stats["rewrites"] += t.count(a_)
                t = t.replace(a_, b_)
        if p.suffix in (".jsonl", ".log"):
            lines = t.splitlines()
            kept = [x for x in lines if not R_ID.search(x) and not re.match(r"^R\d{3}\b", x)]
            stats["rows_dropped"] += len(lines) - len(kept)
            t = "\n".join(kept) + ("\n" if kept else "")
        t2 = re.sub(r"/private/tmp/claude-\d+/[^\"\s]*", "<scratchpad>", t.replace(home, "~"))
        stats["sanitised"] += t2 != t
        dst.write_text(t2, encoding="utf-8")
    (tmp / "README.md").write_text((ROOT / "docs_v4/PUBLIC_README.md").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp / "RELEASE_NOTE.txt").write_text((ROOT / "docs_v4/RELEASE_NOTE_v2.txt").read_text(encoding="utf-8").format(**stats), encoding="utf-8")

    problems = []
    if hashlib.sha256((tmp / "rfl/prompt_v2_1.py").read_bytes()).hexdigest() != freeze["prompt_file_sha256"]:
        problems.append("prompt_not_frozen_bytes")
    unauth = re.sub(r"\s+", "", "".join((PACK / f).read_text(encoding="utf-8") for f in UNAUTHORISED))
    # text that is authorised in full: overlaps fully contained in it are allowed
    authorised = re.sub(r"\s+", "", "".join([(PACK / f).read_text(encoding="utf-8") for f in AUTHORISED_PACK_FILES]
                                             + [(ROOT / "rfl/prompt_v2_1.py").read_text(encoding="utf-8"),
                                                (ROOT / "data_v2/legal_sources_whitelist.json").read_text(encoding="utf-8")]))
    K = 12
    grams = {unauth[i:i + K] for i in range(len(unauth) - K)}
    for f in tmp.rglob("*"):
        rel = f.relative_to(tmp).as_posix()
        if any(part.startswith(".") for part in Path(rel).parts):
            problems.append(f"hidden:{rel}")
        if not f.is_file() or f.suffix in (".png", ".gz") or rel == "scripts/make_release.py":
            continue
        s = f.read_text(encoding="utf-8", errors="ignore")
        if SECRET.search(s):
            problems.append(f"secret:{rel}")
        if home in s or "/Users/" in s:
            problems.append(f"home_path:{rel}")
        for rt in reg_texts:
            if rt in s:
                problems.append(f"regression_text:{rel}:{rt[:12]}")
        t = re.sub(r"\s+", "", s)
        i = 0
        while i < len(t) - K:
            if t[i:i + K] in grams:
                j = i + K
                while j < len(t) and t[i:j + 1] in unauth:
                    j += 1
                for run in re.findall(r"[　-〿一-鿿＀-￯“”‘’]+", t[i:j]):
                    run = run.strip("：:，,。；;、“”‘’（）() ")
                    if len(re.findall(r"[一-鿿]", run)) >= 10 and not any(run in sd for sd in seeds) and run not in authorised:
                        problems.append(f"unauthorised_overlap:{rel}:{run[:30]}")
                i = j
            else:
                i += 1
    if problems:
        raise SystemExit("ABORT:\n" + "\n".join(sorted(set(problems))[:40]))
    out = ROOT / "docs_v4" / "release"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.tar.gz"):
        old.unlink()
    name = "recruitment-fairness-lens_src.tar.gz"
    with tarfile.open(out / name, "w:gz") as tf:
        tf.add(tmp, arcname="recruitment-fairness-lens")
    h = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / "SHA256SUMS.txt").write_text(f"{h}  {name}\n", encoding="utf-8")
    print(name, h, stats, "tmp:", tmp)


if __name__ == "__main__":
    main()
