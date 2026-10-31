"""Conservative rule-based baseline, NOT a legal decision engine."""
import argparse
import json
import re
from pathlib import Path

EXPLICIT = [r"(?:限|只招|仅招|只收|只要|仅面向|限招)\s*(?:男|女)(?:性|生|士|同志)?", r"(?:男性|女性|男生|女生|男士|女士)\s*(?:优先|优先考虑|优先录用)", r"(?:优先考虑|优先录用)\s*(?:男性|女性|男生|女生|男士|女士)"]
REPRODUCTIVE = [r"已婚已育", r"未婚未育", r"(?:不|无|没有)\s*生育计划", r"(?:不|不得|不可)\s*(?:结婚|生育|怀孕)", r"(?:须|必须|要求|需要).*?(?:婚育情况|怀孕计划|妊娠检测|妊娠测试)", r"(?:婚育|生育|婚姻).*?(?:优先|条件|承诺)"]
CONTEXTUAL = [r"宝妈勿扰", r"(?:男生|男性|男士|女同志|女性|女生).*?(?:更适合|比较合适|可能扛不住|慎重投递)", r"(?:家庭负担|育儿负担|生育安排|家里没人需要照顾)"]
SPECIAL = [r"(?:演员|表演|角色|女高音|专项培训|禁忌作业|国家规定|特殊岗位)"]
META = [r"(?:反对|禁止|不得出现|请勿写|不能写|已经删除|已删除|已经废止|现已删除|旧公告已经作废|调查问卷|课堂|讲座|培训|引用|示例错误)"]
NEUTRAL = [r"(?:男女不限|不限性别|性别不限|任何性别均可|所有性别均可|无婚育限制|无需披露婚姻|不以婚育|不要求婚育|欢迎女性申请|不限制性别)"]

def first_match(patterns, s):
    for p in patterns:
        m = re.search(p, s, flags=re.I)
        if m:
            return m.group(0)
    return ''

def predict(item):
    s = item['text']
    # Simple metadata suppression is intentionally brittle: the experiment asks whether LLM helps.
    if first_match(META, s):
        return {'id': item['id'], 'status': 'clear', 'issue_type': 'none', 'evidence': '', 'reason': '疑似法律讨论/已撤销限制表达，需核对文本性质', 'needs_human_review': True}
    if first_match(SPECIAL, s):
        evidence = first_match(SPECIAL, s)
        return {'id': item['id'], 'status': 'review', 'issue_type': 'special_context', 'evidence': evidence, 'reason': '特殊活动或国家规定背景待核实', 'needs_human_review': True}
    if first_match(NEUTRAL, s) and not first_match(EXPLICIT, s):
        return {'id': item['id'], 'status': 'clear', 'issue_type': 'none', 'evidence': '', 'reason': '存在平等招聘或否定限制的表述', 'needs_human_review': False}
    for patterns, kind in [(EXPLICIT, 'sex_preference'), (REPRODUCTIVE, 'marital_reproductive')]:
        e = first_match(patterns, s)
        if e:
            return {'id': item['id'], 'status': 'flag', 'issue_type': kind, 'evidence': e, 'reason': '发现限制性关键词，需人工复核实际法律语境', 'needs_human_review': True}
    e = first_match(CONTEXTUAL, s)
    if e:
        return {'id': item['id'], 'status': 'review', 'issue_type': 'contextual_bias', 'evidence': e, 'reason': '发现间接排斥的可能线索', 'needs_human_review': True}
    return {'id': item['id'], 'status': 'clear', 'issue_type': 'none', 'evidence': '', 'reason': '规则未命中；不代表法律合规', 'needs_human_review': False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    items = [json.loads(line) for line in Path(args.input).read_text(encoding='utf-8').splitlines() if line.strip()]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as fh:
        for item in items:
            fh.write(json.dumps(predict(item), ensure_ascii=False) + '\n')
    print(f'Wrote {len(items)} baseline predictions: {out}')
if __name__ == '__main__':
    main()
