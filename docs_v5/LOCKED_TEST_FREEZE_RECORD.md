# 锁定测试冻结记录（按 TEST_LOCK_PROTOCOL 模板填写）

记录时间：2026-10-31T09:46:15.637186+00:00（UTC）。只记录真实情况，未知的字段写“待填”。

| 字段 | 内容 |
|---|---|
| 技术负责人 | 项目负责人（执行工具：Claude Code，AI 工具，不是团队成员） |
| 冻结时间 | 推理链路：2026-10-29T14:10Z（`docs_v3/FREEZE_v2.1_pp2.3.json`）；评分协议 v1.1 和复核流程 v1.0：2026-10-31（本记录） |
| 代码 commit | 内部工作目录不是 git 仓库，以下面的文件哈希为准。公开仓库 commit `4c33eb54`，其中的 Prompt 与冻结版逐字节一致 |
| Prompt v2.1 文件哈希 | `62a40a7fec3c7dedf1ecc4ed9ad74a7580ca4635227514572ca48150ebde2f66`（复核时间：2026-10-31，一致） |
| 后处理 v2.3 哈希 | `6e13d76c69a7148babf217526cef67ba841468b35a7e54000e08b2cec3b47d42`（依赖的 v2.2：`7215776c168ac6b5b92ca3d1014236c91d65b41b0381a53c8b8dd6b4e10215c5`） |
| 模型标识和服务版本的可见程度 | 讯飞星辰 MaaS，`spark-x2.6-4b`；每次响应都会核对 `model` 字段；**云端 revision、精度、硬件均未披露** |
| 参数 | `thinking.type=disabled`，`max_completion_tokens=640`，`stream=false`；服务端固定 T=1、top_p=0.95（结果有随机性） |
| 调用时间 | 2026-10-31 12:01:48–12:12:37 UTC（一次） |
| 重试和失败策略 | Provider 内置：5xx 和 QPS、TPM 类 429 最多重试 2 次（间隔 2 秒、4 秒）；当日额度用完（11201）不重试；超时 90 秒；调用上限为 3×N+5 次；无效输出计为 invalid，不手动重跑 |
| 输入哈希 | `0f0665ad22c1b36221b36c571b29b2234e985371a91fc0f3b3cbc02c98fef6ba` |
| gold 保管和解封 | 由项目负责人保管；预测封存（`ba921399…7397`）校验通过后，于 2026-10-31 解封给比较方。gold 未公开 |
| 评分协议 | `docs_v5/LOCKED_TEST_SCORING_PROTOCOL.md` v1.1，SHA-256 `2c260b84861d9d7b9e88fa2264cb7b3a0b8b1bb2ea9eaa683910d98a8ee270f4`（v1.0 为 `0a6af395…`，原文保留） |
| 开发集重合核查 | 运行器在执行前，对照完整的 86 条开发集做精确比对和去空白比对 |

## 文件哈希快照
| 文件 | SHA-256 |
|---|---|
| `rfl/prompt_v2_1.py` | `62a40a7fec3c7dedf1ecc4ed9ad74a7580ca4635227514572ca48150ebde2f66` |
| `rfl/postprocess_v2_3.py` | `6e13d76c69a7148babf217526cef67ba841468b35a7e54000e08b2cec3b47d42` |
| `rfl/postprocess_v2_2.py` | `7215776c168ac6b5b92ca3d1014236c91d65b41b0381a53c8b8dd6b4e10215c5` |
| `rfl/contract_v2.py` | `caa6fd2527e7b36b684d5cadf605e69e47c78c65af455f32e2df70188a02c4b2` |
| `rfl/contract.py` | `b14b60c4c72de4f5292010e0d11938d04cedd6edd6862f2c1c95169aff7753e3` |
| `rfl/providers.py` | `cb38196fb70cf751ea61d3dedccd68daf312076a7a854eaeeea989c20e6f737e` |
| `scripts/run_provider.py` | `2d14b6c98d2b0f738db3bcecef228112d05a1dcde1dc1c42d1daa9add772758b` |
| `scripts/evaluate_v2.py` | `f50c3bb43f0166e42eaa247a56b92412eb16f1f246305258d7d5173e35b58324` |
| `scripts/run_locked_test.py` | `57d5a2da040bdbe4631fb741dcc67e563d47027aec03b313481cbf5a50c076aa` |
| `scripts/verify_seal.py` | `c3ca3e1981aab77e08cd714986c54f0e2ecb5353f1f36066ce5ae108f0d3650a` |
| `baseline/baseline.py` | `81fa1d2522c34eb62cd7b8c65bb192f380a1900a06debae8db230ceea6cdcf77` |
| `baseline/rules_v2.py` | `eed3d1cc673b7b2dd8190db0b3832ad176debb8ba55d9fe2b6d449e23e513a5f` |
| `data_v2/legal_sources_whitelist.json` | `68d2dd4a792f406eee025a8a2fd45a4f04e001cce3f9116907b6c54dc2c745c7` |
| `data_v2/dev_inputs.jsonl` | `08d17181ec9585b494d70eea92e14335da7da0966ae93a04afb64faff90b2c9c` |
| `mvp/server.py` | `aa3ae364607cda003e0c31da0701e0fc81de5b4fdc191901b4ec16a3d51ecb8a` |
| `mvp/index.html` | `b47796b2cc5bb7f604d3ac1a1315de71fd713996e91da5003f802565529b85d1` |
| `mvp/review_flow.py` | `e92583fedbc69900158c773d153460a0b04bed307319283bede472e8765a0a00` |
| `docs_v5/LOCKED_TEST_SCORING_PROTOCOL.md` | `2c260b84861d9d7b9e88fa2264cb7b3a0b8b1bb2ea9eaa683910d98a8ee270f4` |

冻结链路核对：`docs_v3/FREEZE_v2.1_pp2.3.json` 中列出的所有文件，要么与冻结哈希一致，要么与 `docs_v4/FREEZE_ADDENDA.json` 中登记的界面或安全改动一致（只涉及 mvp/server.py 和 mvp/index.html）。`run_locked_test.py` 运行前会再自动核对一次。
