import json
import os
import re

import pandas as pd

from factor_engine.common.platform_api import (
    PRICE_VOLUME_LONG_DAILY_TARGET,
    PRICE_VOLUME_SHORT_DAILY_TARGET_ABS,
)
from factor_engine.common.storage import sync_to_v6_1_registry


def load_json_data(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Error: {exc}")
        return None


def build_judge_context(clean_metrics_list, llm1_raw_text, llm3_raw_text):
    logic_map = {}
    lines = llm1_raw_text.strip().split("\n")
    for line in lines:
        if "|" in line and "因子名称" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                raw_name = parts[1].replace("**", "").replace("`", "").strip()
                raw_logic = parts[3].strip()
                if raw_name:
                    logic_map[raw_name] = raw_logic

    code_map = {}
    clean_code_text = llm3_raw_text.replace("```python", "").replace("```", "")
    pattern = r"(def\s+calculate_(\w+)\s*\(.*?\):.*?)(?=\ndef\s+calculate_|\Z)"
    matches = re.findall(pattern, clean_code_text, re.DOTALL)
    for full_code, factor_name in matches:
        code_map[factor_name] = full_code.strip()

    final_context = []
    for item in clean_metrics_list:
        factor_name = item.get("Name")
        final_context.append(
            {
                "name": factor_name,
                "logic": logic_map.get(factor_name, "逻辑描述未匹配到"),
                "code": code_map.get(factor_name, "# 代码未匹配到"),
                "metrics": item,
            }
        )
    return final_context


def get_optimization_queue(decisions, original_context):
    queue = []
    context_map = {item["name"]: item for item in original_context}

    for case in decisions:
        if case.get("decision") != "OPTIMIZE":
            continue

        factor_name = case.get("name")
        source_data = context_map.get(factor_name)
        if not source_data:
            continue

        metrics = source_data.get("metrics", {}) or {}
        top_group_daily = max(float(metrics.get("TopGroupDailyRet") or 0), 0.0)
        bottom_group_daily_abs = max(-float(metrics.get("BottomGroupDailyRet") or 0), 0.0)

        if (
            top_group_daily >= PRICE_VOLUME_LONG_DAILY_TARGET * 0.6
            or bottom_group_daily_abs >= PRICE_VOLUME_SHORT_DAILY_TARGET_ABS * 0.6
        ):
            next_action = "EVOLVE"
        else:
            next_action = "PIVOT"

        queue.append(
            {
                "name": factor_name,
                "original_code": source_data["code"],
                "original_logic": source_data["logic"],
                "metrics": metrics,
                "diagnosis": case.get("diagnosis", ""),
                "reason": case.get("reason", ""),
                "action": next_action,
                "pivot_count": 0,
            }
        )
    return queue


def extract_and_sync_genius_factors(decisions, gen_job_id, config):
    version_tag = config.version.upper()
    print(f"[Archive] Syncing KEEP factors from {version_tag} registry to premium registry...")

    kept_names = []
    for decision in decisions:
        if str(decision.get("decision", "")).strip().upper() == "KEEP":
            kept_names.append(str(decision.get("name", "")))

    if not kept_names:
        print("[Archive] No KEEP factors found in this batch.")
        return []

    registry_path = config.registry_csv
    if not os.path.exists(registry_path):
        print(f"[Archive] Registry file not found: {registry_path}")
        return []

    try:
        registry_df = pd.read_csv(registry_path)
        batch_df = registry_df[registry_df["Job_ID"] == gen_job_id]

        matched_factors = []
        for _, row in batch_df.iterrows():
            registry_name = str(row["Factor_Name"])
            for kept_name in kept_names:
                if kept_name in registry_name or registry_name in kept_name:
                    matched_factors.append(row.to_dict())
                    break

        print(f"[Archive] Matched {len(matched_factors)} KEEP factors from batch {gen_job_id}.")
        if matched_factors:
            sync_to_v6_1_registry(gen_job_id, matched_factors, config)

        return matched_factors
    except Exception as exc:
        print(f"[Archive] Failed to read or sync KEEP factors: {exc}")
        return []
