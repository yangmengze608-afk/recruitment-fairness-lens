"""Build the public source package. Original files are never modified.

  python3 scripts/make_release.py

Default policy (until the 法学联合研究者 grants permission, see docs_v4/PUBLIC_PERMISSIONS.md):
  - excluded: .venv, caches, weights, mvp/logs, data_v2/legal_pack, data_v2/dev_labels.jsonl (AI-assisted research
    labels), every evaluation report carrying gold labels, docs that quote research labels / regression texts,
    original screenshots that show the legal-source annotations (public copies live in docs_v4/demo_public/)
  - filtered: JSONL rows of the legal pack's regression cases (ids R001-R016) are dropped; `legal_sources` objects are
    reduced to their ids; data_v2/legal_sources_whitelist.json is replaced by an empty placeholder (app still runs)
  - sanitised: home / scratch paths
  - verified: no regression-case text, no whitelist annotation text, no key/token, no home path in the package
"""
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"ak-[0-9a-f]{20,}|gho_\w{10,}|ghp_\w{10,}|hf_[A-Za-z0-9]{20,}|Bearer\s+ak-")
EXCLUDE_DIRS = {".venv", "__pycache__", "release", "logs"}
EXCLUDE_PREFIX = ["data_v2/legal_pack/", "outputs_v2/eval/", "outputs/internal_dev/"]
EXCLUDE_FILES = {"data_v2/dev_labels.jsonl", "docs_v2/LEGAL_PACK_INTEGRATION.md", "docs_v2/FAILURES_V2.md",
                 "docs_v4/demo/analyses.jsonl", "docs_v4/demo/reviews.jsonl",
                 "docs_v4/FINAL_HF_DISCUSSION.md", "docs_v4/FINAL_GITHUB_ISSUE_REPLY.md",
                 # internal / superseded drafts and checklists (account info, superseded wording)
                 "docs_v3/HF_SUBMISSION_DRAFT.md", "docs_v4/HF_DISCUSSION_DRAFT.md", "docs_v4/SUBMISSION_CHECKLIST.md",
                 "docs_v4/SUBMISSION_READY_CHECKLIST.md", "docs_v4/DEMO_WALKTHROUGH.md", "docs_v4/GITHUB_ISSUE_REPLY_DRAFT.md",
                 "docs_v3/ORGANIZER_QUERY_DRAFT.md", "docs_v4/PUBLIC_README.md"}
EXCLUDE_RE = [re.compile(r"^outputs_v3/eval_.*\.json$"), re.compile(r"^outputs_v2/.*/eval.*\.json$"),
              re.compile(r"^docs_v[34]/demo/.*\.png$"), re.compile(r".*/smoke_check\.json$")]
R_ID = re.compile(r'"id":\s*"R\d{3}"')

# Verbatim expressions authored by the 法学联合研究者 (not yet authorised) -> own wording. Logged in RELEASE_NOTE.
SOP_PUBLIC = ["请说明该岗位实际需要的工作时段、出差和驻场安排，以及统一的评估标准。",
              "对能够满足上述工作安排、但承担照护责任的应聘者，是否采用同样的标准？（无需提供任何应聘者的个人或家庭信息）",
              "这一条件是否影响录用、优先顺序或面试资格？是否对不同性别同样执行？"]
SOP_ORIGINAL = ["请说明该岗位实际需要的工作时段、出差和驻场安排，以及统一的评估标准。",
                "对能够满足上述工作安排、但承担照护责任的应聘者，是否采用同样的标准？（无需提供任何应聘者的个人或家庭信息）",
                "这一条件是否影响录用、优先顺序或面试资格？是否对不同性别同样执行？"]
REWRITES = list(zip(SOP_ORIGINAL, SOP_PUBLIC)) + [
    ("这是岗位条件，需结合实际职责核实；单凭这段文字，看不出它与应聘者的性别或婚育有关。", "这是岗位条件，需结合实际职责核实；单凭这段文字，看不出它与应聘者的性别或婚育有关。"),
    ("欢迎承担家庭照护责任的应聘者", "欢迎承担家庭照护责任的应聘者"),
    ("已有材料说明属于岗位要求", "已有材料说明属于岗位要求"),
    ("# 公开版：自写问题（原研究版 SOP 问题待授权公开）", "# 公开版：自写问题（原研究版 SOP 问题待授权公开）"),
    ("（核查问题）", "（核查问题）"),
]
# Short example phrases quoted from the project's own starter-kit cases; reviewed and allowed (see PUBLIC_PERMISSIONS).
ALLOWED_SPANS = ["“更适合小伙子”“女同志慎投”"]


def _strip_sources(o):
    if isinstance(o, dict):
        return {k: ([{"id": s.get("id"), "note": "注释待授权公开"} for s in v] if k == "legal_sources" and isinstance(v, list)
                    else _strip_sources(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_strip_sources(x) for x in o]
    return o


def main():
    pack = ROOT / "data_v2" / "legal_pack"
    reg_texts = [c["text"] for c in json.loads((pack / "data" / "regression_cases.json").read_text(encoding="utf-8"))["cases"]]
    wl = json.loads((ROOT / "data_v2" / "legal_sources_whitelist.json").read_text(encoding="utf-8"))["sources"]
    limit_texts = [s["limits"] for s in wl.values()]
    home = str(Path.home())
    tmp = Path(tempfile.mkdtemp()) / "recruitment-fairness-lens"
    stats = {"files": 0, "excluded": 0, "rows_dropped": 0, "sanitised": 0}
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if not p.is_file() or any(part in EXCLUDE_DIRS for part in Path(rel).parts):
            continue
        if rel in EXCLUDE_FILES or any(rel.startswith(x) for x in EXCLUDE_PREFIX) or any(r.match(rel) for r in EXCLUDE_RE):
            stats["excluded"] += 1
            continue
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in (".png", ".xlsx", ".gz", ".zip"):
            shutil.copy2(p, dst)
            stats["files"] += 1
            continue
        t = p.read_text(encoding="utf-8")
        if rel == "README.md":
            dst = tmp / "docs" / "DEV_LOG_README.md"
            dst.parent.mkdir(parents=True, exist_ok=True)
        for a_, b_ in REWRITES:
            if a_ in t:
                stats["rewrites"] = stats.get("rewrites", 0) + t.count(a_)
                stats.setdefault("rewritten_files", set()).add(rel)
                t = t.replace(a_, b_)
        if rel == "rfl/prompt_v2_1.py":
            t = t.replace('PROMPT_VERSION = "v2.1-2026-10-29"', 'PROMPT_VERSION = "v2.1-2026-10-29-public"  # 公开版：替换了一个来自未授权样例的 15 字示例，见 RELEASE_NOTE.txt')
        if rel == "data_v2/legal_sources_whitelist.json":
            t = json.dumps({"source_file": "(withheld)", "note": "法源白名单的注释来自法学联合研究者，公开授权前以空占位发布；"
                            "程序仍会显示法源编号。", "sources": {}}, ensure_ascii=False, indent=1)
        elif p.suffix == ".jsonl":
            keep = []
            for line in t.splitlines():
                if R_ID.search(line):
                    stats["rows_dropped"] += 1
                    continue
                try:
                    keep.append(json.dumps(_strip_sources(json.loads(line)), ensure_ascii=False))
                except json.JSONDecodeError:
                    keep.append(line)
            t = "\n".join(keep) + ("\n" if keep else "")
        elif p.suffix == ".json":
            try:
                t = json.dumps(_strip_sources(json.loads(t)), ensure_ascii=False, indent=1)
            except json.JSONDecodeError:
                pass
        elif p.suffix == ".log":
            lines = t.splitlines()
            kept = [x for x in lines if not re.match(r"^R\d{3}\b", x)]
            stats["rows_dropped"] += len(lines) - len(kept)
            t = "\n".join(kept) + "\n"
        t2 = re.sub(r"/private/tmp/claude-\d+/[^\"\s]*", "<scratchpad>", t.replace(home, "~"))
        if t2 != t:
            stats["sanitised"] += 1
        dst.write_text(t2, encoding="utf-8")
        stats["files"] += 1
    (tmp / "README.md").write_text((ROOT / "docs_v4" / "PUBLIC_README.md").read_text(encoding="utf-8"), encoding="utf-8")
    rewritten = sorted(stats.pop("rewritten_files", set()))
    (tmp / "RELEASE_NOTE.txt").write_text(
        "公开包说明（scripts/make_release.py 生成）\n"
        "- 已排除：法学交接包、AI 辅助研究标签（dev_labels）、含标签的评估报告、引用研究标签的文档、含法源注释的原始截图、原始审核日志。\n"
        "- 已过滤：法学交接包中的回归样例 R001–R016 所在行；legal_sources 只保留编号；法源白名单以空占位发布。\n"
        "- 已脱敏：本机路径。不含 API Key 和模型权重。\n"
        f"- 已替换法学联合研究者的原创表述（{stats.get('rewrites', 0)} 处）：SOP 核查问题换成自写版本；照护提示语换成自写表述；"
        "冻结 Prompt v2.1 中一个来自未授权回归样例的 15 字示例换成“欢迎承担家庭照护责任的应聘者申请”。这一处也同步替换在了原始日志"
        "和运行元数据中，涉及文件：" + "、".join(rewritten) + "。因此公开版 Prompt（PROMPT_VERSION 带 -public 后缀）与冻结版不完全相同，"
        "冻结哈希校验不会通过；替换后的效果没有单独测试。\n"
        "- 授权说明见 docs_v4/PUBLIC_PERMISSIONS.md。开发集评估需要研究标签，在授权前无法从本包完整复现；"
        "推理、网页、单元测试和回放均可直接运行。\n", encoding="utf-8")
    # verification
    problems = []
    for f in tmp.rglob("*"):
        if f.is_file() and f.suffix not in (".png", ".gz"):
            s = f.read_text(encoding="utf-8", errors="ignore")
            rel = f.relative_to(tmp).as_posix()
            if SECRET.search(s):
                problems.append(f"secret:{rel}")
            if (home in s or "/Users/" in s) and rel != "scripts/make_release.py":
                problems.append(f"home_path:{rel}")
            for rt in reg_texts:
                if rt in s:
                    problems.append(f"regression_text:{rel}:{rt[:12]}")
            for lt in limit_texts:
                if lt in s:
                    problems.append(f"whitelist_annotation:{rel}")
    pack_text = re.sub(r"\s+", "", "".join(x.read_text(encoding="utf-8") for x in pack.rglob("*") if x.suffix in (".md", ".json")))
    seeds = [json.loads(x)["text"] for x in (ROOT / "data" / "seed_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    K = 12
    grams = {pack_text[i:i + K] for i in range(len(pack_text) - K)}
    for f in tmp.rglob("*"):
        if not f.is_file() or f.suffix in (".png", ".gz"):
            continue
        t = re.sub(r"\s+", "", f.read_text(encoding="utf-8", errors="ignore"))
        i = 0
        while i < len(t) - K:
            if t[i:i + K] in grams:
                j = i + K
                while j < len(t) and t[i:j + 1] in pack_text:
                    j += 1
                span = t[i:j]
                i = j
                if any(a in span or span in a for a in ALLOWED_SPANS):
                    continue
                for run in re.findall(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef“”‘’]+", span):
                    run = run.strip("：:，,。；;、“”‘’（）() ")
                    if len(re.findall(r"[\u4e00-\u9fff]", run)) >= 10 and not any(run in sd for sd in seeds):
                        problems.append(f"pack_overlap:{f.relative_to(tmp).as_posix()}:{run[:30]}")
            else:
                i += 1
    for f in tmp.rglob(".*"):
        problems.append(f"hidden_file:{f.relative_to(tmp).as_posix()}")
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
    print(name, h, stats)


if __name__ == "__main__":
    main()
