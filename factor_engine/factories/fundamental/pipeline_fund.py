import os
from datetime import datetime

import pandas as pd

from factor_engine.common.history import load_factor_history
from factor_engine.common.platform_api import submit_to_platform, wait_and_save_remote_result
from factor_engine.common.runtime_env import get_platform_url, load_dotenv_files
from factor_engine.common.storage import index_and_save_job_details
from factor_engine.factories.fundamental.llm_chain_fund import run_three_stages_with_memory
from factor_engine.factories.fundamental.local_calc_fund import (
    FactorExecutor,
    LazyFactorDB,
    generate_snapshot_calendar,
    parse_code_to_functions,
)
from factor_engine.operators.op_fundamental import OPERATOR_HEADER_STR


load_dotenv_files()


def pack_code_for_remote(operator_header, code_text):
    return operator_header + "\n\n" + code_text


def run_hybrid_pipeline(
    config,
    data_folders,
    useful_fields,
    field_governance,
    input_instruction,
    client1,
    client2,
    max_rounds=1,
    system_prompt=None,
    snapshot_days=None,
    enable_local_factor_save=True,
):
    """
    Financial-factor generation pipeline aligned to the validated notebook.
    Returns the final round's remote job id, design text, code text, and remote json.
    """
    if snapshot_days is None:
        snapshot_days = generate_snapshot_calendar(2016, 2025)
    remote_url = get_platform_url()

    print(f"[Init] Fundamental factory booting with data: {data_folders}")
    db = LazyFactorDB(data_folders, snapshot_days=snapshot_days)
    executor = FactorExecutor(db) if enable_local_factor_save else None
    all_fields = useful_fields or list(db.keys())
    print(f"[Init] {len(all_fields)} usable fundamental fields loaded.")

    last_job_id = None
    last_design_text = ""
    last_code_text = ""
    last_res_json = None

    for round_i in range(max_rounds):
        print(f"\n[Hybrid Round {round_i + 1}/{max_rounds}] Starting...")
        history_text = load_factor_history(config, max_rounds=10)

        print("[Brain] Generating factor logic and code...")
        code_text, design_text = run_three_stages_with_memory(
            config=config,
            client1=client1,
            client2=client2,
            history_text=history_text,
            all_fields=all_fields,
            extra_instruction=input_instruction,
            system_prompt=system_prompt,
            field_governance=field_governance,
        )

        if not code_text or not design_text:
            print("[Warn] Fundamental generation returned empty output. Skipping round.")
            continue

        print("[Remote] Submitting fundamental batch to platform...")
        final_py_code = pack_code_for_remote(OPERATOR_HEADER_STR, code_text)
        current_job_id = submit_to_platform(
            py_code=final_py_code,
            explain_text=design_text,
            url=remote_url,
            extra_payload={"use_fundamental": 1},
        )

        if current_job_id:
            index_and_save_job_details(current_job_id, design_text, code_text, config)

        if enable_local_factor_save:
            print("[Local] Running validated notebook-style local execution...")
            round_dir_name = (
                str(current_job_id)
                if current_job_id
                else f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            local_save_dir = os.path.join(config.factor_out_dir, round_dir_name)
            os.makedirs(local_save_dir, exist_ok=True)

            calculators = parse_code_to_functions(code_text)
            if calculators:
                valid_factor_names = {
                    name.replace("calculate_", "") for name in calculators.keys()
                }
                try:
                    results = executor.run(calculators, code_text=code_text)
                    saved_count = 0
                    for factor_name, factor_data in results.items():
                        if factor_name not in valid_factor_names:
                            continue
                        save_path = os.path.join(local_save_dir, f"{factor_name}.parquet")
                        if isinstance(factor_data, pd.DataFrame):
                            factor_data.to_parquet(save_path)
                            saved_count += 1
                        elif isinstance(factor_data, pd.Series):
                            factor_data.to_frame(name=factor_name).to_parquet(save_path)
                            saved_count += 1
                    print(f"[Local] Saved {saved_count} fundamental factors to {local_save_dir}")
                except Exception as exc:
                    print(f"[Local] Fundamental execution failed: {exc}")
            else:
                print("[Local] No valid calculators were parsed from generated code.")
        else:
            print("[Local] Skip notebook-style local execution and parquet saving.")

        res_json = None
        if current_job_id:
            remote_file_name = f"{datetime.now():%Y%m%d_%H%M%S}_{current_job_id}.json"
            remote_save_path = os.path.join(config.remote_result_dir, remote_file_name)
            res_json = wait_and_save_remote_result(
                base_url=remote_url,
                job_id=current_job_id,
                save_path=remote_save_path,
            )

        db.clear_cache()

        last_job_id = current_job_id
        last_design_text = design_text
        last_code_text = code_text
        last_res_json = res_json

    return last_job_id, last_design_text, last_code_text, last_res_json
