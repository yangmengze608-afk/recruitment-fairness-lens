# 讯飞星辰 MaaS API 核验记录（P0）

核验时间：2026-10-30（AEDT）。来源：官方文档页面，用 r.jina.ai 读取。调用尚未发生。

## 文档确认的事实
| 项 | 文档内容 | 来源页 |
|---|---|---|
| 接口 | `POST https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions`，兼容 OpenAI；鉴权方式为 `Authorization: Bearer <APIKey>` | 3.1.1 Chat、1.1 API 接入 |
| 模型 ID | `spark-x2.6-4b` 在可选值中（另有 spark-x2.6、spark-x2.6-preview、spark-x2.5、spark-x2.5-4b、spark-x2.5-1.7b）；上架日期 2026/10/21 | 3.1.1、2.1.1 |
| thinking | `thinking.type`：enabled（默认）/ disabled / auto | 3.1.1 |
| 采样 | `temperature` 固定为 1、`top_p` 固定为 0.95，建议不要传入；**不支持贪心或确定性生成** | 3.1.1 |
| JSON mode / response_format | 文档**没有**列出。有 `tools`（function，带 JSON Schema 参数）和 `tool_choice` | 3.1.1 |
| 输出上限 | `max_completion_tokens`（`max_tokens` 已废弃） | 3.1.1 |
| 响应 | 包含 `model`（实际使用的模型 ID）、`usage`（prompt、completion、reasoning tokens）、`finish_reason` | 3.1.1 |
| 限流 | 每个 Key + 模型默认并发 20、TPM 100 万。429 不计费；503 若已部分处理则按实际消耗计费 | 1.3 |
| 错误码 | 401 Key 错误；403/11200 未开通该模型；403/11221 套餐不含该模型；429/11201 当日用量达到上限；10013/10014 敏感内容 | 1.2 |
| 模型介绍 | 写有“Spark-X2.6-4B … 新增 high/low/none 三档 reasoning effort” | 2.1.1 |

## 无法从文档确认
- **价格与免费额度**：文档里没有 spark-x2.6-4b 的价格。公开搜索只查到云端 293B 的价格和 X2.5-4B 曾经“限时免费”，都不能套用到 X2.6-4B。需要负责人登录控制台确认。
- **云端 revision、精度、推理框架**：文档和响应字段都没有披露。记录为“云端具体 revision 未披露”。不能声称与 HF 权重 d1b5f260 逐字节一致。
- **是否需要单独开通**：403/11200 的说明暗示需要为应用开通模型服务，要以控制台为准。

## 与本地配置的差异（不等价）
| | 本地（Stage 1/2） | MaaS |
|---|---|---|
| 权重 | HF XHToken/Spark-X2.6-4B @ d1b5f260，已校验 SHA-256 | 未披露 |
| 解码 | 贪心（do_sample=False） | 服务端固定 T=1、top_p=0.95，有随机性 |
| 关闭思考 | chat template `enable_thinking=False` | `thinking: {type: disabled}` |
| 精度 | bf16，无量化 | 未披露 |

## 比赛合规（官方 Issue #16 原文核对）
- Issue 写的是“download and use it”，要求记录 “model revision, runtime, hardware, precision or quantization”；使用镜像时须注明来源和对应 revision。
- Issue **没有**明确说明通过官方 API 调用是否算作有效使用方式。
- 处理方式：本地开源权重的真实运行记录作为主要的 Spark 使用证据保留；API 作为 Demo 推理服务，如实披露“云端 revision 未披露、采样不同”。需要时，可以通过 Issue 中列出的 ifly_opensource@iflytek.com 向组织方咨询。邮件草稿见 `docs_v3/ORGANIZER_QUERY_DRAFT.md`，**尚未发送**。

## 已实现（未发起任何真实调用）
- `rfl/providers.py`：`xfyun_maas` 与 `local_transformers` 两个 Provider。
  - 密钥来源：环境变量 `XFYUN_API_KEY`，或文件 `~/.config/rfl/xfyun_api_key`（权限必须是 600）。
  - 防护：调用次数上限 `XFYUN_MAX_CALLS`（默认 60）；超时 90 秒；只对 5xx 和 QPS/TPM 类 429 最多重试 2 次，当日上限 11201 不重试。
  - 如果响应里的 `model` 不是 `spark-x2.6-4b`，结果记为 invalid。
- `scripts/run_provider.py`：保存请求体（不含 Authorization）、每次 HTTP 尝试的原始响应、用量和延迟；不会覆盖已有运行目录。
- MVP 服务端通过 Provider 调用模型，浏览器拿不到密钥。
