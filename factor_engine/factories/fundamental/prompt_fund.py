from __future__ import annotations

from factor_engine.common.prompt_loader import load_prompt_bundle, replace_prompt_tokens


_PROMPT_BUNDLE = load_prompt_bundle("factories/fundamental/prompts.yaml")

CICC_STRATEGIES = _PROMPT_BUNDLE["CICC_STRATEGIES"]
STAGE1_SYSTEM_PROMPT_TEMPLATE = str(_PROMPT_BUNDLE["STAGE1_SYSTEM_PROMPT_TEMPLATE"]).strip()
_STAGE1_FEW_SHOT_EXAMPLES = f"\n{_PROMPT_BUNDLE['STAGE1_FEW_SHOT_EXAMPLES']}\n\n"
_STAGE1_TASK_TRIGGER = str(_PROMPT_BUNDLE["STAGE1_TASK_TRIGGER"])
OPERATOR_DOCS = str(_PROMPT_BUNDLE["OPERATOR_DOCS"])
STAGE2_SYSTEM_PROMPT = replace_prompt_tokens(
    str(_PROMPT_BUNDLE["STAGE2_SYSTEM_PROMPT_TEMPLATE"]),
    {"__OPERATOR_DOCS__": OPERATOR_DOCS},
).strip()
_STAGE2_USER_TEMPLATE = str(_PROMPT_BUNDLE["STAGE2_USER_TEMPLATE"])
STAGE3_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["STAGE3_SYSTEM_PROMPT"]).strip()
_STAGE3_USER_TEMPLATE = str(_PROMPT_BUNDLE["STAGE3_USER_TEMPLATE"])


def _build_governance_appendix(field_governance: dict | None) -> str:
    if not field_governance:
        return ""

    lines = ["[Field Governance]"]
    focus_fields = field_governance.get("focus_fields") or []
    denominator_fields = field_governance.get("denominator_fields") or []
    cautious_fields = field_governance.get("cautious_fields") or []
    note_fields = field_governance.get("note_fields") or []

    if focus_fields:
        lines.append(
            "Prefer these focus fields when they fit the financial logic: "
            + ", ".join(focus_fields[:30])
        )
    if denominator_fields:
        lines.append(
            "When a ratio needs a denominator, prefer these fields first: "
            + ", ".join(denominator_fields[:20])
        )
    if cautious_fields:
        lines.append(
            "Use these fields cautiously; avoid letting them alone define the main factor thesis: "
            + ", ".join(cautious_fields[:20])
        )
    if note_fields:
        lines.append(
            "These are note-like enhancement fields; prefer using them as confirmation, risk filter, or adjustment instead of the main backbone: "
            + ", ".join(note_fields[:20])
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def build_stage1_user_content(
    history_text: str,
    data_context_str: str,
    extra_instruction: str = "",
    field_governance: dict | None = None,
) -> str:
    guard = ""
    if history_text:
        guard = (
            "【历史回避清单】\n"
            "以下是已生成的因子。请务必创新，**禁止**生成与下方逻辑高度相似的因子：\n"
            f"{history_text.strip()}\n"
        )

    context_part = f"\n{data_context_str}\n"

    parts = [context_part, guard, _STAGE1_FEW_SHOT_EXAMPLES, _STAGE1_TASK_TRIGGER]
    if extra_instruction:
        parts.append(f"【附加指令】\n{extra_instruction}")
    governance_appendix = _build_governance_appendix(field_governance)
    if governance_appendix:
        parts.append(governance_appendix)

    return "\n\n".join([p for p in parts if p])


def build_stage2_user_content(factor_table_markdown: str) -> str:
    return replace_prompt_tokens(
        _STAGE2_USER_TEMPLATE,
        {"{factor_table_markdown}": factor_table_markdown},
    ).strip()


def build_stage3_user_content(
    draft_code: str,
    all_fields: list,
) -> str:
    fields_str = str(all_fields)
    content = replace_prompt_tokens(
        _STAGE3_USER_TEMPLATE,
        {
            "{draft_code}": draft_code,
            "{fields_str}": fields_str,
        },
    ).strip()
    return content
