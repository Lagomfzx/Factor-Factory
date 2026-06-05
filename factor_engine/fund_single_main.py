from __future__ import annotations

import traceback
from pathlib import Path

from factor_engine.common.config import FactoryConfig
from factor_engine.common.runtime_env import (
    get_bool_env,
    get_env,
    get_int_env,
    load_dotenv_files,
    project_root,
)
from factor_engine.factories.fundamental.field_governance import (
    load_field_governance,
    save_field_governance_snapshot,
    summarize_field_governance,
)
from factor_engine.factories.fundamental.local_calc_fund import generate_snapshot_calendar
from factor_engine.factories.fundamental_single_metric.field_cards import (
    build_field_cards,
    filter_field_cards,
    load_field_cards,
    save_field_cards,
)
from factor_engine.factories.fundamental_single_metric.pipeline_fund_single import (
    run_single_metric_pipeline,
)
from factor_engine.factories.fundamental_single_metric.prompt_fund_single import (
    STAGE1_SYSTEM_PROMPT_TEMPLATE,
    build_target_field_instruction,
)
from factor_engine.fund_main import _build_chat_client, load_useful_fields


load_dotenv_files()

PROJECT_ROOT = project_root()
DEFAULT_FIELDS_PATH = PROJECT_ROOT / "财务有效科目_大于1000.json"
DEFAULT_OUTPUT_BASE_DIR = PROJECT_ROOT / "mydata" / "output"
DEFAULT_FUND_DATA_DIR = PROJECT_ROOT / "mydata" / "fundamental_data"
DEFAULT_FIELD_CARDS_PATH = (
    PROJECT_ROOT
    / "factor_engine"
    / "prompt_assets"
    / "factories"
    / "fundamental_single_metric"
    / "field_cards.json"
)


def _console_safe(value) -> str:
    text = str(value)
    return text.encode("gbk", errors="backslashreplace").decode("gbk")


def build_fund_single_config():
    run_mode = (
        get_env("FACTOR_FACTORY_FUND_SINGLE_RUN_MODE", default="test") or "test"
    ).strip().lower()
    version = get_env("FACTOR_FACTORY_FUND_SINGLE_VERSION", default="v8") or "v8"
    test_output_folder_name = (
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_TEST_OUTPUT_FOLDER_NAME",
            default="fund_single_metric_test",
        )
        or "fund_single_metric_test"
    )
    output_base_dir = Path(
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_OUTPUT_BASE_DIR",
            default=str(DEFAULT_OUTPUT_BASE_DIR),
        )
        or DEFAULT_OUTPUT_BASE_DIR
    )
    cache_dir = Path(
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_CACHE_DIR",
            default=str(PROJECT_ROOT / "runtime_cache" / "fund_single_metric"),
        )
        or str(PROJECT_ROOT / "runtime_cache" / "fund_single_metric")
    )
    if not cache_dir.is_absolute():
        cache_dir = PROJECT_ROOT / cache_dir

    if run_mode not in {"test", "prod"}:
        raise ValueError(
            "FACTOR_FACTORY_FUND_SINGLE_RUN_MODE must be 'test' or 'prod', "
            f"got: {run_mode}"
        )

    base_dir = output_base_dir if run_mode == "prod" else output_base_dir / test_output_folder_name
    config = FactoryConfig(
        factory_name="fund_single_metric",
        version=version,
        base_dir=str(base_dir),
        cache_dir=str(cache_dir),
    )
    print(f"[Fund Single Factory] RUN_MODE={run_mode} | output_base={_console_safe(base_dir)}")
    print(f"[Fund Single Factory] Version={config.version}")
    print(f"[Fund Single Factory] LLM output dir: {_console_safe(config.llm_output_dir)}")
    print(f"[Fund Single Factory] Factor output dir: {_console_safe(config.factor_out_dir)}")
    print(f"[Fund Single Factory] Remote result dir: {_console_safe(config.remote_result_dir)}")
    print(f"[Fund Single Factory] Cache DB: {_console_safe(config.db_path)}")
    print(f"[Fund Single Factory] Registry CSV: {_console_safe(config.registry_csv)}")
    print(
        "[Fund Single Factory] Field governance JSON: "
        f"{_console_safe(config.field_governance_json)}"
    )
    return config


def _parse_target_fields(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _is_all_target_fields(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"all", "*", "__all__"}


def build_single_clients():
    judge_model = (
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_JUDGE_MODEL",
            aliases=["FACTOR_FACTORY_FUND_JUDGE_MODEL"],
            default="qwen3-max",
        )
        or "qwen3-max"
    )
    coder_model = (
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_CODER_MODEL",
            aliases=["FACTOR_FACTORY_FUND_CODER_MODEL"],
            default="qwen-plus",
        )
        or "qwen-plus"
    )
    print(f"[Fund Single Factory] Judge model: {judge_model}")
    print(f"[Fund Single Factory] Coder model: {coder_model}")
    return _build_chat_client(model_name=judge_model), _build_chat_client(model_name=coder_model)


def main() -> None:
    config = build_fund_single_config()

    data_path = Path(
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_DATA_PATH",
            aliases=["FACTOR_FACTORY_FUND_DATA_PATH"],
            default=str(DEFAULT_FUND_DATA_DIR),
        )
        or DEFAULT_FUND_DATA_DIR
    )
    fields_path = Path(
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_FIELDS_PATH",
            aliases=["FACTOR_FACTORY_FUND_FIELDS_PATH"],
            default=str(DEFAULT_FIELDS_PATH),
        )
        or DEFAULT_FIELDS_PATH
    )
    governance_path_env = (
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_GOVERNANCE_PATH",
            aliases=["FACTOR_FACTORY_FUND_GOVERNANCE_PATH"],
            default="",
        )
        or ""
    )
    target_fields_raw = (
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_TARGET_FIELDS",
            default="IS_OPERATINGREVENUE",
        )
        or "IS_OPERATINGREVENUE"
    )
    field_cards_path = Path(
        get_env(
            "FACTOR_FACTORY_FUND_SINGLE_FIELD_CARDS_PATH",
            default=str(DEFAULT_FIELD_CARDS_PATH),
        )
        or DEFAULT_FIELD_CARDS_PATH
    )
    if not field_cards_path.is_absolute():
        field_cards_path = PROJECT_ROOT / field_cards_path
    auto_generate_cards = get_bool_env(
        "FACTOR_FACTORY_FUND_SINGLE_AUTOGENERATE_FIELD_CARDS",
        default=False,
    )
    max_target_fields = get_int_env("FACTOR_FACTORY_FUND_SINGLE_MAX_TARGET_FIELDS", default=1)
    continue_on_error = get_bool_env(
        "FACTOR_FACTORY_FUND_SINGLE_CONTINUE_ON_ERROR",
        default=True,
    )
    enable_local_factor_save = get_bool_env(
        "FACTOR_FACTORY_FUND_SINGLE_ENABLE_LOCAL_FACTOR_SAVE",
        default=False,
    )
    use_history_context = get_bool_env(
        "FACTOR_FACTORY_FUND_SINGLE_USE_HISTORY_CONTEXT",
        default=True,
    )
    history_max_rounds = get_int_env(
        "FACTOR_FACTORY_FUND_SINGLE_HISTORY_MAX_ROUNDS",
        default=10,
    )

    client_judge_doctor, client_coder = build_single_clients()
    snapshot_days = generate_snapshot_calendar(2016, 2025)
    all_fields = load_useful_fields(str(fields_path))

    governance_path = None
    if governance_path_env:
        governance_path = Path(governance_path_env)
        if not governance_path.is_absolute():
            governance_path = PROJECT_ROOT / governance_path

    field_governance = load_field_governance(
        useful_fields=all_fields,
        path=governance_path,
    )
    useful_fields = field_governance["allowed_fields"]
    save_field_governance_snapshot(field_governance, config.field_governance_json)

    print(f"[Fund Single Factory] Loaded {len(all_fields)} raw fields from: {fields_path}")
    print(
        "[Fund Single Factory] Governance source: "
        f"{field_governance['source_path'] or 'default-auto'}"
    )
    print(
        "[Fund Single Factory] Governance summary: "
        f"{summarize_field_governance(field_governance)}"
    )

    if auto_generate_cards or not field_cards_path.exists():
        cards = build_field_cards(useful_fields, field_governance)
        save_field_cards(cards, field_cards_path)
        print(
            "[Fund Single Factory] Field cards generated: "
            f"{len(cards)} -> {_console_safe(field_cards_path)}"
        )

    field_cards = load_field_cards(field_cards_path)
    print(
        "[Fund Single Factory] Field cards loaded: "
        f"{len(field_cards)} <- {_console_safe(field_cards_path)}"
    )

    target_fields = (
        None
        if _is_all_target_fields(target_fields_raw)
        else _parse_target_fields(target_fields_raw)
    )
    selected_cards = filter_field_cards(
        field_cards,
        target_fields=target_fields,
        allowed_fields=set(useful_fields),
    )
    available_cards = len(selected_cards)
    if max_target_fields > 0:
        selected_cards = selected_cards[:max_target_fields]

    if not selected_cards:
        raise ValueError(
            "No valid target field cards. Check FACTOR_FACTORY_FUND_SINGLE_FIELD_CARDS_PATH "
            "and FACTOR_FACTORY_FUND_SINGLE_TARGET_FIELDS."
        )
    print(
        "[Fund Single Factory] Batch selection: "
        f"target_mode={'ALL' if target_fields is None else 'LIST'} | "
        f"available={available_cards} | "
        f"limit={max_target_fields if max_target_fields > 0 else 'ALL'} | "
        f"selected={len(selected_cards)} | continue_on_error={continue_on_error}"
    )

    for round_idx, field_card in enumerate(selected_cards, start=1):
        target_field = str(field_card["field"])
        print("\n" + "=" * 60)
        print(
            f"[Fund Single Factory] Target {round_idx}/{len(selected_cards)} | "
            f"field={target_field}"
        )
        print("=" * 60)

        input_instruction = build_target_field_instruction(
            target_field,
            field_governance=field_governance,
            field_card=field_card,
        )
        current_system_prompt = STAGE1_SYSTEM_PROMPT_TEMPLATE.format(style_block="")

        try:
            run_single_metric_pipeline(
                config=config,
                data_folders=str(data_path),
                useful_fields=useful_fields,
                field_governance=field_governance,
                input_instruction=input_instruction,
                client1=client_judge_doctor,
                client2=client_coder,
                max_rounds=1,
                system_prompt=current_system_prompt,
                snapshot_days=snapshot_days,
                enable_local_factor_save=enable_local_factor_save,
                use_history_context=use_history_context,
                history_max_rounds=history_max_rounds,
            )
        except Exception as exc:
            print(
                "[Fund Single Factory] Target failed | "
                f"field={target_field} | {exc.__class__.__name__}: {exc}"
            )
            print(traceback.format_exc(limit=8))
            if not continue_on_error:
                raise

    print("\n[Done] Fundamental single-metric factory finished.")


if __name__ == "__main__":
    main()
