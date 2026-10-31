"""Human-review flow (review cards + closing rules). NOT part of the frozen inference / scoring chain.

Implements HUMAN_REVIEW_PRODUCT_REQUIREMENTS.md (法学联合研究者 608, 2026-10-31) at the UI / workflow layer:
per-channel review cards (why queued, <=3 targeted questions, materials, responsible role, basis with level and
article, a template rewrite suggestion) and status rules that refuse to close a case without the required record.
Article references follow LEGAL_EVIDENCE_MEMO.md (2026-10-30). They are human-review references only: the frozen
`source_ids` mapping in rfl/contract_v2.py is unchanged, and S21 is NOT in the frozen whitelist.
The model never sets a status; every status is chosen and justified by a named person.
"""
REVIEW_FLOW_VERSION = "review-flow-v1.0-2026-10-31"

LANE_TASK = {
    "flag": "文本线索明确：重点核对规范适用、是否援引例外、以及如何修改文案。",
    "review": "语义或关联待核：先回答事实问题，再决定是否升级或更正。",
    "unknown": "关键材料缺失：列出缺什么，补齐前保持待核。",
    "clear": "未见本产品关注的线索：不额外增加审核任务（不表示合法）。",
    "invalid": "模型输出未通过校验：由人工阅读原文判断，或重新请求。",
}

CARDS = {
    "explicit_sex": {
        "title": "明确性别条件",
        "queue_reason": "原文对应聘者的性别作出限定、优先或劝退。",
        "questions": ["该条件是否用于当前这次招聘？", "如果援引了例外，具体是哪部规范的哪一条，岗位的实际职责是什么？",
                      "岗位真正需要的能力能否改写成对所有应聘者一致适用、可以验证的要求？"],
        "materials": ["岗位说明书", "统一的筛选规则", "如果援引例外：规范全称、条款、版本，以及作业事实"],
        "role": "招聘审核人员联系发布方；对规范适用有争议的，交法律审阅者",
        "basis": ["若限男或男性优先：S01 妇女权益保障法（法律）第43条第1项",
                  "一般平等就业：S02 就业促进法（法律）第3、26条；S21 劳动法（法律）第12条；S03 人力资源市场暂行条例（行政法规）第24条；S04 2024年招聘信息通知（部门文件）第1项",
                  "若限女或女性优先：不机械援引 S01 第43条第1项，按一般平等就业依据，并核对 S02 第27条、S21 第13条的例外"],
        "suggestion": "建议删除「{q}」。如果岗位确有能力或排班需要，改写为具体、可以验证、对所有应聘者一致适用的要求，例如具体的负重、班次或证书。",
    },
    "marriage_birth": {
        "title": "婚育条件、婚育调查或孕检",
        "queue_reason": "原文把婚姻、生育状况或计划作为条件，或者要求询问、承诺、检查这些情况。",
        "questions": ["对应的是哪一项：录用条件、承诺书、登记表字段，还是体检项目？",
                      "属于哪一类：限制结婚、生育计划、婚育状态、进一步询问，还是孕检？",
                      "是否援引了具体的国家规定？请给出全称和条款。"],
        "materials": ["实际使用的表单或承诺书", "体检项目清单", "录用条件原文"],
        "role": "招聘审核人员；对主体范围、个人基本信息限定有争议的，交法律审阅者",
        "basis": ["S01 妇女权益保障法（法律）第43条：第2项（进一步询问女性婚育，注意“个人基本信息”的限定）、第3项（孕检）、第4项（婚育条件）",
                  "S02 就业促进法（法律）第27条；S04 2024年招聘信息通知（部门文件）第1项",
                  "“男女都要回答”不能作为自动免责的理由"],
        "suggestion": "建议删除「{q}」及对应的承诺书、表单字段或体检项目，不以婚育状况或计划作为录用条件，修改后重新检测。",
    },
    "care_condition": {
        "title": "照护条件（性别关联未建立）",
        "queue_reason": "原文以家庭、育儿或照护状况作为条件或偏好。文字本身不表明与性别或婚育有关。",
        "questions": ["岗位实际需要什么样的班次、出差频率或驻场安排？",
                      "能满足这些安排的照护者，是否按同样的标准考虑？",
                      "这个条件是否决定录用、优先顺序或面试资格？是否对不同性别同样执行？"],
        "materials": ["岗位职责与排班、出差要求", "统一的筛选标准", "必要的脱敏摘录（不收集求职者家庭信息）"],
        "role": "招聘审核人员联系发布方；不向求职者索取家庭或婚育信息",
        "basis": ["S02 就业促进法（法律）第3、26条；S04 2024年招聘信息通知（部门文件）第1项（岗位适配性）",
                  "S07 劳动合同法（法律）第8条：只能了解与劳动合同直接相关的情况，不是调查家庭的授权",
                  "S08 民法典第1058条：仅用作纠正“照护等于女性”刻板印象的依据；S10 指导案例185号：只借用分析路径（原案是地域歧视，不是照护案）"],
        "suggestion": "建议把「{q}」改写为具体的履职条件（例如具体班次、出差频率），不以家庭或照护状况筛选应聘者。",
    },
    "exception_missing": {
        "title": "特殊岗位或声称例外",
        "queue_reason": "原文自称依据国家规定、特殊工种或禁忌作业，但没有给出可以核对的条款和岗位事实。",
        "questions": ["所依据规范的全称、条款和版本是什么？",
                      "岗位的真实职责和作业强度是什么（例如负重的次数和重量）？",
                      "该规定适用于全体女性，还是只适用于特定期间（孕期、哺乳期等）？"],
        "materials": ["规范原文及版本", "岗位作业事实材料", "适用对象说明"],
        "role": "招聘审核人员收集材料；规范和事实材料都齐全后，交法律审阅者核对适用",
        "basis": ["S02 就业促进法（法律）第27条；S21 劳动法（法律）第13条、第59—63条",
                  "S05 女职工劳动保护特别规定（行政法规）第4条及附录。例如一般负重：每小时6次以上且每次超过20公斤，或间断负重每次超过25公斤。不能只凭“需要搬运”就援引"],
        "suggestion": "在补齐规范条款和岗位作业事实之前，暂不发布「{q}」；如果无法提供，建议删除该限定。",
    },
    "role_voice": {
        "title": "角色或声部表达",
        "queue_reason": "原文涉及剧中角色或声部。需要分清这是对呈现效果或能力的要求，还是对应聘者本人身份的限定。",
        "questions": ["这里要求的是角色呈现、声部能力，还是应聘者本人的身份？",
                      "如果另外限定了应聘者本人的性别，依据是什么？", "能否改写为按试演、试唱评估？"],
        "materials": ["角色或声部说明", "选拔方式"],
        "role": "招聘审核人员；没有行业一律豁免，身份限定需要依据",
        "basis": ["S02 就业促进法（法律）第26条；S04 2024年招聘信息通知（部门文件）第1项", "演艺行业不设一律豁免"],
        "suggestion": "如果只是角色或声部要求，建议写明“按角色或声部的试演、试唱能力评估”；如果另外限定了应聘者本人的身份，需要提供依据。",
    },
    "context": {
        "title": "语境暗示、引用或历史条件",
        "queue_reason": "原文的语境可能暗示性别偏好，或者包含引用、历史条件，需要确认当前招聘是否采用。",
        "questions": ["当前是谁在采用这个条件，适用于什么时间？", "这只是引用或历史内容，还是当前仍在使用？",
                      "还有哪些页面或渠道仍在显示这个条件？"],
        "materials": ["当前有效的招聘页面", "历史版本记录"],
        "role": "招聘审核人员",
        "basis": ["S02 就业促进法（法律）第26条；S04 2024年招聘信息通知（部门文件）第1、2项（发布审核）",
                  "删除声明不能证明已经整改；历史问题和当前条件要分别记录"],
        "suggestion": "核实「{q}」是否被当前招聘采用；如果只是引用或历史内容，建议在文案中标明，避免被理解为当前条件。",
    },
}

# status -> (label, required fields). evidence entries: {"description","source","verification"}
STATUSES = {
    "pending_evidence": ("待补材料", ["missing_materials", "next_step"]),
    "context_corrected": ("语境误报已更正", ["rationale"]),
    "text_revised": ("已形成修改文案", ["revised_text", "revised_by", "recheck"]),
    "concern_supported": ("风险线索获补强，交法律审阅", ["evidence_obtained", "next_step"]),
    "exception_review": ("材料已齐，待核例外适用", ["evidence_obtained", "next_step"]),
    "unresolved": ("材料缺失或意见不一，保留不确定", ["rationale"]),
    "job_requirement_supported": ("材料支持岗位解释（不等于整体合法）", ["evidence_obtained", "rationale"]),
    "out_of_scope": ("不属于本产品范围", ["rationale"]),
}
LEGACY_STATUSES = {"legal_review_required"}  # accepted only when loading old records
VERIFICATION = ("self_reported", "independently_verified", "not_obtained")
DECISIONS = ("accept", "modify", "reject", "pending")


def channel_of(finding):
    if finding.get("scope_check") == "performance_role_or_voice":
        return "role_voice"
    return finding.get("reason") if finding.get("reason") in CARDS else "context"


def build_cards(record):
    cards = []
    for i, f in enumerate(record.get("findings") or []):
        ch = channel_of(f)
        c = CARDS[ch]
        cards.append({"finding_index": i, "channel": ch, "title": c["title"], "lane": f.get("triage"),
                      "lane_task": LANE_TASK.get(f.get("triage"), ""), "quote": f.get("quote"),
                      "queue_reason": c["queue_reason"], "questions": c["questions"][:3], "materials": c["materials"],
                      "role": c["role"], "basis": c["basis"],
                      "basis_note": "条款参考来自法律依据备忘录（2026-10-30），适用性需要法律审阅者确认；S21 未纳入冻结白名单。",
                      "suggestion_template": c["suggestion"].format(q=f.get("quote", "")),
                      "suggestion_note": "模板建议，不是模型输出，也不是法律意见；修改文案与原文分开保存。"})
    return {"version": REVIEW_FLOW_VERSION, "document_lane_task": LANE_TASK.get(record.get("triage"), ""), "cards": cards}


def _nonempty(v):
    return isinstance(v, str) and v.strip() != ""


def validate_review(body, n_findings):
    """Return a list of human-readable errors (empty list = OK). Never infers or fills anything."""
    errs = []
    st = body.get("human_outcome")
    if st not in STATUSES:
        return [f"未知的处理状态：{st}"]
    if not _nonempty(body.get("reviewer")):
        errs.append("必须填写审核人（真实姓名或角色）")
    if body.get("human_triage") not in (None, "", "flag", "review", "clear", "unknown"):
        errs.append("人工分流取值无效")
    fds = body.get("finding_decisions", [])
    if not isinstance(fds, list) or any(not isinstance(d, dict) or d.get("decision") not in DECISIONS for d in fds):
        errs.append("逐条判断取值无效")
    ev = body.get("evidence") or []
    if not isinstance(ev, list) or any(not isinstance(e, dict) or e.get("verification") not in VERIFICATION
                                       or not _nonempty(e.get("description")) for e in ev):
        errs.append("证据条目格式无效（需要描述和核验状态）")
        ev = []
    obtained = [e for e in ev if e.get("verification") != "not_obtained"]
    label, required = STATUSES[st]
    for r in required:
        if r == "evidence_obtained":
            if not obtained:
                errs.append(f"选择“{label}”必须至少登记一份已取得的材料（发布方自述请标为 self_reported）")
        elif r == "recheck":
            if not (_nonempty(body.get("recheck_note")) or _nonempty(body.get("recheck_analysis_id"))):
                errs.append("“已形成修改文案”必须附上再检测记录（再检测的记录编号或说明）")
        elif not _nonempty(body.get(r)):
            names = {"missing_materials": "缺少的材料", "next_step": "下一步", "rationale": "理由",
                     "revised_text": "修改后的文案", "revised_by": "实际修改人"}
            errs.append(f"选择“{label}”必须填写：{names.get(r, r)}")
    return errs
