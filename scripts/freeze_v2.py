"""Record SHA-256 of everything that must not change before the locked-test run (see docs_v2/LOCKED_TEST_PROTOCOL.md).

Usage: python3 scripts/freeze_v2.py --prompt-module rfl.prompt_v2 --output FREEZE_v2.json [--locked-inputs-sha <hex>]
Never reads any label file.
"""
import argparse
import datetime as dt
import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FILES = ["rfl/contract.py", "rfl/contract_v2.py", "scripts/run_spark_v2.py", "scripts/evaluate_v2.py",
         "baseline/baseline.py", "baseline/rules_v2.py", "data_v2/legal_sources_whitelist.json", "env/model_revision.json",
         "rfl/providers.py", "rfl/postprocess_v2_2.py", "rfl/postprocess_v2_3.py", "scripts/run_provider.py", "mvp/server.py", "mvp/index.html"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-module", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--locked-inputs-sha")
    a = ap.parse_args()
    pm = importlib.import_module(a.prompt_module)
    pfile = ROOT / (a.prompt_module.replace(".", "/") + ".py")
    rec = {"frozen_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
           "prompt_module": a.prompt_module, "prompt_version": pm.PROMPT_VERSION,
           "prompt_file_sha256": sha(pfile),
           "system_prompt_sha256": hashlib.sha256(pm.SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
           "files_sha256": {f: sha(ROOT / f) for f in FILES},
           "generation": {"local_transformers": {"do_sample": False, "max_new_tokens": 640, "enable_thinking": False, "dtype": "bfloat16", "device": "mps"},
                          "xfyun_maas": {"model": "spark-x2.6-4b", "thinking": {"type": "disabled"}, "max_completion_tokens": 640,
                                         "sampling": "server-fixed T=1, top_p=0.95", "revision": "云端具体 revision 未披露"}},
           "postprocess": "v2.3-2026-10-30",
           "locked_inputs_sha256_registered": a.locked_inputs_sha}
    Path(a.output).write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rec, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
