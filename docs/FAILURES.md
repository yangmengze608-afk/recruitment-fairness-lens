# 失败案例与错误原因记录（Round 1，2026-10-29）

全部来自真实 Spark-X2.6-4B 运行，原始输出见对应 `outputs/spark/<run>/raw.jsonl`。未修改、未删除任何失败项。

## A. 结构失败（仅出现在 thinking=low 配置）
| run | id | 现象 | 原因 |
|---|---|---|---|
| smoke_v1_thinklow | S02 | `parse:no_json_object` | 思考 1536 token 用尽仍在推敲 flag/review，未输出 JSON |
| smoke_v1_thinklow | S07 | `parse:no_json_object` | 同上 |
| smoke_v1_thinklow | S14 | 原样输出契约模板 `"status":"flag\|review\|clear"`、`evidence":"原文连续子串，或空字符串"` | 思考中反复纠结契约里 `needs_human_review:true` 示例与 clear 的矛盾，最终照抄模板；预算耗尽 |

thinking=off 配置：64/64（14 smoke + 50 seed）全部通过 JSON 契约校验，所有非空 evidence 均为原文逐字连续子串。

## B. 语义失败（thinking=off，主配置）
1. **`review` 塌缩为 `flag`**（最主要问题）。smoke：S10 话剧女性角色、S11 依国家规定不安排女职工、S12 "没有家庭方面的牵挂" 均判 flag。seed：draft 为 review 的 15 条中 12 条判 flag（E021–E028、E045–E047、E049）。模型理由里常写“需人工复核是否属于合理例外”，但状态仍选 flag —— 即它识别到了不确定性，却没有把不确定性映射到 `review`。
2. **包容性表述误判为限制**：E033 “欢迎女性申请技术岗位。” → flag/sex_preference，理由称“明确限定申请主体为女性”。这是语义误读。
3. **问卷/讨论引用误报**：E041 问卷中的“男性优先”→ flag；E040 公开课讨论 → review。（S06、S07 的培训/新闻引用则正确判 clear。）
4. **专项岗位漏报**：E050 “某专项岗位需按照国家规定确认聘用条件。” → clear（draft 为 review）。
5. **`needs_human_review` 恒为 true**（含所有 clear）。疑似模型照抄契约示例值；当前字段对下游无信息量。

## C. 根因假设（待验证，不在锁定集上验证）
- 提示词 v1 只给了 review 的一句规则（“无法确定是否属于例外时返回 review”），**没有给出 flag / review / clear 的定义**（LABELING_GUIDE 中有，但 SPARK_INTERFACE 的系统提示未包含）。
- 契约示例把 `needs_human_review` 写成字面量 `true`。
- 思考模式下模型把大量预算花在解读契约歧义上，说明契约本身需要澄清。

## D. 基线（固定对照组）的失败
见 `docs/PHASE1_AUDIT.md` §2 与 smoke 对照：S07 新闻引用误报 flag；S08 “有孩子的妈妈” 漏报；S11、S12 漏报；S13 “男女不限，但已婚者优先” 漏报。
