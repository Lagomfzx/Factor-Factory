from __future__ import annotations

from factor_engine.common.prompt_loader import load_prompt_bundle, replace_prompt_tokens
from factor_engine.factories.fundamental.prompt_fund import _build_governance_appendix
from factor_engine.factories.fundamental_single_metric.field_cards import (
    build_field_card,
    render_field_card,
)


_PROMPT_BUNDLE = load_prompt_bundle("factories/fundamental_single_metric/prompts.yaml")

CICC_STRATEGIES = _PROMPT_BUNDLE.get("CICC_STRATEGIES", {})
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


def build_target_field_instruction(
    target_field: str,
    field_governance: dict | None = None,
    field_card: dict | None = None,
) -> str:
    card = field_card or build_field_card(target_field, field_governance)
    field_card_text = render_field_card(card)
    return (
        f"【目标科目】{target_field}\n"
        f"{field_card_text}\n"
        "本轮只能围绕这个目标科目展开。请先判断该科目的财务角色，"
        "再为该科目设计 10 个单因子变体。你可以从水平、同比、"
        "同比变化、一年趋势斜率、两年趋势斜率、回归残差、标准化意外、"
        "历史异常、历史位置、基本面回撤、过去高点距离、过去低点距离、"
        "符号切换、连续改善比例、反向观察等模板中选择最适合的方式；"
        "不要机械套满模板。每个因子都必须在逻辑解释中说明高分组画像、低分组画像、"
        "全市场截面排序含义和待验证假设；不要预设高分组或低分组一定更好。"
        "严格单科目模式下，公式只能包含该目标科目，不要引入其他财务字段。"
    )


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
            "以下是已生成的因子。请务必创新，**禁止**生成与下方母变量和变换模板高度相似的因子：\n"
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
    return replace_prompt_tokens(
        _STAGE3_USER_TEMPLATE,
        {
            "{draft_code}": draft_code,
            "{fields_str}": fields_str,
        },
    ).strip()
