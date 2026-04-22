from __future__ import annotations

from factor_engine.common.prompt_loader import load_prompt_bundle


_PROMPT_BUNDLE = load_prompt_bundle("optimizer/fundamental/prompts.yaml")
_FACTORY_PROMPT_BUNDLE = load_prompt_bundle("factories/fundamental/prompts.yaml")

FUND_JUDGE_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["FUND_JUDGE_SYSTEM_PROMPT"]).strip()
FUND_JUDGE_USER_TEMPLATE = str(_PROMPT_BUNDLE["FUND_JUDGE_USER_TEMPLATE"]).strip()
FUND_REFEREE_PROMPT = str(_PROMPT_BUNDLE["FUND_REFEREE_PROMPT"]).strip()
FUND_DOCTOR_TABLE_SYSTEM_PROMPT = str(_PROMPT_BUNDLE["FUND_DOCTOR_TABLE_SYSTEM_PROMPT"]).strip()
FUND_DOCTOR_TABLE_USER_TEMPLATE = str(_PROMPT_BUNDLE["FUND_DOCTOR_TABLE_USER_TEMPLATE"]).strip()
FUND_CODER_PROMPT_TEMPLATE = str(_PROMPT_BUNDLE["FUND_CODER_PROMPT_TEMPLATE"]).strip()
FUND_OPERATOR_DOCS = str(_FACTORY_PROMPT_BUNDLE["OPERATOR_DOCS"]).strip()

FUND_DATA_SHAPE_CONTEXT = """
Financial data shape constraints:
1. This is low-frequency, quarterly-aligned financial statement data, not daily price-volume data.
2. In practice there are only a few refreshed accounting slices per year, so do not treat the series like dense daily observations.
3. Never invent suffixes such as _TTM / _Q / _YOY unless that exact field already exists in the provided useful field list.
4. Use operators such as TTM / YOY / QOQ / Delay only when they match the real accounting cadence and the available fields.
5. Prefer research-faithful rewrites such as divergence, validation failure, mismatch, acceleration, abnormal ratio, or conditional activation.
6. Do not smooth everything into a generic ranking factor if the prescription is about a specific tail-risk or tail-improvement mechanism.
""".strip()


def build_fund_coder_prompt(
    name: str,
    formula: str,
    logic: str,
    useful_fields: list[str] | None = None,
) -> str:
    prompt = FUND_CODER_PROMPT_TEMPLATE.format(
        name=name,
        formula=formula,
        logic=logic,
    )

    if useful_fields:
        fields_str = ", ".join(
            sorted({str(field).strip() for field in useful_fields if str(field).strip()})
        )
        prompt += (
            "\n\n"
            "[Useful Field Whitelist]\n"
            "You may only use exact field names from the list below inside context['...'].\n"
            "If a field is not in the list, do not write it into the code.\n"
            "Do not translate semantic concepts like Inventory / Revenue / NetProfit into invented context keys.\n"
            "Do not append suffixes such as _TTM / _Q / _YOY unless that exact key is already present in the whitelist.\n"
            "If the prescription references an unavailable field, rewrite the logic so it only depends on fields from this whitelist.\n"
            f"{fields_str}"
        )

    prompt += (
        "\n\n"
        "[Available Operators]\n"
        "The following operator references come from the main fundamental factory and should be treated as the available toolbox.\n"
        f"{FUND_OPERATOR_DOCS}"
        "\n\n"
        "[Financial Data Shape]\n"
        f"{FUND_DATA_SHAPE_CONTEXT}"
    )

    return prompt
