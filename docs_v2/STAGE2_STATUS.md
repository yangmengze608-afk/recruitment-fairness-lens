# Stage 2 状态报告（2026-10-29）

AI 辅助披露：代码、运行和文档由 Claude Code 完成。Claude 是 AI 工具，不是团队成员。

## 已真实运行
- **Spark-X2.6-4B**：revision d1b5f260，MPS，bf16，无量化，thinking 关闭，贪心解码，`max_new_tokens=640`。
- 运行记录：
  - `outputs_v2/spark/_probe3_v2.0`：3 条格式试跑。
  - `outputs_v2/spark/dev86_v2.0_nothink`：prompt v2.0，86 条。
  - `outputs_v2/spark/dev86_v2.1_nothink_merged`：prompt v2.1，86 条，由两部分拼接，原因见 MERGE_NOTE。
- 基线 A（原始规则，未改，sha256 81fa1d25…）和基线 B（rules-v2.0）各跑了 86 条。
- MVP 回放模式做过接口和页面自测。实时模式代码已写好，但这一轮**没有**在 MVP 里加载模型实测。

## 已完成，但只在开发集上验证
- 四分类契约与校验：`rfl/contract_v2.py`。
- Prompt v2.0 和 v2.1，版本记录见 `docs_v2/PROMPT_V2_CHANGELOG.md`。
- 评估器 `scripts/evaluate_v2.py`。
- 单元测试 22 个，全部通过。
- 三方比较：`outputs_v2/eval/COMPARISON_dev86.md`。
- 失败日志：`docs_v2/FAILURES_V2.md`。
- Go/No-Go：`docs_v2/GO_NO_GO_V2.md`。
- 交接包整合与冲突报告：`docs_v2/LEGAL_PACK_INTEGRATION.md`。
- 单页 MVP：`mvp/`。

## 待人工法律确认
- 12 处标签变更，以及 smoke 期望的改写（S08、S10、S11、S12）。
- reason→triage 映射，reason→法源 ID 对应表。
- 50 条研究标签仍是 AI 辅助初审。

## 尚未进行
- 锁定测试：协议见 `docs_v2/LOCKED_TEST_PROTOCOL.md`，冻结工具是 `scripts/freeze_v2.py`。
- 批量推理延迟。
- 人工纠错时间（需要真人实测）。
- 用户研究。

## 当前阻塞
- 锁定测试集需要法学联合研究者独立出题和标注。
- 冻结哪个 Prompt 版本、是否加 v2.2 后处理，需要负责人决定。
- 本机 16 GB 内存。其他应用占用多时，Spark 会进入换页等待：这一轮出现过一次卡住超过 14 分钟和一次首条 1719 秒。

## 复现
```bash
python3 scripts/build_dev_data_v2.py
.venv/bin/python scripts/run_spark_v2.py --prompt-module rfl.prompt_v2_1 --input data_v2/dev_inputs.jsonl --out-dir outputs_v2/spark/<run>
python3 baseline/rules_v2.py --input data_v2/dev_inputs.jsonl --out-dir outputs_v2/baselineB_rules_v2.0_dev86
python3 scripts/evaluate_v2.py --cases data_v2/dev_inputs.jsonl --labels data_v2/dev_labels.jsonl --predictions outputs_v2/spark/<run>/records.jsonl --raw outputs_v2/spark/<run>/raw.jsonl --label-source mixed_dev --output outputs_v2/eval/<name>.json
python3 mvp/server.py --replay outputs_v2/spark/dev86_v2.1_nothink_merged/records.jsonl     # 回放模式
.venv/bin/python mvp/server.py --load-model                                                 # 实时模式（需约 9 GB 空闲内存）
python3 -m unittest discover -s tests
```
