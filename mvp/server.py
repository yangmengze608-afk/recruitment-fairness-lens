"""Single-page MVP server (stdlib only, binds 127.0.0.1).

  XFYUN_API_KEY=... python3 mvp/server.py --provider xfyun_maas   # official iFlytek MaaS spark-x2.6-4b
  .venv/bin/python mvp/server.py --provider local_transformers       # local HF weights on MPS (fallback)
  python3 mvp/server.py --replay outputs_v2/spark/dev86_v2.0_nothink/records.jsonl
                                                # no model: browse REAL saved dev-set runs, clearly labelled replay

Every analysis (raw model output + derived record) and every human edit is appended to mvp/logs/*.jsonl.
No scraping, no reporting, no accounts, no cloud storage. Output is a triage aid, not a legal opinion.
"""
import argparse
import datetime as dt
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfl.contract_v2 import load_whitelist  # noqa: E402
from mvp import review_flow  # noqa: E402

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
SOP_CARE_QUESTIONS = [  # 逐字摘自 HUMAN_REVIEW_SOP.md「家庭／育儿条件的定向核查卡」
    "该岗位具体需要哪些出勤时段、出差频率或持续驻场安排？请提供实际职责和统一评估标准，而不是泛称工作忙。",
    "一名有照护责任但能满足上述安排的应聘者，是否与其他人按相同标准考虑？请说明筛选规则；不提供求职者姓名、孩子情况或家庭成员资料。",
    "“没有家庭／育儿负担”是否直接决定不予录用、优先级或面试资格？是否只对某一性别执行？如有已有审核材料，请仅提供必要的脱敏摘录。",
]
HUMAN_OUTCOMES = list(review_flow.STATUSES)  # review-flow v1.0; legacy legal_review_required only in old records


class Engine:
    """Server-side inference: provider (xfyun_maas | local_transformers) + prompt v2.1 + postprocess v2.3."""

    def __init__(self, provider_name):
        from rfl import postprocess_v2_3, prompt_v2_1
        from rfl.providers import get_provider
        self.pm, self.post = prompt_v2_1, postprocess_v2_3
        self.provider = get_provider(provider_name)
        self.lock = threading.Lock()
        self.meta = {**self.provider.meta, "prompt_version": prompt_v2_1.PROMPT_VERSION,
                     "postprocess_version": postprocess_v2_3.POSTPROCESS_VERSION}

    def run(self, rid, text):
        from scripts.run_provider import analyse
        with self.lock:  # one request at a time: cost and memory guard
            return analyse(self.provider, self.pm, {"id": rid, "text": text}, App.whitelist, self.post)


def append(name, row):
    LOGS.mkdir(exist_ok=True)
    with (LOGS / name).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class App:
    engine = None
    replay = {}
    whitelist = load_whitelist()
    analyses = {}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/":
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/status":
            return self._send(200, {"mode": "live" if App.engine else "replay", "engine": App.engine.meta if App.engine else None,
                                    "replay_ids": sorted(App.replay), "outcomes": HUMAN_OUTCOMES,
                                    "outcome_rules": {k: {"label": v[0], "required": v[1]} for k, v in review_flow.STATUSES.items()},
                                    "review_flow_version": review_flow.REVIEW_FLOW_VERSION})
        if self.path.startswith("/api/export/"):
            aid = self.path.rsplit("/", 1)[-1]
            a = App.analyses.get(aid)
            if not a:
                return self._send(404, {"error": "unknown analysis id"})
            if "review_cards" not in a:  # records created before review-flow v1.0
                a["review_cards"] = review_flow.build_cards(a["record"])
            return self._send(200, a, extra={"Content-Disposition": f'attachment; filename="audit_{aid}.json"'})
        return self._send(404, {"error": "not found"})

    def _same_origin(self):
        """Block cross-site requests: a page on another site must not trigger paid API calls or write audit records."""
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        allowed = {f"http://{host}"}
        return host.startswith(("127.0.0.1:", "localhost:")) and (origin is None or origin in allowed)

    def do_POST(self):
        if not self._same_origin():
            return self._send(403, {"error": "cross-origin request refused"})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(415, {"error": "Content-Type must be application/json"})
        try:
            body = self._json()
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": f"bad JSON: {e}"})
        if self.path == "/api/analyze":
            try:
                return self.analyze(body)
            except Exception as e:  # never drop the connection silently; nothing is classified
                return self._send(500, {"error": f"服务端错误，未生成任何判断：{type(e).__name__}: {e}"})
        if self.path == "/api/review":
            a = App.analyses.get(body.get("analysis_id"))
            if not a:
                return self._send(404, {"error": "unknown analysis id"})
            errs = review_flow.validate_review(body, len(a["record"].get("findings") or []))
            if errs:
                return self._send(400, {"error": "；".join(errs), "errors": errs})
            rev = {"reviewed_at": now(), "reviewer": body["reviewer"].strip(),
                   "review_flow_version": review_flow.REVIEW_FLOW_VERSION,
                   "finding_decisions": body.get("finding_decisions", []), "human_triage": body.get("human_triage") or None,
                   "human_outcome": body["human_outcome"], "rationale": body.get("rationale", ""),
                   "missing_materials": body.get("missing_materials", ""), "next_step": body.get("next_step", ""),
                   "evidence": body.get("evidence") or [],
                   "revised_text": body.get("revised_text", ""), "revised_by": body.get("revised_by", ""),
                   "recheck_analysis_id": body.get("recheck_analysis_id", ""), "recheck_note": body.get("recheck_note", ""),
                   "original_text_unchanged": True, "legal_conclusion": "not_determined"}
            a["human_reviews"].append(rev)
            append("reviews.jsonl", {"analysis_id": a["analysis_id"], **rev})
            return self._send(200, a)
        return self._send(404, {"error": "not found"})

    def analyze(self, body):
        aid = uuid.uuid4().hex[:12]
        if body.get("replay_id"):
            rec = App.replay.get(body["replay_id"])
            if not rec:
                return self._send(404, {"error": "unknown replay id"})
            a = {"analysis_id": aid, "created_at": now(), "mode": "replay_of_saved_real_run",
                 "provenance": "outputs_v2 dev-set run (real Spark-X2.6-4B output, development set)", "input_text": rec["text"],
                 "raw_model_output": rec.get("_raw"), "record": rec, "latency_s": rec.get("_latency")}
        else:
            if not App.engine:
                return self._send(400, {"error": "model not loaded; start with --load-model or use replay"})
            text = (body.get("text") or "").strip()
            if not text or len(text) > 2000:
                return self._send(400, {"error": "text must be 1-2000 characters"})
            rid = "U" + aid
            row, pred, rec = App.engine.run(rid, text)
            safe_row = {k: v for k, v in row.items() if k != "messages"}
            a = {"analysis_id": aid, "created_at": now(), "mode": "live", "engine": App.engine.meta, "input_text": text,
                 "raw_model_output": row.get("raw_output_clean"), "provider_error": row.get("error"),
                 "usage": row.get("usage"), "response_model": row.get("response_model"), "response_id": row.get("response_id"),
                 "record": rec, "latency_s": row.get("end_to_end_s"), "raw_call": safe_row, "model_repairs": pred.get("repairs")}
        for k in ("retry_of", "recheck_of"):
            if body.get(k):
                a[k] = body[k]
        a["review_cards"] = review_flow.build_cards(a["record"])
        a["sop_care_questions"] = SOP_CARE_QUESTIONS if a["record"].get("care_condition") else []
        a["human_reviews"] = []
        a["disclaimer"] = "文本分流辅助，不是法律意见；clear 不表示合法；一次独立锁定测试与单一研究者参考分类一致 15/30，不是法律准确率。"
        App.analyses[aid] = a
        append("analyses.jsonl", a)
        return self._send(200, a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["none", "xfyun_maas", "local_transformers"], default="none",
                    help="none = replay only; xfyun_maas needs XFYUN_API_KEY in the environment")
    ap.add_argument("--replay", help="records.jsonl from a real run (raw.jsonl next to it is attached)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--replay-raw", help="raw.jsonl of the run behind --replay (default: next to it)")
    a = ap.parse_args()
    # Persisted audit trail: reload earlier analyses and human reviews so exports survive restarts.
    if (LOGS / "analyses.jsonl").exists():
        for s in (LOGS / "analyses.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(s)
            r["human_reviews"] = []
            App.analyses[r["analysis_id"]] = r
    if (LOGS / "reviews.jsonl").exists():
        for s in (LOGS / "reviews.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(s)
            if r["analysis_id"] in App.analyses:
                App.analyses[r["analysis_id"]]["human_reviews"].append({k: v for k, v in r.items() if k != "analysis_id"})
    if (LOGS / "voided_reviews.json").exists():  # void marks only; the original lines stay in reviews.jsonl
        for v in json.loads((LOGS / "voided_reviews.json").read_text(encoding="utf-8"))["voided"]:
            for rev in App.analyses.get(v["analysis_id"], {}).get("human_reviews", []):
                if rev["reviewed_at"] == v["reviewed_at"]:
                    rev["voided"] = v["reason"]
    if a.replay:
        rp = Path(a.replay)
        raw_path = Path(a.replay_raw) if a.replay_raw else rp.parent / "raw.jsonl"
        raws = {}
        if raw_path.exists():
            for s in raw_path.read_text(encoding="utf-8").splitlines():
                r = json.loads(s)
                raws[r["id"]] = r
        for s in rp.read_text(encoding="utf-8").splitlines():
            r = json.loads(s)
            r["_raw"] = raws.get(r["id"], {}).get("raw_output_clean")
            r["_latency"] = raws.get(r["id"], {}).get("latency_s")
            App.replay[r["id"]] = r
    if a.provider != "none":
        App.engine = Engine(a.provider)
    print(f"http://127.0.0.1:{a.port}  mode={'live' if App.engine else 'replay'}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
