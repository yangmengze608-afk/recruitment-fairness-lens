"""Prompt v1. Frozen copy of the system prompt in SPARK_INTERFACE.md plus the output schema.

Only `id` and `text` of an input record are ever sent to the model. Draft labels,
`challenge`, and `review_notes` are never read here (see build_messages).
Any change to this file must bump PROMPT_VERSION and must not be tuned on a locked test set.
"""
PROMPT_VERSION = "v1-2026-10-29"

SYSTEM_PROMPT = (
    "你是一名招聘文案人工审核的辅助工具，不是法律裁判。请仅根据给定原文识别可能需要人工复核的性别和婚育限制，"
    "返回一行符合契约的 JSON，不输出其他文本。区分实际岗位条件与否定、报道或培训引用；无法确定是否属于例外时返回 review。"
    "不要作法律定性，不补造事实。evidence 必须为原文连续子串。判断为 clear 时可返回空证据。\n\n"
    "JSON 契约：\n"
    '{"id":"<与输入一致>","status":"flag|review|clear","issue_type":"sex_preference|marital_reproductive|contextual_bias|special_context|none",'
    '"evidence":"原文连续子串，或空字符串","reason":"一句话解释，不得直接判定违法","needs_human_review":true}'
)


def build_messages(record):
    allowed = {"id": record["id"], "text": record["text"]}
    user = f"id: {allowed['id']}\n原文：{allowed['text']}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
