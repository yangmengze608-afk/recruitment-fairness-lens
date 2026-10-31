"""Run the real Spark-X2.6-4B on a JSONL file of {id, text} records.

Writes, per run directory:
  raw.jsonl          every rendered prompt and the verbatim decoded model output (incl. thinking), latency, token counts, errors
  predictions.jsonl  parsed contract object (or null) + contract violations; nothing is repaired or filled in
  run_meta.json      model path/revision/file hashes, framework versions, device, dtype, generation params, timings

Only `id` and `text` are read from input records.
"""
import argparse
import datetime as dt
import json
import platform
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rfl.contract import extract_json, validate  # noqa: E402
from rfl.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_messages  # noqa: E402


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT.parent / "models" / "Spark-X2.6-4B"))
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--thinking", choices=["off", "low", "high"], default="off")
    ap.add_argument("--max-new-tokens", type=int, default=384)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = [{"id": r["id"], "text": r["text"]} for r in read_jsonl(args.input)]
    if args.limit:
        records = records[: args.limit]

    gen_params = {"do_sample": False, "max_new_tokens": args.max_new_tokens}
    tmpl_kwargs = {"enable_thinking": args.thinking != "off"}
    if args.thinking != "off":
        tmpl_kwargs["reasoning_effort"] = args.thinking

    meta = {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model_path": args.model,
        "model_revision": json.loads((ROOT / "env" / "model_revision.json").read_text())
        if (ROOT / "env" / "model_revision.json").exists() else None,
        "input_file": args.input,
        "n_records": len(records),
        "prompt_version": PROMPT_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "chat_template_kwargs": tmpl_kwargs,
        "generation_params": gen_params,
        "generation_note": "greedy decoding for reproducibility; vendor default is sampling (T=1.0, top_p=0.95)",
        "quantization": "none",
        "dtype": args.dtype,
        "device": args.device,
        "python": sys.version,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, trust_remote_code=True, dtype=getattr(torch, args.dtype)
    ).to(args.device)
    model.eval()
    meta["load_seconds"] = round(time.perf_counter() - t0, 2)
    meta["model_class"] = type(model).__name__
    print(f"loaded in {meta['load_seconds']}s on {args.device}", flush=True)

    raw_fh = (out / "raw.jsonl").open("w", encoding="utf-8")
    pred_fh = (out / "predictions.jsonl").open("w", encoding="utf-8")
    latencies = []
    for rec in records:
        messages = build_messages(rec)
        row = {"id": rec["id"], "input_text": rec["text"], "messages": messages}
        try:
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **tmpl_kwargs)
            enc = tok(prompt, return_tensors="pt", add_special_tokens=False).to(args.device)
            if args.device == "mps":
                torch.mps.synchronize()
            t = time.perf_counter()
            with torch.no_grad():
                gen = model.generate(**enc, **gen_params, pad_token_id=tok.pad_token_id)
            if args.device == "mps":
                torch.mps.synchronize()
            lat = time.perf_counter() - t
            new = gen[0][enc["input_ids"].shape[-1]:]
            row.update(
                prompt_rendered=prompt,
                raw_output=tok.decode(new, skip_special_tokens=False),
                raw_output_clean=tok.decode(new, skip_special_tokens=True),
                input_tokens=int(enc["input_ids"].shape[-1]),
                output_tokens=int(new.shape[-1]),
                hit_max_new_tokens=int(new.shape[-1]) >= args.max_new_tokens,
                latency_s=round(lat, 3),
                error=None,
            )
            latencies.append(lat)
            obj, perr = extract_json(row["raw_output_clean"])
        except Exception as e:  # keep the original error, never fabricate output
            row.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
            obj, perr = None, "generation_error"
        violations = validate(obj, rec["id"], rec["text"])
        if perr and perr != "trailing_text":
            violations = [f"parse:{perr}"] + [x for x in violations if x != "unparseable"]
        elif perr == "trailing_text":
            violations.append("parse:trailing_text")
        raw_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        raw_fh.flush()
        pred_fh.write(json.dumps({"id": rec["id"], "prediction": obj, "violations": violations}, ensure_ascii=False) + "\n")
        pred_fh.flush()
        print(f"{rec['id']} {row.get('latency_s')}s tok={row.get('output_tokens')} "
              f"status={(obj or {}).get('status')} viol={violations}", flush=True)
    raw_fh.close()
    pred_fh.close()

    meta["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    if latencies:
        s = sorted(latencies)
        meta["latency_s"] = {"n": len(s), "mean": round(sum(s) / len(s), 3), "median": round(s[len(s) // 2], 3),
                             "min": round(s[0], 3), "max": round(s[-1], 3), "total": round(sum(s), 3)}
    if args.device == "mps":
        meta["mps_driver_allocated_gb"] = round(torch.mps.driver_allocated_memory() / 1e9, 2)
    (out / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta.get("latency_s"), ensure_ascii=False))


if __name__ == "__main__":
    main()
