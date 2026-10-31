> **先看**：安装与复现见 [REPRODUCE.md](REPRODUCE.md)；提交清单见 [docs_v4/SUBMISSION_READY_CHECKLIST.md](docs_v4/SUBMISSION_READY_CHECKLIST.md)。下文是各阶段的工作记录。

# 招聘公平镜 · Stage 1 工程目录（rfl_stage1）

只做招聘文本中性别/婚育相关**风险线索识别与人工复核辅助**。不认定违法；`clear` 不表示合法。
原始工具包未改动（`../HER7_*.zip`，解压副本在 `../_extracted/`）。

## 目录
```
rfl/contract.py        输出契约校验（枚举、id、证据逐字子串、禁止法律定性用语）与 JSON 抽取（不修补）
rfl/prompt.py          提示词 v1（SPARK_INTERFACE 系统提示 + 契约），只发送 id 与 text
scripts/run_spark.py   真实 Spark-X2.6-4B 推理，保存原始输出 / 解析结果 / 运行元数据
scripts/evaluate.py    独立评估：需单独标签文件，支持 unresolved；非 human_frozen 标签一律标 INTERNAL_DEV_ONLY
scripts/check_smoke.py smoke 探针核对（AI 工程侧期望，非法律标签）
baseline/baseline.py   原始关键词基线（逐字节复制，未修改）
data/                  seed_cases（原样）、seed_inputs_only（仅 id+text）、draft_labels_INTERNAL、smoke/
env/                   model_revision.json（revision + SHA-256）、pip_freeze.txt、copied_file_hashes.txt
outputs/spark/<run>/   raw.jsonl · predictions.jsonl · run_meta.json（· smoke_check.json）
outputs/baseline/      基线预测
outputs/internal_dev/  对 draft 标签的内部对照（不得用于对外主张）
docs/                  PHASE1_AUDIT · FAILURES · GO_NO_GO · ROUND1_STATUS
tests/                 契约、泄漏防护、评估器单测
```

## 复现
```bash
# 1) 模型（公开、Apache-2.0、无需 token），固定 revision
hf download XHToken/Spark-X2.6-4B --revision d1b5f26071101c27fcd07728e7a7770e428281f4 --local-dir ../models/Spark-X2.6-4B --exclude "images/*"
# 2) 环境（官方 README 要求 transformers==4.57.1）
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
# 3) 测试（仅标准库）
python3 -m unittest discover -s tests -v
# 4) Spark smoke（thinking 关闭、贪心解码）
.venv/bin/python scripts/run_spark.py --input data/smoke/smoke_inputs.jsonl --out-dir outputs/spark/smoke_v1_nothink --thinking off
python3 scripts/check_smoke.py --run-dir outputs/spark/smoke_v1_nothink --expectations data/smoke/smoke_expectations.jsonl
# 5) 基线
python3 baseline/baseline.py --input data/seed_inputs_only.jsonl --output outputs/baseline/seed_predictions.jsonl
# 6) 正式评估（标签冻结后）
python3 scripts/evaluate.py --cases <locked_cases> --labels <human_labels> --predictions <pred> --label-source human_frozen --output <report>
```

## 运行配置（Round 1 实测）
| 项 | 值 |
|---|---|
| 模型 | XHToken/Spark-X2.6-4B @ d1b5f26071101c27fcd07728e7a7770e428281f4（`Spark2_5ForCausalLM`，trust_remote_code，代码已审阅：仅导入 torch/transformers） |
| 框架 | transformers 4.57.1 · torch 2.14.1 · Python 3.12 |
| 设备 | Apple M3，16 GB 统一内存，macOS 26.5.2，MPS |
| 精度/量化 | bfloat16，无量化 |
| 生成 | `do_sample=False`（贪心，为可复现；厂商默认 T=1.0/top_p=0.95 采样），`max_new_tokens=384`；thinking 变体 1536 |
| 提示 | v1-2026-10-29，`enable_thinking=False`（模板渲染为 `<|Bot|></think>`） |

AI 辅助披露：本目录代码与文档由 Claude Code（AI 工具）编写与运行；ChatGPT 负责独立验收。AI 不是团队成员。

## Stage 2（2026-10-29）
四分类契约、Prompt v2.x、两个基线、开发集评估和 MVP，全部放在新文件中；Stage 1 的文件已设为只读，快照见 `env/STAGE1_SNAPSHOT.json`。
从 `docs_v2/STAGE2_STATUS.md` 开始看。法学交接包的只读副本在 `data_v2/legal_pack/`，新的运行输出在 `outputs_v2/`。

## Stage 3（2026-10-30）：讯飞星辰 MaaS 官方 API
从 `docs_v3/STAGE3_STATUS.md` 开始看。
- 推理 Provider：`rfl/providers.py`，可选 `xfyun_maas` 或 `local_transformers`。
- 运行脚本：`scripts/run_provider.py`。
- 后处理：`rfl/postprocess_v2_3.py`。
- 云端输出：`outputs_v3/`。
- API 核验记录：`docs_v3/MAAS_API_VERIFICATION.md`。
- 投稿草稿：`docs_v3/HF_SUBMISSION_DRAFT.md`（尚未发布）。

API Key 只从环境变量 `XFYUN_API_KEY` 或文件 `~/.config/rfl/xfyun_api_key`（权限 600）读取。

## Stage 4（2026-10-30）：冻结与提交准备
先看 `docs_v4/SUBMISSION_CHECKLIST.md`。图文 Demo 在 `docs_v4/DEMO_WALKTHROUGH.md`，锁定测试运行器是 `scripts/run_locked_test.py`。投稿草稿**尚未发布**。
