import os
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from factor_engine.common.history import append_factor_history
from factor_engine.common.storage import save_output_to_file
from factor_engine.factories.fundamental_single_metric.prompt_fund_single import (
    STAGE1_SYSTEM_PROMPT_TEMPLATE,
    STAGE2_SYSTEM_PROMPT,
    STAGE3_SYSTEM_PROMPT,
    build_stage1_user_content,
    build_stage2_user_content,
    build_stage3_user_content,
)


TRANSIENT_LLM_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_LLM_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailableError",
}


def to_lc_messages(messages_payload):
    lc_messages = []
    for message in messages_payload:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or str(raw_value).strip() == "":
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError:
        return default
    return max(value, 1)


def _is_transient_llm_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code in TRANSIENT_LLM_STATUS_CODES:
        return True
    return exc.__class__.__name__ in TRANSIENT_LLM_ERROR_NAMES


def _invoke_with_retry(client, messages, stage_name: str):
    max_attempts = _read_int_env("FACTOR_FACTORY_LLM_MAX_RETRIES", 4)
    base_sleep_seconds = _read_int_env("FACTOR_FACTORY_LLM_RETRY_BASE_SECONDS", 5)

    for attempt in range(1, max_attempts + 1):
        try:
            return client.invoke(messages)
        except Exception as exc:
            if not _is_transient_llm_error(exc) or attempt >= max_attempts:
                print(
                    f">>> {stage_name} failed after {attempt}/{max_attempts} attempts: "
                    f"{exc.__class__.__name__}: {exc}"
                )
                raise

            sleep_seconds = base_sleep_seconds * (2 ** (attempt - 1))
            print(
                f">>> {stage_name} transient error "
                f"({exc.__class__.__name__}: {exc}); retrying in {sleep_seconds}s "
                f"({attempt}/{max_attempts})..."
            )
            time.sleep(sleep_seconds)


def run_three_stages_with_memory(
    config,
    client1,
    client2,
    history_text,
    all_fields,
    extra_instruction="",
    system_prompt=None,
    field_governance=None,
):
    stage1_system_prompt = system_prompt or STAGE1_SYSTEM_PROMPT_TEMPLATE

    messages_stage1 = [
        {"role": "system", "content": stage1_system_prompt},
        {
            "role": "user",
            "content": build_stage1_user_content(
                history_text,
                all_fields,
                extra_instruction,
                field_governance=field_governance,
            ),
        },
    ]

    print(">>> Calling Stage 1 (Single-Metric Fundamental Design)...")
    resp1 = _invoke_with_retry(
        client1,
        to_lc_messages(messages_stage1),
        "Stage 1 (Single-Metric Fundamental Design)",
    )
    text_1 = getattr(resp1, "content", str(resp1))

    save_output_to_file(text_1, file_prefix="model_chain_1_output", config=config)
    append_factor_history(text_1, config)

    messages_stage2 = [
        {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
        {"role": "user", "content": build_stage2_user_content(text_1)},
    ]

    print(">>> Calling Stage 2 (Single-Metric Code Generation)...")
    resp2 = _invoke_with_retry(
        client2,
        to_lc_messages(messages_stage2),
        "Stage 2 (Single-Metric Code Generation)",
    )
    text_2 = getattr(resp2, "content", str(resp2))

    save_output_to_file(text_2, file_prefix="model_chain_2_output", config=config)

    messages_stage3 = [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_stage3_user_content(
                text_2,
                all_fields,
            ),
        },
    ]

    print(">>> Calling Stage 3 (Single-Metric Code Correction)...")
    resp3 = _invoke_with_retry(
        client2,
        to_lc_messages(messages_stage3),
        "Stage 3 (Single-Metric Code Correction)",
    )
    text_3 = getattr(resp3, "content", str(resp3))

    save_output_to_file(text_3, file_prefix="model_chain_3_output", config=config)

    return text_3, text_1
