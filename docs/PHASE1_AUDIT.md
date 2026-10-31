# Phase 1 现有技术包审计（2026-10-29，Claude Code 执行）

原始文件未修改。两个 zip 解压到 `../_extracted/`，原 zip SHA-256：
- StarterKit `ac3bd51c…f08de`
- TwoPerson_LegalReview `94761ed5…a8f0`

## 1. 已实际运行（可复现）
| 项 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests`（Python 3.13.11） | 4/4 通过 |
| 重新运行 `baseline.py` | 输出与包内 `outputs/baseline_predictions.jsonl` 逐字节一致 |
| 重新运行 `evaluate.py` | 报告与包内一致：对暂定标签 40/50 |
| JSONL 完整性 | 50 行，均可解析；ID 无重复；文本无重复；字段集合一致 |
| 暂定标签分布 | flag 20 / review 15 / clear 15 |
| 法学盲审表 `LEGAL_BLIND_REVIEW.xlsx` | 三个工作表的判断列全部为空 → **目前不存在任何人工法律标签** |

`baseline.py` 与 `seed_cases.jsonl` 已原样复制到本目录（哈希一致，见 `env/copied_file_hashes.txt`），未做任何“修复”，以保持其作为固定对照组。

## 2. 关键词基线的已确认缺陷（用新构造输入实测）
| 输入 | 基线输出 | 问题 |
|---|---|---|
| 招聘培训专员，仅限男性。 | clear | META 规则优先：只要出现“培训/课堂/引用”等词就整句判 clear |
| 男女不限，宝妈勿扰。 | clear | NEUTRAL 命中后跳过婚育与语境规则 |
| 男女不限，要求已婚已育。 | clear | 同上 |
| 性别不限，但女性须填写婚育情况。 | clear | 同上 |
| 招聘演员助理，只招女生。 | review/special_context | SPECIAL 关键词“演员”压过显性限制 |

其他：META 分支返回 `clear` 却 `needs_human_review: true`（E035/36/37/41/43/49），状态语义自相矛盾。

## 3. 评估方法缺陷
1. **循环验证**：案例、暂定标签、规则均由同一方编写，40/50 是样本内一致率，不是泛化性能。
2. **金标准不存在**：`evaluate.py` 以 `draft_status` 为真值；法学盲审尚未提交。
3. **不支持 `unresolved`**：金标签为 `unresolved` 时直接 `KeyError` 崩溃（已实测）。
4. **无开发/测试划分**，无锁定集。
5. 证据检查只看“是否子串”，不检查非 clear 时证据为空、不检查枚举值、不检查 id 一致。
6. 无 macro 指标、无切片指标（否定误报率、隐性漏报率）。
7. 缺失预测计入分母，但在混淆矩阵中被静默跳过。

## 4. 数据泄漏与数据质量风险
- `challenge` 字段（如 `quote-not-rule`、`explicit-sex`）几乎直接给出答案；`review_notes` 亦然。**两者与 draft 标签都不得进入模型输入**。新代码只读取 `id` 与 `text`，并有单元测试防回归。
- ID 顺序与标签完全成块（E001–E020 全 flag，E021–E029 review…）。锁定集应重新随机编号、打乱顺序。
- 文本长度 9–25 字，均为单句，远短于真实招聘公告；结论不能外推到长文本。
- 文本含全角标点（26 条非 NFKC 规范）；证据校验必须**不做归一化**逐字比对，已有测试覆盖。
- 合成语料标签分布（40% flag）为人为设定，不代表真实发生率。
- 标签存疑：E029 已自带注释；E030 / E039 等中性句与 E021（“更适合小伙子”）的边界需法学判断。

## 5. 结论
现有包可运行、可复现，但只能用作**内部开发检查**。任何对外性能表述必须等待法学独立标签冻结后，用本目录 `scripts/evaluate.py --label-source human_frozen` 在锁定集上一次性计算。
