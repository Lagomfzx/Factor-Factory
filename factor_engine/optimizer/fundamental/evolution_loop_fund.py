import json
import os

import pandas as pd

from factor_engine.common.platform_api import (
    FUND_LONG_NEGATIVE_DAILY_TARGET_ABS,
    FUND_LONG_POSITIVE_DAILY_FLOOR,
    FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS,
    FUND_RECENT_POSITIVE_DAILY_TARGET,
    submit_batch_factors,
)
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


def _metric_float(metrics, key, default=0.0):
    try:
        return float(metrics.get(key, default) or default)
    except Exception:
        return default


def _metric_bool(metrics, key, default=False):
    value = metrics.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


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

        prescriptions = run_doctor_step_fund(
            current_queue,
            client1,
            round_idx,
            useful_fields=useful_fields,
            field_governance=field_governance,
        )
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
            parent_metrics = parent_task.get("metrics", {}) if parent_task else {}
            parent_ic = parent_metrics.get("RankIC", 0)
            parent_icir = parent_metrics.get("ICIR", 0)
            parent_pivot_count = parent_task.get("pivot_count", 0) if parent_task else 0

            parent_best_side = parent_metrics.get("BestExtremeSide", "UNKNOWN")
            parent_top_daily = _metric_float(parent_metrics, "TopGroupDailyRet")
            parent_bottom_daily = _metric_float(parent_metrics, "BottomGroupDailyRet")
            parent_positive_daily = _metric_float(parent_metrics, "PositiveAlphaDaily")
            parent_negative_abs = _metric_float(parent_metrics, "NegativeAlphaDailyAbs")
            parent_recent_years = parent_metrics.get("RecentYears", [])
            parent_recent_positive_daily = _metric_float(parent_metrics, "RecentPositiveAlphaDaily")
            parent_recent_negative_abs = _metric_float(parent_metrics, "RecentNegativeAlphaAbs")
            parent_recent_positive_all = _metric_bool(parent_metrics, "RecentPositiveAllPositive")
            parent_recent_negative_all = _metric_bool(parent_metrics, "RecentNegativeAllNegative")
            parent_extreme_excess = _metric_float(parent_metrics, "ExtremeGroupMaxExcess")
            parent_extreme_daily = _metric_float(parent_metrics, "ExtremeGroupDailyExcess")

            child_best_side = child_metrics.get("BestExtremeSide", "UNKNOWN")
            child_top_daily = _metric_float(child_metrics, "TopGroupDailyRet")
            child_bottom_daily = _metric_float(child_metrics, "BottomGroupDailyRet")
            child_positive_daily = _metric_float(child_metrics, "PositiveAlphaDaily")
            child_negative_abs = _metric_float(child_metrics, "NegativeAlphaDailyAbs")
            child_recent_years = child_metrics.get("RecentYears", [])
            child_recent_positive_daily = _metric_float(child_metrics, "RecentPositiveAlphaDaily")
            child_recent_negative_abs = _metric_float(child_metrics, "RecentNegativeAlphaAbs")
            child_recent_positive_all = _metric_bool(child_metrics, "RecentPositiveAllPositive")
            child_recent_negative_all = _metric_bool(child_metrics, "RecentNegativeAllNegative")
            child_extreme_excess = _metric_float(child_metrics, "ExtremeGroupMaxExcess")
            child_extreme_daily = _metric_float(child_metrics, "ExtremeGroupDailyExcess")

            prompt_compare = FUND_REFEREE_PROMPT.format(
                parent_name=task["Parent_Name"],
                parent_ic=parent_ic,
                parent_icir=parent_icir,
                parent_best_side=parent_best_side,
                parent_top_daily=parent_top_daily,
                parent_bottom_daily=parent_bottom_daily,
                parent_positive_daily=parent_positive_daily,
                parent_negative_abs=parent_negative_abs,
                parent_recent_years=parent_recent_years,
                parent_recent_positive_daily=parent_recent_positive_daily,
                parent_recent_negative_abs=parent_recent_negative_abs,
                parent_recent_positive_all=parent_recent_positive_all,
                parent_recent_negative_all=parent_recent_negative_all,
                parent_extreme_daily=parent_extreme_daily,
                parent_extreme_excess=parent_extreme_excess,
                child_name=f_name,
                child_ic=child_metrics["RankIC"],
                child_icir=child_metrics["ICIR"],
                child_best_side=child_best_side,
                child_top_daily=child_top_daily,
                child_bottom_daily=child_bottom_daily,
                child_positive_daily=child_positive_daily,
                child_negative_abs=child_negative_abs,
                child_recent_years=child_recent_years,
                child_recent_positive_daily=child_recent_positive_daily,
                child_recent_negative_abs=child_recent_negative_abs,
                child_recent_positive_all=child_recent_positive_all,
                child_recent_negative_all=child_recent_negative_all,
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
                parent_positive_gap = abs(FUND_LONG_POSITIVE_DAILY_FLOOR - parent_positive_daily)
                child_positive_gap = abs(FUND_LONG_POSITIVE_DAILY_FLOOR - child_positive_daily)
                parent_recent_positive_gap = abs(
                    FUND_RECENT_POSITIVE_DAILY_TARGET - parent_recent_positive_daily
                )
                child_recent_positive_gap = abs(
                    FUND_RECENT_POSITIVE_DAILY_TARGET - child_recent_positive_daily
                )
                parent_negative_gap = abs(FUND_LONG_NEGATIVE_DAILY_TARGET_ABS - parent_negative_abs)
                child_negative_gap = abs(FUND_LONG_NEGATIVE_DAILY_TARGET_ABS - child_negative_abs)
                parent_recent_negative_gap = abs(
                    FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS - parent_recent_negative_abs
                )
                child_recent_negative_gap = abs(
                    FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS - child_recent_negative_abs
                )
                child_hit_positive = (
                    child_positive_daily >= FUND_LONG_POSITIVE_DAILY_FLOOR
                    and child_recent_positive_all
                    and child_recent_positive_daily >= FUND_RECENT_POSITIVE_DAILY_TARGET
                    and (
                        child_positive_daily >= parent_positive_daily
                        or child_recent_positive_daily >= parent_recent_positive_daily
                    )
                )
                child_improved_positive = (
                    child_positive_daily > parent_positive_daily
                    or (child_recent_positive_all and child_recent_positive_daily > parent_recent_positive_daily)
                    or (
                        parent_positive_daily < FUND_LONG_POSITIVE_DAILY_FLOOR
                        and child_positive_gap < parent_positive_gap
                    )
                    or (
                        child_recent_positive_all
                        and parent_recent_positive_daily < FUND_RECENT_POSITIVE_DAILY_TARGET
                        and child_recent_positive_gap < parent_recent_positive_gap
                    )
                )
                child_hit_negative = (
                    child_negative_abs >= FUND_LONG_NEGATIVE_DAILY_TARGET_ABS
                    and child_recent_negative_all
                    and child_recent_negative_abs >= FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS
                    and (
                        child_negative_abs >= parent_negative_abs
                        or child_recent_negative_abs >= parent_recent_negative_abs
                    )
                )
                child_improved_negative = (
                    child_negative_abs > parent_negative_abs
                    or (child_recent_negative_all and child_recent_negative_abs > parent_recent_negative_abs)
                    or (
                        parent_negative_abs < FUND_LONG_NEGATIVE_DAILY_TARGET_ABS
                        and child_negative_gap < parent_negative_gap
                    )
                    or (
                        child_recent_negative_all
                        and parent_recent_negative_abs < FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS
                        and child_recent_negative_gap < parent_recent_negative_gap
                    )
                )
                child_has_progress = (
                    child_hit_positive
                    or child_improved_positive
                    or child_hit_negative
                    or child_improved_negative
                )
                ref_res = {
                    "decision": "WIN" if child_has_progress else "LOSE",
                    "action": (
                        "KEEP"
                        if child_hit_positive
                        else ("EVOLVE" if child_has_progress else "PIVOT")
                    ),
                    "reason": (
                        "Fallback decision prioritizes long-horizon positive floor 0.0002 "
                        "plus recent positive persistence near 0.0004; negative factors require "
                        "long-horizon -0.0004 and recent -0.0006 style tail evidence."
                    ),
                    "diagnosis": (
                        "Continue optimizing for a simple positive fundamental alpha: "
                        "first clear the long-horizon 0.0002 floor, then make recent high-group "
                        "returns persistently positive and close to 0.0004. Only keep negative-tail "
                        "direction if the logic is explicitly risk/removal and recent downside persists."
                    ),
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
