from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

from factor_engine.common.config import FactoryConfig
from factor_engine.common.platform_api import clean_platform_result
from factor_engine.common.runtime_env import (
    get_bool_env,
    get_env,
    get_int_env,
    load_dotenv_files,
    project_root,
    require_env,
)
from factor_engine.common.storage import tag_kept_factors
from factor_engine.factories.fundamental.local_calc_fund import generate_snapshot_calendar
from factor_engine.factories.fundamental.pipeline_fund import run_hybrid_pipeline
from factor_engine.factories.fundamental.prompt_fund import (
    CICC_STRATEGIES,
    STAGE1_SYSTEM_PROMPT_TEMPLATE,
)
from factor_engine.optimizer.fundamental.data_bridge_fund import (
    build_judge_context_fund,
    get_optimization_queue_fund,
)
from factor_engine.optimizer.fundamental.evolution_loop_fund import (
    run_evolutionary_loop_fund,
)
from factor_engine.optimizer.fundamental.llm_agents_fund import run_judge_workflow_fund
from factor_engine.optimizer.price_volume.data_bridge import extract_and_sync_genius_factors


load_dotenv_files()

PROJECT_ROOT = project_root()
DEFAULT_FIELDS_PATH = PROJECT_ROOT / "财务有效科目_大于1000.json"
DEFAULT_OUTPUT_BASE_DIR = PROJECT_ROOT / "mydata" / "output"
DEFAULT_FUND_DATA_DIR = PROJECT_ROOT / "mydata" / "fundamental_data"


def _build_chat_client(*, model_name: str) -> ChatOpenAI:
    api_key = require_env(
        "FACTOR_FACTORY_LLM_API_KEY",
        aliases=["OPENAI_API_KEY"],
        hint="set it in .env or .env.local before running fund_main.py",
    )
    base_url = get_env("FACTOR_FACTORY_LLM_BASE_URL", aliases=["OPENAI_BASE_URL"])
    timeout = get_int_env("FACTOR_FACTORY_LLM_TIMEOUT", default=120)
    max_retries = get_int_env("FACTOR_FACTORY_LLM_MAX_RETRIES", default=5)

    kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": 0,
        "max_retries": max_retries,
        "timeout": timeout,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def build_clients() -> tuple[ChatOpenAI, ChatOpenAI]:
    judge_model = get_env("FACTOR_FACTORY_FUND_JUDGE_MODEL", default="qwen3-max") or "qwen3-max"
    coder_model = get_env("FACTOR_FACTORY_FUND_CODER_MODEL", default="qwen-plus") or "qwen-plus"
    return _build_chat_client(model_name=judge_model), _build_chat_client(model_name=coder_model)


def _normalize_field_list(items):
    normalized = []
    for item in items:
        value = str(item).strip()
        if value:
            normalized.append(value)
    return sorted(set(normalized))


def load_useful_fields(path):
    if not os.path.exists(path):
        return []

    if os.path.isfile(path) and str(path).lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, list):
            return _normalize_field_list(payload)

        if isinstance(payload, dict):
            for key in ["fields", "useful_fields", "valid_fields", "items", "data"]:
                value = payload.get(key)
                if isinstance(value, list):
                    return _normalize_field_list(value)

            selected = []
            for key, value in payload.items():
                if value is True:
                    selected.append(key)
                elif isinstance(value, (int, float)) and value:
                    selected.append(key)

            if selected:
                return _normalize_field_list(selected)

        raise ValueError(f"Unsupported fields json format: {path}")

    return sorted(
        [name for name in os.listdir(path) if os.path.isdir(os.path.join(path, name))]
    )


def build_fund_config():
    run_mode = (get_env("FACTOR_FACTORY_FUND_RUN_MODE", default="test") or "test").strip().lower()
    fund_version = get_env("FACTOR_FACTORY_FUND_VERSION", default="v7") or "v7"
    test_output_folder_name = get_env(
        "FACTOR_FACTORY_FUND_TEST_OUTPUT_FOLDER_NAME",
        default="fund_factory_test",
    ) or "fund_factory_test"
    output_base_dir = Path(
        get_env(
            "FACTOR_FACTORY_FUND_OUTPUT_BASE_DIR",
            default=str(DEFAULT_OUTPUT_BASE_DIR),
        )
        or DEFAULT_OUTPUT_BASE_DIR
    )
    cache_dir_env = (
        get_env(
            "FACTOR_FACTORY_FUND_CACHE_DIR",
            default=str(PROJECT_ROOT / "runtime_cache" / "fund"),
        )
        or str(PROJECT_ROOT / "runtime_cache" / "fund")
    )
    cache_dir = Path(cache_dir_env)
    if not cache_dir.is_absolute():
        cache_dir = PROJECT_ROOT / cache_dir

    if run_mode not in {"test", "prod"}:
        raise ValueError(f"FACTOR_FACTORY_FUND_RUN_MODE must be 'test' or 'prod', got: {run_mode}")

    if run_mode == "prod":
        base_dir = output_base_dir
    else:
        base_dir = output_base_dir / test_output_folder_name

    config = FactoryConfig(
        factory_name="fund",
        version=fund_version,
        base_dir=str(base_dir),
        cache_dir=str(cache_dir),
    )
    print(f"[Fund Factory] RUN_MODE={run_mode} | output_base={base_dir}")
    print(f"[Fund Factory] Cache DB: {config.db_path}")
    print(f"[Fund Factory] Registry CSV: {config.registry_csv}")
    print(f"[Fund Factory] Premium CSV: {config.premium_registry_csv}")
    return config


def main() -> None:
    fund_config = build_fund_config()

    data_path = Path(get_env("FACTOR_FACTORY_FUND_DATA_PATH", default=str(DEFAULT_FUND_DATA_DIR)) or DEFAULT_FUND_DATA_DIR)
    fields_path = Path(get_env("FACTOR_FACTORY_FUND_FIELDS_PATH", default=str(DEFAULT_FIELDS_PATH)) or DEFAULT_FIELDS_PATH)
    base_instruction = get_env(
        "FACTOR_FACTORY_FUND_BASE_INSTRUCTION",
        default="请开始挖掘高 alpha 的基本面因子",
    ) or "请开始挖掘高 alpha 的基本面因子"
    macro_rounds = get_int_env("FACTOR_FACTORY_FUND_MACRO_ROUNDS", default=1)
    evolution_rounds = get_int_env("FACTOR_FACTORY_FUND_EVOLUTION_ROUNDS", default=3)
    enable_local_factor_save = get_bool_env("FACTOR_FACTORY_FUND_ENABLE_LOCAL_FACTOR_SAVE", default=False)

    client_judge_doctor, client_coder = build_clients()
    snapshot_days = generate_snapshot_calendar(2016, 2025)
    all_fields = load_useful_fields(str(fields_path))

    exclude_fields = {
        # "BS_TOTALDEBT",
        # "BS_STBORROW",
    }
    exclude_keywords = [
        # "DEBT",
        # "LIABILITY",
    ]
    useful_fields = [
        field
        for field in all_fields
        if field not in exclude_fields
        and not any(keyword in field for keyword in exclude_keywords)
    ]
    print(f"[Fund Factory] Excluded by exact name: {sorted(exclude_fields)}")
    print(f"[Fund Factory] Excluded by keyword: {exclude_keywords}")

    print(f"[Fund Factory] Loaded {len(useful_fields)} allowed fields from: {fields_path}")
    style_keys = list(CICC_STRATEGIES.keys())

    for round_idx in range(macro_rounds):
        current_style_name = style_keys[round_idx % len(style_keys)]
        style_info = CICC_STRATEGIES[current_style_name]

        print("\n" + "=" * 60)
        print(
            f"[Fund Factory] Round {round_idx + 1}/{macro_rounds} | style={current_style_name}"
        )
        print("=" * 60)

        style_block_content = (
            f"【本轮专项任务：{current_style_name}】\n"
            f"* 核心逻辑：{style_info['desc']}\n"
            f"* 分析思路：{style_info['logic']}\n"
        )
        current_system_prompt = STAGE1_SYSTEM_PROMPT_TEMPLATE.format(
            style_block=style_block_content
        )
        current_user_instruction = (
            f"{base_instruction}\n"
            f"【专家特别提示】为了实现“{current_style_name}”逻辑，请优先尝试组合以下字段：\n"
            f"{style_info['fields']}"
        )

        gen_job_id, llm1_text, llm3_text, gen_res_json = run_hybrid_pipeline(
            config=fund_config,
            data_folders=str(data_path),
            useful_fields=useful_fields,
            input_instruction=current_user_instruction,
            client1=client_judge_doctor,
            client2=client_coder,
            max_rounds=1,
            system_prompt=current_system_prompt,
            snapshot_days=snapshot_days,
            enable_local_factor_save=enable_local_factor_save,
        )

        if not gen_res_json or not gen_res_json.get("results"):
            print("[Warn] Fundamental generation round has no valid remote results.")
            continue

        clean_list = [clean_platform_result(item) for item in gen_res_json["results"]]
        judge_context = build_judge_context_fund(
            raw_results=gen_res_json["results"],
            clean_metrics_list=clean_list,
            llm1_raw_text=llm1_text,
            llm3_raw_text=llm3_text,
        )
        decisions = run_judge_workflow_fund(judge_context, client_judge_doctor)

        extract_and_sync_genius_factors(decisions, gen_job_id, config=fund_config)
        tag_kept_factors(decisions, gen_job_id, config=fund_config)

        opt_tasks = get_optimization_queue_fund(decisions, judge_context)
        if opt_tasks:
            print(f"[Evolution] {len(opt_tasks)} fundamental tasks enter evolution loop.")
            run_evolutionary_loop_fund(
                config=fund_config,
                initial_tasks=opt_tasks,
                client1=client_judge_doctor,
                client2=client_coder,
                data_folders=str(data_path),
                useful_fields=useful_fields,
                snapshot_days=snapshot_days,
                max_rounds=evolution_rounds,
                enable_local_factor_save=enable_local_factor_save,
            )
        else:
            print("[Evolution] No optimization candidates this round.")

    print("\n[Done] Fundamental factory macro loop finished.")


if __name__ == "__main__":
    main()
