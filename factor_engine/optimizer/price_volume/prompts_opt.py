from __future__ import annotations

from factor_engine.common.prompt_loader import load_prompt_bundle, replace_prompt_tokens
from factor_engine.operators import op_price_volume


_PROMPT_BUNDLE = load_prompt_bundle("optimizer/price_volume/prompts.yaml")

JUDGE_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["JUDGE_SYSTEM_PROMPT"])
JUDGE_USER_TEMPLATE = str(_PROMPT_BUNDLE["JUDGE_USER_TEMPLATE"])
REFEREE_PROMPT = str(_PROMPT_BUNDLE["REFEREE_PROMPT"])
DOCTOR_TABLE_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["DOCTOR_TABLE_SYSTEM_PROMPT"])
DOCTOR_TABLE_USER_TEMPLATE = str(_PROMPT_BUNDLE["DOCTOR_TABLE_USER_TEMPLATE"])
DOCTOR_SYSTEM_BASE = str(_PROMPT_BUNDLE["DOCTOR_SYSTEM_BASE"])
DOCTOR_USER_TEMPLATE = str(_PROMPT_BUNDLE["DOCTOR_USER_TEMPLATE"])
CODER_PROMPT_TEMPLATE = replace_prompt_tokens(
    str(_PROMPT_BUNDLE["CODER_PROMPT_TEMPLATE"]),
    {"__OPERATORS_TOOL__": op_price_volume.operators_sets},
)
