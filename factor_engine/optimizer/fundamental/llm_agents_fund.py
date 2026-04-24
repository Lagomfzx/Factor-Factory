# import json
# import os

# import pandas as pd

# from factor_engine.common.platform_api import EXTREME_GROUP_DAILY_TARGET
# from factor_engine.common.platform_api import submit_batch_factors
# from factor_engine.common.storage import (
#     OptimizationStorage,
#     sync_to_streamlit_registry,
#     sync_to_v6_1_registry,
# )
# from factor_engine.factories.fundamental.local_calc_fund import (
#     FactorExecutor,
#     LazyFactorDB,
#     generate_snapshot_calendar,
#     parse_code_to_functions,
# )
# from factor_engine.operators.op_fundamental import OPERATOR_HEADER_STR
# from factor_engine.optimizer.fundamental.llm_agents_fund import (
#     run_coder_step_fund,
#     run_doctor_step_fund,
# )
# from factor_engine.optimizer.fundamental.prompts_opt_fund import FUND_REFEREE_PROMPT


# def run_evolutionary_loop_fund(
#     config,
#     initial_tasks,
#     client1,
#     client2,
#     data_folders,
#     useful_fields=None,
#     snapshot_days=None,
#     max_rounds=3,
#     enable_local_factor_save=True,
# ):
#     if snapshot_days is None:
#         snapshot_days = generate_snapshot_calendar(2016, 2025)

#     current_queue = initial_tasks
#     hall_of_fame = []
#     storage = OptimizationStorage(config)

#     db = LazyFactorDB(data_folders, snapshot_days=snapshot_days) if enable_local_factor_save else None
#     executor = FactorExecutor(db) if enable_local_factor_save else None

#     for round_idx in range(1, max_rounds + 1):
#         round_label = f"round_{round_idx}"
#         print(f"\n========== Fundamental Evolution {round_idx}/{max_rounds} ==========")

#         if not current_queue:
#             print("[Stop] No remaining optimization tasks.")
#             break

#         prescriptions = run_doctor_step_fund(current_queue, client1, round_idx)
#         new_factors = run_coder_step_fund(
#             prescriptions,
#             client2,
#             useful_fields=useful_fields,
#         )
#         if not new_factors:
#             print(f"[Warn] No valid evolved factors generated in {round_label}.")
#             continue

#         storage.save_full_records(round_label, new_factors)

#         batch_job_id, batch_results = submit_batch_factors(
#             new_factors,
#             OPERATOR_HEADER_STR,
#             config.remote_result_dir,
#             extra_payload={"use_fundamental": 1},
#         )

#         if batch_job_id:
#             sync_to_streamlit_registry(batch_job_id, new_factors, config)

#             if enable_local_factor_save:
#                 try:
#                     batch_code_combined = "\n\n".join([f["Code"] for f in new_factors])
#                     calculators = parse_code_to_functions(batch_code_combined)
#                     factor_results = executor.run(calculators, code_text=batch_code_combined)

#                     run_dir = os.path.join(config.factor_out_dir, str(batch_job_id))
#                     os.makedirs(run_dir, exist_ok=True)

#                     saved_count = 0
#                     for fname, factor_data in factor_results.items():
#                         if isinstance(factor_data, pd.Series):
#                             save_df = factor_data.to_frame(name=fname)
#                         elif isinstance(factor_data, pd.DataFrame):
#                             save_df = factor_data
#                         else:
#                             continue

#                         save_df = save_df.reset_index()
#                         save_df.columns = save_df.columns.astype(str)
#                         save_df.to_parquet(os.path.join(run_dir, f"{fname}.parquet"))
#                         saved_count += 1
#                     print(f"[Local] Saved {saved_count} evolved fundamental factors.")
#                 except Exception as exc:
#                     print(f"[Local] Fundamental evolution local execution failed: {exc}")
#             else:
#                 print("[Local] Skip evolved factor local execution and parquet saving.")

#         next_round_queue = []
#         this_round_decisions = []
#         this_round_kept_factors = []

#         for task in new_factors:
#             f_name = task["Factor_Name"]
#             child_metrics = batch_results.get(f_name)
#             if not child_metrics or child_metrics.get("RankIC") == "N/A":
#                 continue

#             parent_task = next((p for p in current_queue if p["name"] == task["Parent_Name"]), None)
#             parent_ic = parent_task.get("metrics", {}).get("RankIC", 0) if parent_task else 0
#             parent_icir = parent_task.get("metrics", {}).get("ICIR", 0) if parent_task else 0
#             parent_pivot_count = parent_task.get("pivot_count", 0) if parent_task else 0

#             parent_extreme_excess = (
#                 parent_task.get("metrics", {}).get("ExtremeGroupMaxExcess", 0)
#                 if parent_task
#                 else 0
#             )
#             parent_extreme_daily = (
#                 parent_task.get("metrics", {}).get("ExtremeGroupDailyExcess", 0)
#                 if parent_task
#                 else 0
#             )
#             child_extreme_excess = child_metrics.get("ExtremeGroupMaxExcess", 0)
#             child_extreme_daily = child_metrics.get("ExtremeGroupDailyExcess", 0)

#             prompt_compare = FUND_REFEREE_PROMPT.format(
#                 parent_name=task["Parent_Name"],
#                 parent_ic=parent_ic,
#                 parent_icir=parent_icir,
#                 parent_extreme_daily=parent_extreme_daily,
#                 parent_extreme_excess=parent_extreme_excess,
#                 child_name=f_name,
#                 child_ic=child_metrics["RankIC"],
#                 child_icir=child_metrics["ICIR"],
#                 child_extreme_daily=child_extreme_daily,
#                 child_extreme_excess=child_extreme_excess,
#                 doctor_prescription=task["Logic"],
#             )

#             try:
#                 resp = client1.invoke([{"role": "user", "content": prompt_compare}])
#                 content = getattr(resp, "content", str(resp))
#                 clean_json = content.replace("```json", "").replace("```", "").strip()
#                 ref_res = json.loads(clean_json)
#             except Exception:
#                 parent_gap = abs(EXTREME_GROUP_DAILY_TARGET - float(parent_extreme_daily or 0))
#                 child_gap = abs(EXTREME_GROUP_DAILY_TARGET - float(child_extreme_daily or 0))
#                 child_hit_target = float(child_extreme_daily or 0) >= EXTREME_GROUP_DAILY_TARGET
#                 child_improved = child_gap < parent_gap
#                 ref_res = {
#                     "decision": "WIN" if child_hit_target or child_improved else "LOSE",
#                     "action": (
#                         "KEEP"
#                         if child_hit_target
#                         else ("EVOLVE" if child_improved else "PIVOT")
#                     ),
#                     "reason": "Fallback decision based on closeness to the 0.0004 extreme-group daily target.",
#                     "diagnosis": "Continue optimizing specifically for extreme-group daily excess toward 0.0004.",
#                 }

#             this_round_decisions.append(
#                 {
#                     "name": f_name,
#                     "decision": ref_res.get("decision"),
#                     "action": ref_res.get("action"),
#                     "reason": ref_res.get("reason"),
#                     "diagnosis": ref_res.get("diagnosis"),
#                 }
#             )

#             action = ref_res.get("action")
#             if action == "KEEP":
#                 hall_of_fame.append({**task, "metrics": child_metrics})
#                 this_round_kept_factors.append(task)
#             elif action == "EVOLVE":
#                 next_round_queue.append(
#                     {
#                         "name": f_name,
#                         "original_logic": task["Logic"],
#                         "code": task["Code"],
#                         "metrics": child_metrics,
#                         "diagnosis": ref_res.get("diagnosis", ""),
#                         "action": "EVOLVE",
#                         "pivot_count": 0,
#                     }
#                 )
#             elif action == "PIVOT" and parent_pivot_count < 1:
#                 next_round_queue.append(
#                     {
#                         "name": f_name,
#                         "original_logic": task["Logic"],
#                         "code": task["Code"],
#                         "metrics": child_metrics,
#                         "diagnosis": ref_res.get("diagnosis", ""),
#                         "action": "PIVOT",
#                         "pivot_count": parent_pivot_count + 1,
#                     }
#                 )

#         if this_round_kept_factors and batch_job_id:
#             sync_to_v6_1_registry(batch_job_id, this_round_kept_factors, config)

#         storage.save_decisions(round_label, this_round_decisions)
#         current_queue = next_round_queue

#     if db is not None:
#         db.clear_cache()
#     print(f"\n[Done] Fundamental evolution finished. Hall of fame: {len(hall_of_fame)}")
#     return hall_of_fame

import json
import re

from factor_engine.optimizer.fundamental.prompts_opt_fund import (
    FUND_DOCTOR_TABLE_SYSTEM_PROMPT,
    FUND_DOCTOR_TABLE_USER_TEMPLATE,
    FUND_JUDGE_SYSTEM_PROMPT,
    FUND_JUDGE_USER_TEMPLATE,
    build_fund_coder_prompt,
)


def parse_markdown_table_to_list(markdown_text, job_id, round_num):
    data = []
    lines = [line.strip() for line in markdown_text.strip().split("\n") if line.strip()]

    start_row = -1
    col_map = {}
    for i, line in enumerate(lines):
        if "|" in line and "Parent_Name" in line and "Formula" in line:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            col_map = {name: idx for idx, name in enumerate(cols)}
            start_row = i + 2
            break

    if start_row == -1:
        return []

    variant_counter = {}
    for line in lines[start_row:]:
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue

        parent_name = parts[col_map.get("Parent_Name", 0)].replace("`", "").replace("*", "")
        formula = parts[col_map.get("Formula", 1)]
        logic = parts[col_map.get("Logic", 2)]

        root_name = parent_name.split("_G")[0]
        variant_counter[parent_name] = variant_counter.get(parent_name, 0) + 1
        variant_idx = variant_counter[parent_name]
        factor_name = f"{root_name}_G{round_num}_v{variant_idx}"

        data.append(
            {
                "Job_ID": job_id,
                "Parent_Name": parent_name,
                "Factor_Name": factor_name,
                "Logic": logic,
                "Formula": formula,
                "Code": "",
            }
        )

    return data


def run_doctor_step_fund(optimization_tasks, client_doctor, round_num):
    if not optimization_tasks:
        return []

    print(f"[FUND-LLM5] Generating prescriptions for {len(optimization_tasks)} factors...")
    tasks_desc = ""
    for task in optimization_tasks:
        action = task.get("action", "PIVOT")
        num_variants = 3 if action == "PIVOT" else 1
        metrics = task.get("metrics", {})

        tasks_desc += f"- 原名: {task['name']}\n"
        tasks_desc += f"  当前状态: {action}\n"
        tasks_desc += f"  要求生成方案数: {num_variants}\n"
        tasks_desc += f"  RankIC: {metrics.get('RankIC', 'N/A')}\n"
        tasks_desc += f"  ICIR: {metrics.get('ICIR', 'N/A')}\n"
        tasks_desc += f"  ExtremeGroupDailyExcess: {metrics.get('ExtremeGroupDailyExcess', 0)}\n"
        tasks_desc += f"  ExtremeGroupMaxExcess: {metrics.get('ExtremeGroupMaxExcess', 0)}\n"
        tasks_desc += f"  目标阈值(日频): 0.0004\n"
        tasks_desc += (
            "  诊断意见: "
            f"{task.get('diagnosis', '请强化极值组识别能力，并把日频极值组超额绝对值推向 0.0004')}\n"
        )
        tasks_desc += f"  原始逻辑: {task.get('original_logic', '无')}\n\n"

    try:
        user_content = FUND_DOCTOR_TABLE_USER_TEMPLATE.format(tasks_description=tasks_desc)
        resp = client_doctor.invoke(
            [
                {"role": "system", "content": FUND_DOCTOR_TABLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
        content = getattr(resp, "content", str(resp))
        round_label = f"round_{round_num}"
        prescriptions = parse_markdown_table_to_list(content, round_label, round_num)
        print(f"[FUND-LLM5] Generated {len(prescriptions)} prescriptions.")
        return prescriptions
    except Exception as exc:
        print(f"[FUND-LLM5] Doctor step failed: {exc}")
        return []


def _extract_context_fields(code_text):
    return set(re.findall(r"context\[['\"]([^'\"]+)['\"]\]", code_text or ""))


def run_coder_step_fund(prescriptions, client_coder, useful_fields=None):
    if not prescriptions:
        return []

    print(f"[FUND-LLM6] Writing code for {len(prescriptions)} factors...")
    results = []
    useful_fields_set = {str(field).strip() for field in (useful_fields or []) if str(field).strip()}
    for item in prescriptions:
        raw_name = item["Factor_Name"]
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
        item["Factor_Name"] = safe_name

        try:
            prompt = build_fund_coder_prompt(
                name=safe_name,
                formula=item["Formula"],
                logic=item["Logic"],
                useful_fields=sorted(useful_fields_set),
            )
            resp = client_coder.invoke(prompt)
            content = getattr(resp, "content", str(resp))
            if "```python" in content:
                clean_code = content.split("```python")[1].split("```")[0].strip()
            else:
                clean_code = content.replace("```", "").strip()

            invalid_fields = sorted(_extract_context_fields(clean_code) - useful_fields_set) if useful_fields_set else []
            if invalid_fields:
                repair_prompt = (
                    prompt
                    + "\n\n"
                    + f"你刚才错误引用了这些不在白名单中的字段: {', '.join(invalid_fields)}。\n"
                    + "请立即重写整段代码，只允许使用白名单中的字段，并只输出完整 Python 代码。"
                )
                resp = client_coder.invoke(repair_prompt)
                content = getattr(resp, "content", str(resp))
                if "```python" in content:
                    clean_code = content.split("```python")[1].split("```")[0].strip()
                else:
                    clean_code = content.replace("```", "").strip()
                invalid_fields = sorted(_extract_context_fields(clean_code) - useful_fields_set)

            if invalid_fields:
                print(
                    f"[FUND-LLM6] Skip {safe_name}: generated unavailable fields "
                    f"{', '.join(invalid_fields)}"
                )
                continue

            item["Code"] = clean_code
            results.append(item)
        except Exception as exc:
            print(f"[FUND-LLM6] Code generation failed for {safe_name}: {exc}")

    return results


def run_judge_workflow_fund(full_factor_context, client_llm):
    if not full_factor_context:
        return []

    print(f"[FUND-LLM4] Judging {len(full_factor_context)} financial factors...")
    context_str = json.dumps(full_factor_context, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": FUND_JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": FUND_JUDGE_USER_TEMPLATE.format(context_json=context_str)},
    ]

    try:
        response = client_llm.invoke(messages)
        content = getattr(response, "content", str(response))
        clean_content = content.replace("```json", "").replace("```", "").strip()
        decisions = json.loads(clean_content)
        return decisions
    except Exception as exc:
        print(f"[FUND-LLM4] Judge step failed: {exc}")
        print("Raw output:", content if "content" in locals() else "None")
        return []

