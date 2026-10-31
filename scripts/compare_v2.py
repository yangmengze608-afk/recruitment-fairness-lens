"""Render a markdown comparison of evaluate_v2 reports (development set only)."""
import json
import sys
from pathlib import Path


def f(x):
    return "—" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


def main(paths):
    reps = [(Path(p).stem, json.loads(Path(p).read_text(encoding="utf-8"))) for p in paths]
    out = ["| 指标 | " + " | ".join(n for n, _ in reps) + " |", "|---|" + "---|" * len(reps)]
    rows = [("n", lambda r: r["n_determinate"]), ("四分类一致率", lambda r: r["accuracy"]),
            ("四分类 macro-F1", lambda r: r["macro_f1_4class"]), ("契约通过率", lambda r: r["contract_pass_rate"]),
            ("引用子串有效率", lambda r: r["quote_substring_rate"]),
            ("核心性别/婚育线索 P", lambda r: r["core_sex_marriage_cue"]["precision"]),
            ("核心性别/婚育线索 R", lambda r: r["core_sex_marriage_cue"]["recall"]),
            ("人工队列 P", lambda r: r["human_review_queue"]["precision"]),
            ("人工队列 R", lambda r: r["human_review_queue"]["recall"])]
    for t in ("flag", "review", "clear", "unknown"):
        rows.append((f"{t} F1", lambda r, t=t: r["per_class"][t]["f1"]))
    for name, fn in rows:
        out.append(f"| {name} | " + " | ".join(f(fn(r)) for _, r in reps) + " |")
    names = [s["name"] for s in reps[0][1]["error_slices"]]
    for s in names:
        cells = []
        for _, r in reps:
            x = next(y for y in r["error_slices"] if y["name"] == s)
            cells.append(f"{x['errors']}/{x['n']}")
        out.append(f"| 错误：{s} | " + " | ".join(cells) + " |")
    lat = [r.get("latency_s") for _, r in reps]
    out.append("| 单条延迟中位数(s) | " + " | ".join(f(l["median"]) if l else "—" for l in lat) + " |")
    print("\n".join(out))
    for n, r in reps:
        print(f"\n### {n}：四分类混淆矩阵（行=标签，列=预测）\n")
        cols = ["flag", "review", "clear", "unknown", "invalid"]
        print("| gold\\pred | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
        for g, row in r["confusion_rows_gold_cols_pred"].items():
            print(f"| {g} | " + " | ".join(str(row[c]) for c in cols) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
