| 指标 | eval_local_v2.1_raw_dev86 | eval_maas_v2.1_raw_dev86 | eval_local_v2.1_pp2.2_dev86 | eval_maas_v2.1_pp2.2_dev86 |
|---|---|---|---|---|
| n | 86 | 86 | 86 | 86 |
| 四分类一致率 | 0.92 | 0.79 | 0.94 | 0.86 |
| 四分类 macro-F1 | 0.93 | 0.85 | 0.93 | 0.87 |
| 契约通过率 | 0.98 | 0.85 | 1.00 | 0.94 |
| 引用子串有效率 | 1.00 | 1.00 | 1.00 | 1.00 |
| 核心性别/婚育线索 P | 0.89 | 0.90 | 0.98 | 0.95 |
| 核心性别/婚育线索 R | 1.00 | 0.90 | 1.00 | 0.97 |
| 人工队列 P | 0.90 | 0.82 | 0.91 | 0.83 |
| 人工队列 R | 1.00 | 1.00 | 1.00 | 1.00 |
| flag F1 | 0.94 | 0.90 | 0.99 | 0.96 |
| review F1 | 1.00 | 0.93 | 0.80 | 0.80 |
| clear F1 | 0.90 | 0.78 | 0.92 | 0.80 |
| unknown F1 | 0.89 | 0.80 | 1.00 | 0.91 |
| 错误：review_predicted_as_flag | 0/8 | 0/8 | 0/8 | 0/8 |
| 错误：flag_predicted_as_review | 0/40 | 0/40 | 0/40 | 0/40 |
| 错误：unknown_forced_determinate | 0/5 | 0/5 | 0/5 | 0/5 |
| 错误：spurious_unknown | 0/81 | 1/81 | 0/81 | 1/81 |
| 错误：normal_condition_false_alarm | 0/7 | 0/7 | 0/7 | 0/7 |
| 错误：care_to_sex_inference | 0/7 | 0/7 | 0/7 | 0/7 |
| 错误：care_dropped_to_clear | 0/7 | 0/7 | 0/7 | 0/7 |
| 错误：quote_history_negation_false_alarm | 0/18 | 1/18 | 0/18 | 1/18 |
| 错误：role_voice_false_alarm | 4/4 | 4/4 | 4/4 | 4/4 |
| 错误：welcome_or_welfare_false_alarm | 1/3 | 0/3 | 1/3 | 2/3 |
| 错误：training_scope_false_alarm | 0/1 | 0/1 | 0/1 | 0/1 |
| 错误：multi_condition_or_history_plus_current_miss | 0/4 | 0/4 | 0/4 | 0/4 |
| 错误：injection_followed | 0/2 | 1/2 | 0/2 | 1/2 |
| 错误：invalid_output | 2/86 | 13/86 | 0/86 | 5/86 |
| 单条延迟中位数(s) | 22.38 | 4.11 | — | — |

### eval_local_v2.1_raw_dev86：四分类混淆矩阵（行=标签，列=预测）

| gold\pred | flag | review | clear | unknown | invalid |
|---|---|---|---|---|---|
| flag | 40 | 0 | 0 | 0 | 0 |
| review | 0 | 8 | 0 | 0 | 0 |
| clear | 5 | 0 | 27 | 0 | 1 |
| unknown | 0 | 0 | 0 | 4 | 1 |

### eval_maas_v2.1_raw_dev86：四分类混淆矩阵（行=标签，列=预测）

| gold\pred | flag | review | clear | unknown | invalid |
|---|---|---|---|---|---|
| flag | 36 | 0 | 0 | 0 | 4 |
| review | 0 | 7 | 0 | 0 | 1 |
| clear | 4 | 0 | 21 | 1 | 7 |
| unknown | 0 | 0 | 0 | 4 | 1 |

### eval_local_v2.1_pp2.2_dev86：四分类混淆矩阵（行=标签，列=预测）

| gold\pred | flag | review | clear | unknown | invalid |
|---|---|---|---|---|---|
| flag | 40 | 0 | 0 | 0 | 0 |
| review | 0 | 8 | 0 | 0 | 0 |
| clear | 1 | 4 | 28 | 0 | 0 |
| unknown | 0 | 0 | 0 | 5 | 0 |

### eval_maas_v2.1_pp2.2_dev86：四分类混淆矩阵（行=标签，列=预测）

| gold\pred | flag | review | clear | unknown | invalid |
|---|---|---|---|---|---|
| flag | 39 | 0 | 0 | 0 | 1 |
| review | 0 | 8 | 0 | 0 | 0 |
| clear | 2 | 4 | 22 | 1 | 4 |
| unknown | 0 | 0 | 0 | 5 | 0 |
