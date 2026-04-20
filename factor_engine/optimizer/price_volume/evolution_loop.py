import json
import os

import pandas as pd

from factor_engine.common.platform_api import submit_batch_factors
from factor_engine.common.storage import (
    OptimizationStorage,
    sync_to_streamlit_registry,
    sync_to_v6_1_registry,
)
from factor_engine.factories.price_volume.local_calc_pv import (
    apply_matrix_calculators,
    extract_calculators_vectorized,
)
from factor_engine.operators.op_price_volume import matrix_operators, operator_lib_header
from factor_engine.optimizer.price_volume.llm_agents import run_coder_step, run_doctor_step
from factor_engine.optimizer.price_volume.prompts_opt import REFEREE_PROMPT


def run_evolutionary_loop(config, initial_tasks, client1, client2, matrix_dict, max_rounds=3):
    current_queue = initial_tasks
    hall_of_fame = []
    storage = OptimizationStorage(config)

    for round_idx in range(1, max_rounds + 1):
        round_label = f"round_{round_idx}"
        print(f"\n========== Price-Volume Evolution {round_idx}/{max_rounds} ==========")

        if not current_queue:
            print("[Stop] No remaining optimization tasks.")
            break

        prescriptions = run_doctor_step(current_queue, client1, round_idx)
        new_factors = run_coder_step(prescriptions, client2)
        if not new_factors:
            print(f"[Warn] No valid evolved factors generated in {round_label}.")
            continue

        storage.save_full_records(round_label, new_factors)
        batch_job_id, batch_results = submit_batch_factors(new_factors, operator_lib_header)

        if batch_job_id:
            sync_to_streamlit_registry(batch_job_id, new_factors, config)

            print(f"[Local] Computing factor entities for batch {batch_job_id} ...")
            try:
                batch_code_text = "\n\n".join([factor["Code"] for factor in new_factors])
                calculators = extract_calculators_vectorized(batch_code_text, matrix_operators())
                factor_results = apply_matrix_calculators(matrix_dict, calculators)

                run_dir = os.path.join(config.factor_out_dir, str(batch_job_id))
                os.makedirs(run_dir, exist_ok=True)

                saved_count = 0
                for factor_name, factor_df in factor_results.items():
                    if not isinstance(factor_df, pd.DataFrame):
                        continue
                    save_df = factor_df.reset_index()
                    save_df.columns = save_df.columns.astype(str)
                    save_df.to_parquet(os.path.join(run_dir, f"{factor_name}.parquet"))
                    saved_count += 1

                print(f"[Local] Saved {saved_count} evolved factor parquet files to {run_dir}")
            except Exception as exc:
                print(f"[Local] Local factor computation/save failed: {exc}")

        print("[LLM4] Reviewing evolved factors...")
        next_round_queue = []
        this_round_decisions = []
        this_round_kept_factors = []

        for task in new_factors:
            factor_name = task["Factor_Name"]
            child_metrics = batch_results.get(factor_name)
            if not child_metrics or child_metrics.get("RankIC") == "N/A":
                continue

            parent_task = next((item for item in current_queue if item["name"] == task["Parent_Name"]), None)
            parent_ic = parent_task.get("metrics", {}).get("RankIC", 0) if parent_task else 0
            parent_icir = parent_task.get("metrics", {}).get("ICIR", 0) if parent_task else 0
            parent_pivot_count = parent_task.get("pivot_count", 0) if parent_task else 0

            prompt_compare = REFEREE_PROMPT.format(
                parent_name=task["Parent_Name"],
                parent_ic=parent_ic,
                parent_icir=parent_icir,
                parent_turnover="N/A",
                child_name=factor_name,
                child_ic=child_metrics["RankIC"],
                child_icir=child_metrics["ICIR"],
                child_turnover="N/A",
                doctor_prescription=task["Logic"],
            )

            try:
                resp = client1.invoke([{"role": "user", "content": prompt_compare}])
                content = getattr(resp, "content", str(resp))
                clean_json = content.replace("```json", "").replace("```", "").strip()
                ref_res = json.loads(clean_json)
            except Exception as exc:
                print(f"[LLM4] Referee failed, using fallback: {exc}")
                ref_res = {
                    "decision": "WIN"
                    if abs(float(child_metrics.get("RankIC", 0))) > abs(float(parent_ic))
                    else "LOSE",
                    "action": "EVOLVE"
                    if abs(float(child_metrics.get("RankIC", 0))) > 0.01
                    else "TERMINATE",
                    "reason": "Fallback numeric referee decision.",
                    "diagnosis": "Continue strengthening the current signal direction.",
                }

            this_round_decisions.append(
                {
                    "name": factor_name,
                    "decision": ref_res.get("decision"),
                    "action": ref_res.get("action"),
                    "reason": ref_res.get("reason"),
                    "diagnosis": ref_res.get("diagnosis"),
                }
            )

            action = ref_res.get("action")
            ic_val = abs(float(child_metrics.get("RankIC", 0)))
            icir_val = abs(float(child_metrics.get("ICIR", 0)))

            if action == "KEEP":
                print(f"[Keep] {factor_name} (IC={ic_val:.4f}, ICIR={icir_val:.2f})")
                hall_of_fame.append({**task, "metrics": child_metrics})
                this_round_kept_factors.append(task)
            elif action == "EVOLVE":
                print(f"[Evolve] {factor_name} enters next round.")
                next_round_queue.append(
                    {
                        "name": factor_name,
                        "original_logic": task["Logic"],
                        "code": task["Code"],
                        "metrics": child_metrics,
                        "diagnosis": ref_res.get("diagnosis", "Continue along the current direction."),
                        "action": "EVOLVE",
                        "pivot_count": 0,
                    }
                )
            elif action == "PIVOT":
                if ic_val >= 0.005:
                    if parent_pivot_count >= 1:
                        print(f"[Terminate] {factor_name} exhausted after repeated pivot.")
                    else:
                        print(f"[Pivot] {factor_name} gets one final structural pivot.")
                        next_round_queue.append(
                            {
                                "name": factor_name,
                                "original_logic": task["Logic"],
                                "code": task["Code"],
                                "metrics": child_metrics,
                                "diagnosis": ref_res.get(
                                    "diagnosis",
                                    "Current direction failed, switch to a new mathematical structure.",
                                ),
                                "action": "PIVOT",
                                "pivot_count": parent_pivot_count + 1,
                            }
                        )
                else:
                    print(f"[Terminate] {factor_name} too weak to justify pivot (IC={ic_val:.4f}).")
            else:
                print(f"[Terminate] {factor_name} dropped: {ref_res.get('reason')}")

        if this_round_kept_factors and batch_job_id:
            sync_to_v6_1_registry(batch_job_id, this_round_kept_factors, config)

        storage.save_decisions(round_label, this_round_decisions)
        current_queue = next_round_queue

    print(f"\n[Done] Price-volume evolution finished. Hall of fame: {len(hall_of_fame)}")
    return hall_of_fame
