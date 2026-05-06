import json
import os

import pandas as pd

from factor_engine.common.platform_api import EXTREME_GROUP_DAILY_TARGET
from factor_engine.common.platform_api import submit_batch_factors
from factor_engine.common.storage import (
    OptimizationStorage,
    sync_to_streamlit_registry,
    sync_to_v6_1_registry,
)
from factor_engine.factories.fundamental.local_calc_fund import (
    FactorExecutor,
    LazyFactorDB,
    generate_snapshot_calendar,
    parse_code_to_functions,
)
from factor_engine.operators.op_fundamental import OPERATOR_HEADER_STR
from factor_engine.optimizer.fundamental.llm_agents_fund import (
    run_coder_step_fund,
    run_doctor_step_fund,
)
from factor_engine.optimizer.fundamental.prompts_opt_fund import FUND_REFEREE_PROMPT


def run_evolutionary_loop_fund(
    config,
    initial_tasks,
    client1,
    client2,
    data_folders,
    useful_fields=None,
    field_governance=None,
    snapshot_days=None,
    max_rounds=3,
    enable_local_factor_save=True,
):
    if snapshot_days is None:
        snapshot_days = generate_snapshot_calendar(2016, 2025)

    current_queue = initial_tasks
    hall_of_fame = []
    storage = OptimizationStorage(config)

    db = LazyFactorDB(data_folders, snapshot_days=snapshot_days) if enable_local_factor_save else None
    executor = FactorExecutor(db) if enable_local_factor_save else None

    for round_idx in range(1, max_rounds + 1):
        round_label = f"round_{round_idx}"
        print(f"\n========== Fundamental Evolution {round_idx}/{max_rounds} ==========")

        if not current_queue:
            print("[Stop] No remaining optimization tasks.")
            break

        prescriptions = run_doctor_step_fund(current_queue, client1, round_idx)
        new_factors = run_coder_step_fund(
            prescriptions,
            client2,
            useful_fields=useful_fields,
            field_governance=field_governance,
        )
        if not new_factors:
            print(f"[Warn] No valid evolved factors generated in {round_label}.")
            continue

        storage.save_full_records(round_label, new_factors)

        batch_job_id, batch_results = submit_batch_factors(
            new_factors,
            OPERATOR_HEADER_STR,
            config.remote_result_dir,
            extra_payload={
                "need_adj": 0,
                "time_period": 10,
                "use_fundamental": 1,
                "local_data_subdir": "/财务数据/指标_v1",
            }
        )

        if batch_job_id:
            sync_to_streamlit_registry(batch_job_id, new_factors, config)

            if enable_local_factor_save:
                try:
                    batch_code_combined = "\n\n".join([f["Code"] for f in new_factors])
                    calculators = parse_code_to_functions(batch_code_combined)
                    factor_results = executor.run(calculators, code_text=batch_code_combined)

                    run_dir = os.path.join(config.factor_out_dir, str(batch_job_id))
                    os.makedirs(run_dir, exist_ok=True)

                    saved_count = 0
                    for fname, factor_data in factor_results.items():
                        if isinstance(factor_data, pd.Series):
                            save_df = factor_data.to_frame(name=fname)
                        elif isinstance(factor_data, pd.DataFrame):
                            save_df = factor_data
                        else:
                            continue

                        save_df = save_df.reset_index()
                        save_df.columns = save_df.columns.astype(str)
                        save_df.to_parquet(os.path.join(run_dir, f"{fname}.parquet"))
                        saved_count += 1
                    print(f"[Local] Saved {saved_count} evolved fundamental factors.")
                except Exception as exc:
                    print(f"[Local] Fundamental evolution local execution failed: {exc}")
            else:
                print("[Local] Skip evolved factor local execution and parquet saving.")

        next_round_queue = []
        this_round_decisions = []
        this_round_kept_factors = []

        for task in new_factors:
            f_name = task["Factor_Name"]
            child_metrics = batch_results.get(f_name)
            if not child_metrics or child_metrics.get("RankIC") == "N/A":
                continue

            parent_task = next((p for p in current_queue if p["name"] == task["Parent_Name"]), None)
            parent_ic = parent_task.get("metrics", {}).get("RankIC", 0) if parent_task else 0
            parent_icir = parent_task.get("metrics", {}).get("ICIR", 0) if parent_task else 0
            parent_pivot_count = parent_task.get("pivot_count", 0) if parent_task else 0

            parent_extreme_excess = (
                parent_task.get("metrics", {}).get("ExtremeGroupMaxExcess", 0)
                if parent_task
                else 0
            )
            parent_extreme_daily = (
                parent_task.get("metrics", {}).get("ExtremeGroupDailyExcess", 0)
                if parent_task
                else 0
            )
            child_extreme_excess = child_metrics.get("ExtremeGroupMaxExcess", 0)
            child_extreme_daily = child_metrics.get("ExtremeGroupDailyExcess", 0)

            prompt_compare = FUND_REFEREE_PROMPT.format(
                parent_name=task["Parent_Name"],
                parent_ic=parent_ic,
                parent_icir=parent_icir,
                parent_extreme_daily=parent_extreme_daily,
                parent_extreme_excess=parent_extreme_excess,
                child_name=f_name,
                child_ic=child_metrics["RankIC"],
                child_icir=child_metrics["ICIR"],
                child_extreme_daily=child_extreme_daily,
                child_extreme_excess=child_extreme_excess,
                doctor_prescription=task["Logic"],
            )

            try:
                resp = client1.invoke([{"role": "user", "content": prompt_compare}])
                content = getattr(resp, "content", str(resp))
                clean_json = content.replace("```json", "").replace("```", "").strip()
                ref_res = json.loads(clean_json)
            except Exception:
                parent_gap = abs(EXTREME_GROUP_DAILY_TARGET - float(parent_extreme_daily or 0))
                child_gap = abs(EXTREME_GROUP_DAILY_TARGET - float(child_extreme_daily or 0))
                child_hit_target = float(child_extreme_daily or 0) >= EXTREME_GROUP_DAILY_TARGET
                child_improved = child_gap < parent_gap
                ref_res = {
                    "decision": "WIN" if child_hit_target or child_improved else "LOSE",
                    "action": (
                        "KEEP"
                        if child_hit_target
                        else ("EVOLVE" if child_improved else "PIVOT")
                    ),
                    "reason": "Fallback decision based on closeness to the 0.0004 extreme-group daily target.",
                    "diagnosis": "Continue optimizing specifically for extreme-group daily excess toward 0.0004.",
                }

            this_round_decisions.append(
                {
                    "name": f_name,
                    "decision": ref_res.get("decision"),
                    "action": ref_res.get("action"),
                    "reason": ref_res.get("reason"),
                    "diagnosis": ref_res.get("diagnosis"),
                }
            )

            action = ref_res.get("action")
            if action == "KEEP":
                hall_of_fame.append({**task, "metrics": child_metrics})
                this_round_kept_factors.append(task)
            elif action == "EVOLVE":
                next_round_queue.append(
                    {
                        "name": f_name,
                        "original_logic": task["Logic"],
                        "code": task["Code"],
                        "metrics": child_metrics,
                        "diagnosis": ref_res.get("diagnosis", ""),
                        "action": "EVOLVE",
                        "pivot_count": 0,
                    }
                )
            elif action == "PIVOT" and parent_pivot_count < 1:
                next_round_queue.append(
                    {
                        "name": f_name,
                        "original_logic": task["Logic"],
                        "code": task["Code"],
                        "metrics": child_metrics,
                        "diagnosis": ref_res.get("diagnosis", ""),
                        "action": "PIVOT",
                        "pivot_count": parent_pivot_count + 1,
                    }
                )

        if this_round_kept_factors and batch_job_id:
            sync_to_v6_1_registry(batch_job_id, this_round_kept_factors, config)

        storage.save_decisions(round_label, this_round_decisions)
        current_queue = next_round_queue

    if db is not None:
        db.clear_cache()
    print(f"\n[Done] Fundamental evolution finished. Hall of fame: {len(hall_of_fame)}")
    return hall_of_fame
