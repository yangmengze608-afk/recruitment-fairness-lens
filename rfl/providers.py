"""Inference providers. Both return the same shape so contract_v2 validation and derivation are unchanged.

  local_transformers  Mac MPS, HF weights @ env/model_revision.json, greedy, enable_thinking=False (Stage 1/2 config)
  xfyun_maas          iFlytek MaaS Chat Completions, model "spark-x2.6-4b" only, thinking.type=disabled.
                      Sampling is fixed server-side (temperature=1, top_p=0.95 per docs) -> NOT deterministic, NOT
                      equivalent to local greedy decoding. Cloud model revision is not disclosed by the API.

Secrets: the API key is read from the environment variable XFYUN_API_KEY and is never logged or returned.
Cost guard: XFYUN_MAX_CALLS (default 60) caps HTTP attempts per process; retries count toward the cap.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MAAS_DEFAULT_URL = "https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions"
MAAS_MODEL = "spark-x2.6-4b"
RETRYABLE_HTTP = {500, 502, 503, 504}
RETRYABLE_429_CODES = {11202, 11203, 11210}  # QPS / concurrency / TPM; 11201 (daily cap) is not retried


TRIAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "scope", "findings", "context_quotes", "missing_facts", "rationale"],
    "properties": {
        "id": {"type": "string"},
        "scope": {"type": "string", "enum": ["recruitment", "context_only", "training", "insufficient"]},
        "findings": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["quote", "reason", "sex_link", "care_condition"],
                     "properties": {"quote": {"type": "string"},
                                    "reason": {"type": "string", "enum": ["explicit_sex", "marriage_birth", "care_condition", "context", "exception_missing"]},
                                    "sex_link": {"type": "string", "enum": ["explicit", "suggested", "unestablished", "none", "unknown"]},
                                    "care_condition": {"type": "boolean"}}}},
        "context_quotes": {"type": "array", "items": {"type": "string"}},
        "missing_facts": {"type": "string"},
        "rationale": {"type": "string"}}}


class ProviderError(Exception):
    pass


def _read_key_file():
    p = Path(os.environ.get("XFYUN_API_KEY_FILE") or Path.home() / ".config" / "rfl" / "xfyun_api_key")
    if not p.is_file():
        return None
    if p.stat().st_mode & 0o077:
        raise ProviderError(f"{p} must not be readable by group/others (chmod 600)")
    return p.read_text(encoding="utf-8").strip() or None


class LocalTransformersProvider:
    name = "local_transformers"

    def __init__(self, model_path=None, max_new_tokens=640, device="mps"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.device, self.max_new_tokens = torch, device, max_new_tokens
        model_path = model_path or str(ROOT.parent / "models" / "Spark-X2.6-4B")
        self.tok = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True, dtype=torch.bfloat16).to(device).eval()
        rev = json.loads((ROOT / "env" / "model_revision.json").read_text()).get("revision")
        self.meta = {"provider": self.name, "model": "XHToken/Spark-X2.6-4B", "revision": rev, "device": device,
                     "dtype": "bfloat16", "do_sample": False, "enable_thinking": False, "max_new_tokens": max_new_tokens}

    def generate(self, messages):
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False).to(self.device)
        with self.torch.no_grad():
            t = time.perf_counter()
            out = self.model.generate(**enc, do_sample=False, max_new_tokens=self.max_new_tokens, pad_token_id=self.tok.pad_token_id)
            if self.device == "mps":
                self.torch.mps.synchronize()
            lat = time.perf_counter() - t
        new = out[0][enc["input_ids"].shape[-1]:]
        return {"text": self.tok.decode(new, skip_special_tokens=True), "latency_s": round(lat, 3),
                "usage": {"prompt_tokens": int(enc["input_ids"].shape[-1]), "completion_tokens": int(new.shape[-1])},
                "finish_reason": "length" if new.shape[-1] >= self.max_new_tokens else "stop",
                "attempts": [], "response_model": "local", "raw_response": None}


class XfyunMaasProvider:
    name = "xfyun_maas"

    def __init__(self, max_completion_tokens=640, timeout_s=90, max_retries=2, url=None, structured=False):
        self.key = os.environ.get("XFYUN_API_KEY") or _read_key_file()
        if not self.key:
            raise ProviderError("XFYUN_API_KEY is not set (env var, or file ~/.config/rfl/xfyun_api_key with mode 600)")
        self.url = url or os.environ.get("XFYUN_MAAS_URL") or MAAS_DEFAULT_URL
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.max_calls = int(os.environ.get("XFYUN_MAX_CALLS", "60"))
        self.calls = 0
        self.max_completion_tokens = max_completion_tokens
        self.structured = structured or os.environ.get("XFYUN_STRUCTURED") == "1"
        self.meta = {"structured_output": "function-calling tool_choice=submit_triage (JSON Schema)" if self.structured else "none (plain text JSON)","provider": self.name, "url": self.url, "model": MAAS_MODEL, "thinking": {"type": "disabled"},
                     "max_completion_tokens": max_completion_tokens, "stream": False,
                     "sampling": "server-fixed temperature=1, top_p=0.95 (not sent; per MaaS docs); not deterministic",
                     "revision": "云端具体 revision 未披露", "timeout_s": timeout_s, "max_retries": max_retries,
                     "max_calls_per_process": self.max_calls}

    def body(self, messages):
        b = {"model": MAAS_MODEL, "messages": messages, "stream": False, "thinking": {"type": "disabled"},
             "max_completion_tokens": self.max_completion_tokens}
        if self.structured:
            b["tools"] = [{"type": "function", "function": {"name": "submit_triage",
                           "description": "提交招聘文本的线索分流结果（字段含义见系统提示）", "parameters": TRIAGE_SCHEMA}}]
            b["tool_choice"] = {"type": "function", "function": {"name": "submit_triage"}}
        return b

    def _post(self, body):
        if self.calls >= self.max_calls:
            raise ProviderError(f"call cap reached ({self.max_calls}); raise XFYUN_MAX_CALLS deliberately if intended")
        self.calls += 1
        req = urllib.request.Request(self.url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                status, raw, hdr = r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, raw, hdr = e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})
        except Exception as e:  # timeout / network; keep original error text, never the key
            return {"http_status": None, "error": f"{type(e).__name__}: {e}", "latency_s": round(time.perf_counter() - t, 3)}
        keep = {k: v for k, v in hdr.items() if k.lower() in ("x-request-id", "x-trace-id", "date", "content-type")
                or k.lower().startswith("x-ratelimit")}
        return {"http_status": status, "body": raw, "headers": keep, "latency_s": round(time.perf_counter() - t, 3)}

    def generate(self, messages):
        body = self.body(messages)
        attempts = []
        for i in range(self.max_retries + 1):
            a = self._post(body)
            attempts.append(a)
            st = a.get("http_status")
            parsed = None
            try:
                parsed = json.loads(a.get("body") or "null")
            except json.JSONDecodeError:
                pass
            code = (parsed or {}).get("code") if isinstance(parsed, dict) else None
            if st == 200 and isinstance(parsed, dict) and parsed.get("choices"):
                ch = parsed["choices"][0]
                msg = ch.get("message") or {}
                text = msg.get("content") or ""
                if self.structured and msg.get("tool_calls"):
                    text = msg["tool_calls"][0].get("function", {}).get("arguments") or ""
                return {"text": text, "reasoning_content": msg.get("reasoning_content"),
                        "latency_s": a["latency_s"], "end_to_end_s": round(sum(x["latency_s"] for x in attempts), 3),
                        "usage": parsed.get("usage"), "finish_reason": ch.get("finish_reason"),
                        "response_model": parsed.get("model"), "response_id": parsed.get("id"),
                        "attempts": attempts, "raw_response": parsed}
            retry = st is None or st in RETRYABLE_HTTP or (st == 429 and code in RETRYABLE_429_CODES)
            if not retry or i == self.max_retries:
                break
            time.sleep(2 * (i + 1))
        last = attempts[-1]
        raise ProviderError(json.dumps({"http_status": last.get("http_status"), "error": last.get("error"),
                                        "body": (last.get("body") or "")[:800], "n_attempts": len(attempts)}, ensure_ascii=False))


def get_provider(name, **kw):
    if name == "local_transformers":
        return LocalTransformersProvider(**kw)
    if name == "xfyun_maas":
        return XfyunMaasProvider(**kw)
    raise ValueError(name)
