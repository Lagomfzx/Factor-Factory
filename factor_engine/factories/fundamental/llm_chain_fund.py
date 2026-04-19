from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from factor_engine.common.history import append_factor_history
from factor_engine.common.storage import save_output_to_file
from factor_engine.factories.fundamental.prompt_fund import (
    STAGE1_SYSTEM_PROMPT_TEMPLATE,
    STAGE2_SYSTEM_PROMPT,
    STAGE3_SYSTEM_PROMPT,
    build_stage1_user_content,
    build_stage2_user_content,
    build_stage3_user_content,
)


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


def run_three_stages_with_memory(
    config,
    client1,
    client2,
    history_text,
    all_fields,
    extra_instruction="",
    system_prompt=None,
):
    stage1_system_prompt = system_prompt or STAGE1_SYSTEM_PROMPT_TEMPLATE

    messages_stage1 = [
        {"role": "system", "content": stage1_system_prompt},
        {
            "role": "user",
            "content": build_stage1_user_content(history_text, all_fields, extra_instruction),
        },
    ]

    print(">>> Calling Stage 1 (Factor Design)...")
    resp1 = client1.invoke(to_lc_messages(messages_stage1))
    text_1 = getattr(resp1, "content", str(resp1))

    save_output_to_file(text_1, file_prefix="model_chain_1_output", config=config)
    append_factor_history(text_1, config)

    messages_stage2 = [
        {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
        {"role": "user", "content": build_stage2_user_content(text_1)},
    ]

    print(">>> Calling Stage 2 (Code Generation)...")
    resp2 = client2.invoke(to_lc_messages(messages_stage2))
    text_2 = getattr(resp2, "content", str(resp2))

    save_output_to_file(text_2, file_prefix="model_chain_2_output", config=config)

    messages_stage3 = [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {"role": "user", "content": build_stage3_user_content(text_2, all_fields)},
    ]

    print(">>> Calling Stage 3 (Code Correction)...")
    resp3 = client2.invoke(to_lc_messages(messages_stage3))
    text_3 = getattr(resp3, "content", str(resp3))

    save_output_to_file(text_3, file_prefix="model_chain_3_output", config=config)

    return text_3, text_1
