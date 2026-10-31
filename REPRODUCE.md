# 招聘公平镜 · 安装与复现

中文招聘文本中性别、婚育、照护条件线索的**人工复核辅助工具**。Spark-X2.6-4B 负责定位原文线索；程序负责校验，并按法学研究规则分流；最后由人来确认。工具**不认定违法，不自动举报，不做企业排名**。

## 1. 环境
- Python 3.12 或更高。云端模式和 MVP 只用标准库。
- 本地模型模式另外需要：`transformers==4.57.1`（模型官方 README 要求的版本）和 `torch`。参考配置：Apple M3 16 GB、MPS、bf16，见 `requirements.txt`。

```bash
python3 -m unittest discover -s tests          # 34 个测试，只需要标准库（Python 3.12+）
```

## 2. 云端模式（讯飞星辰 MaaS 官方 API，Demo 使用的方式）
```bash
mkdir -p ~/.config/rfl && pbpaste > ~/.config/rfl/xfyun_api_key && chmod 600 ~/.config/rfl/xfyun_api_key   # 先把 Key 复制到剪贴板；也可以改用环境变量 XFYUN_API_KEY
python3 mvp/server.py --provider xfyun_maas    # 浏览器打开 http://127.0.0.1:8765
```
- 模型 `spark-x2.6-4b`，参数 `thinking.type=disabled`、`max_completion_tokens=640`。
- 采样由服务端固定为 T=1、top_p=0.95，不能确定性生成，同一输入多次运行结果可能不同。
- 云端模型的具体 revision 未披露。
- 服务只监听 127.0.0.1，拒绝跨站请求；默认每个进程最多调用 60 次 API（环境变量 `XFYUN_MAX_CALLS`）。

## 3. 本地模式（Hugging Face 开源权重）
```bash
hf download XHToken/Spark-X2.6-4B --revision d1b5f26071101c27fcd07728e7a7770e428281f4 --local-dir ../models/Spark-X2.6-4B --exclude "images/*"
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python mvp/server.py --provider local_transformers
```
- 贪心解码，`enable_thinking=False`，`max_new_tokens=640`。
- 16 GB 内存的机器上，如果同时开着其他大程序，可能因为交换内存而严重变慢。

## 4. 只读回放（不调用模型）
```bash
python3 mvp/server.py --replay outputs_v3/maas_v2.1_plus_pp2.3_dev86/records.jsonl --replay-raw outputs_v3/maas/dev86_v2.1_raw/raw.jsonl
```
页面会明确标注“回放”，这时不是实时推理。

## 5. 冻结版本
- Prompt v2.1（`rfl/prompt_v2_1.py`）+ 后处理 v2.3（`rfl/postprocess_v2_3.py`）+ 契约 v2（`rfl/contract_v2.py`）+ Provider（`rfl/providers.py`）。
- 哈希：`docs_v3/FREEZE_v2.1_pp2.3.json`。只涉及界面或安全、不影响推理的后续改动，登记在 `docs_v4/FREEZE_ADDENDA.json`。

## 6. 开发集评估（探索性，不是正式成绩；**公开仓库无法完整运行**）
> 评估需要 `data_v2/dev_labels.jsonl`（法学联合研究者授权下的 AI 辅助研究标签），这个文件尚未授权公开，所以公开仓库里没有。下面的第一条命令（推理）可以运行，第二条（评估）需要先获得标签文件。

```bash
python3 scripts/run_provider.py --provider xfyun_maas --prompt-module rfl.prompt_v2_1 --postprocess v2.3 --input data_v2/dev_inputs.jsonl --out-dir outputs_v3/<new_run>
python3 scripts/evaluate_v2.py --cases data_v2/dev_inputs.jsonl --labels data_v2/dev_labels.jsonl --predictions outputs_v3/<new_run>/records.jsonl --raw outputs_v3/<new_run>/raw.jsonl --label-source mixed_dev --output outputs_v3/eval_<new_run>.json
```
开发集共 86 条合成文本。标签是 AI 辅助的研究意见和工程探针，**不是人工金标准**。评估器只要发现标签不是 `human_frozen`，就会把报告标为 DEVELOPMENT_ONLY。

## 7. 锁定测试（一次性）
```bash
python3 scripts/run_locked_test.py --inputs <只含 case_id/text 的文件> --registered-sha <出题人登记的 SHA-256>
python3 scripts/verify_seal.py          # 先确认预测已封存且没有改动，再打开标签
python3 scripts/evaluate_v2.py ... --label-source human_frozen
```
协议见 `docs_v2/LOCKED_TEST_PROTOCOL.md`。
> 公开仓库中的 `rfl/prompt_v2_1.py` 是公开版，替换了一个来自未授权样例的 15 字示例。因此冻结哈希校验不会通过，锁定测试脚本会拒绝运行；正式锁定测试在内部冻结环境中执行。

## 8. 文件地图
- `rfl/`：契约、Prompt、Provider、后处理
- `scripts/`：运行、评估、冻结、锁定测试、打包
- `mvp/`：单页网页与服务端
- `outputs*/`：各轮真实原始输出（只读）
- `docs*/`：各阶段报告、失败日志、Demo、投稿草稿
