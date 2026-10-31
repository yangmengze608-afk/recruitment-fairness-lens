"""Stage-3 runner: same prompt / contract / derivation as run_spark_v2.py, pluggable provider.

  python3 scripts/run_provider.py --provider xfyun_maas --prompt-module rfl.prompt_v2_1 \
      --input data_v2/dev_inputs.jsonl --ids R009,E045 --out-dir outputs_v3/maas/<run>

raw.jsonl keeps the request body (no Authorization header) and every HTTP attempt verbatim. A response whose
`model` field is not exactly spark-x2.6-4b is marked invalid (model_identity_mismatch). Nothing is repaired here;
`--postprocess v2.2` applies the separately versioned, logged repairs in rfl/postprocess_v2_2.py.
"""
import argparse
import datetime as dt
import importlib
import json
import platform
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rfl.contract import extract_json  # noqa: E402
from rfl.contract_v2 import CONTRACT_VERSION, derive_record, load_whitelist, validate_v2  # noqa: E402
from rfl.providers import MAAS_MODEL, ProviderError, get_provider  # noqa: E402


def read_jsonl(p):
    return [json.loads(s) for s in Path(p).read_text(encoding="utf-8").splitlines() if s.strip()]


def analyse(provider, pm, rec, whitelist, postprocess=None):
    """One record end to end. Returns (raw_row, pred_row, derived)."""
    messages = pm.build_messages(rec)
    row = {"id": rec["id"], "input_text": rec["text"], "messages": messages, "provider": provider.name}
    text_repairs = []
    if provider.name == "xfyun_maas":
        row["request_body"] = provider.body(messages)
    try:
        g = provider.generate(messages)
        row.update(raw_output_clean=g["text"], reasoning_content=g.get("reasoning_content"), latency_s=g["latency_s"],
                   end_to_end_s=g.get("end_to_end_s", g["latency_s"]), usage=g.get("usage"),
                   finish_reason=g.get("finish_reason"), response_model=g.get("response_model"),
                   response_id=g.get("response_id"), attempts=g.get("attempts"), raw_response=g.get("raw_response"), error=None)
        obj, perr = extract_json(g["text"])
        if postprocess and hasattr(postprocess, "repair_text") and perr:
            fixed, text_repairs = postprocess.repair_text(g["text"], perr)
            if text_repairs:
                obj, perr = extract_json(fixed)
    except ProviderError as e:
        row.update(error=f"ProviderError: {e}")
        obj, perr = None, "provider_error"
    except Exception as e:  # keep original error
        row.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
        obj, perr = None, "generation_error"
    v, w = validate_v2(obj, rec["id"], rec["text"])
    if perr and perr != "trailing_text":
        v = [f"parse:{perr}"] + [x for x in v if x != "unparseable"]
    elif perr == "trailing_text":
        w.append("parse:trailing_text")
    if row.get("finish_reason") == "length":
        w.append("finish_reason_length")
    if provider.name == "xfyun_maas" and row.get("response_model") not in (None, MAAS_MODEL) and not row.get("error"):
        v.append(f"model_identity_mismatch:{row.get('response_model')}")
    repairs = list(text_repairs)
    if postprocess:
        obj, v, w, more = postprocess.apply(obj, v, w, rec)
        repairs += more
    pred = {"id": rec["id"], "prediction": obj, "violations": v, "warnings": w, "repairs": repairs}
    derived = derive_record(obj, v, w, rec["id"], rec["text"], whitelist)
    derived["repairs"] = repairs
    if postprocess:
        derived = postprocess.annotate(derived, rec)
    derived["provider"] = provider.name
    return row, pred, derived


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["xfyun_maas", "local_transformers"], required=True)
    ap.add_argument("--prompt-module", default="rfl.prompt_v2_1")
    ap.add_argument("--postprocess", choices=["none", "v2.2", "v2.3"], default="none")
    ap.add_argument("--input", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    pm = importlib.import_module(a.prompt_module)
    post = importlib.import_module("rfl.postprocess_v" + a.postprocess.replace(".", "_").lstrip("v")) if a.postprocess != "none" else None
    recs = [{"id": r["id"], "text": r["text"]} for r in read_jsonl(a.input)]
    if a.ids:
        want = a.ids.split(",")
        recs = [r for r in recs if r["id"] in want]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=False)  # never overwrite a previous run
    prov = get_provider(a.provider)
    wl = load_whitelist()
    meta = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "provider_meta": prov.meta,
            "prompt_module": a.prompt_module, "prompt_version": pm.PROMPT_VERSION, "contract_version": CONTRACT_VERSION,
            "postprocess": a.postprocess, "input": a.input, "ids": [r["id"] for r in recs],
            "client_platform": platform.platform(), "python": sys.version.split()[0]}
    with (out / "raw.jsonl").open("w", encoding="utf-8") as rf, (out / "predictions.jsonl").open("w", encoding="utf-8") as pf, \
            (out / "records.jsonl").open("w", encoding="utf-8") as df:
        for rec in recs:
            row, pred, derived = analyse(prov, pm, rec, wl, post)
            for fh, obj in ((rf, row), (pf, pred), (df, derived)):
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
                fh.flush()
            print(rec["id"], row.get("end_to_end_s"), derived["triage"], derived.get("all_review_reasons"), pred["violations"],
                  (row.get("error") or "")[:200], flush=True)
    meta["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    meta["http_attempts"] = getattr(prov, "calls", None)
    (out / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
