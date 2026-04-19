from __future__ import annotations

from factor_engine.common.prompt_loader import load_prompt_bundle, replace_prompt_tokens
from factor_engine.operators import op_price_volume


_PROMPT_BUNDLE = load_prompt_bundle("factories/price_volume/prompts.yaml")

CICC_STRATEGIES = _PROMPT_BUNDLE["CICC_STRATEGIES"]
STAGE1_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["STAGE1_SYSTEM_PROMPT"]).strip()
_STAGE1_FEW_SHOT_EXAMPLES = f"\n{_PROMPT_BUNDLE['STAGE1_FEW_SHOT_EXAMPLES']}\n\n"
_STAGE1_TASK_TRIGGER = str(_PROMPT_BUNDLE["STAGE1_TASK_TRIGGER"])
STAGE2_SYSTEM_PROMPT = replace_prompt_tokens(
    str(_PROMPT_BUNDLE["STAGE2_SYSTEM_PROMPT_TEMPLATE"]),
    {"__OPERATORS__": op_price_volume.operators_sets},
).strip()
_STAGE2_USER_TEMPLATE = str(_PROMPT_BUNDLE["STAGE2_USER_TEMPLATE"])
STAGE3_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["STAGE3_SYSTEM_PROMPT"]).strip()
_STAGE3_USER_TEMPLATE = str(_PROMPT_BUNDLE["STAGE3_USER_TEMPLATE"])


def build_stage1_user_content(history_text: str, extra_instruction: str = "") -> str:
    guard = ""
    if history_text:
        guard = (
            "【历史回避清单】\n"
            "以下是已生成的因子逻辑。请务必创新，**禁止**生成与下方数学逻辑高度相似的因子：\n"
            f"{history_text.strip()}\n"
        )

    parts = [guard, _STAGE1_FEW_SHOT_EXAMPLES, _STAGE1_TASK_TRIGGER]
    if extra_instruction:
        parts.append(f"【附加指令】\n{extra_instruction}")

    return "\n\n".join([p for p in parts if p])


def build_stage2_user_content(factor_table_markdown: str) -> str:
    return replace_prompt_tokens(
        _STAGE2_USER_TEMPLATE,
        {"{factor_table_markdown}": factor_table_markdown},
    ).strip()


def build_stage3_user_content(draft_code: str) -> str:
    return replace_prompt_tokens(
        _STAGE3_USER_TEMPLATE,
        {"{draft_code}": draft_code},
    ).strip()
