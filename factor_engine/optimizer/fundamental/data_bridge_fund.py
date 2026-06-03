import re

from factor_engine.common.platform_api import (
    EXTREME_GROUP_ANNUAL_TARGET,
    EXTREME_GROUP_DAILY_TARGET,
    FUND_LONG_NEGATIVE_DAILY_TARGET_ABS,
    FUND_LONG_POSITIVE_DAILY_FLOOR,
    FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS,
    FUND_RECENT_POSITIVE_DAILY_TARGET,
    extract_extreme_group_metrics,
    extract_yearly_group_metrics,
)


def build_judge_context_fund(raw_results, clean_metrics_list, llm1_raw_text, llm3_raw_text):
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

    raw_map = {item.get("col_name"): item for item in (raw_results or [])}
    final_context = []
    for item in clean_metrics_list:
        factor_name = item.get("Name")
        raw_item = raw_map.get(factor_name, {})
        extreme_metrics = extract_extreme_group_metrics(raw_item)
        yearly_metrics = extract_yearly_group_metrics(raw_item)

        enriched_metrics = dict(item)
        for price_volume_key in [
            "LongDailyTarget",
            "ShortDailyTargetAbs",
            "LongTargetGap",
            "ShortTargetGap",
            "HitLongTarget",
            "HitShortTarget",
        ]:
            enriched_metrics.pop(price_volume_key, None)
        enriched_metrics["ExtremeGroupDailyExcess"] = extreme_metrics["ExtremeGroupDailyExcess"]
        enriched_metrics["ExtremeGroupMaxExcess"] = extreme_metrics["ExtremeGroupMaxExcess"]
        enriched_metrics["BestExtremeSide"] = extreme_metrics["BestExtremeSide"]
        enriched_metrics["TopGroupDailyRet"] = extreme_metrics["TopGroupDailyRet"]
        enriched_metrics["BottomGroupDailyRet"] = extreme_metrics["BottomGroupDailyRet"]
        enriched_metrics["PositiveAlphaDaily"] = extreme_metrics["PositiveAlphaDaily"]
        enriched_metrics["NegativeAlphaDailyAbs"] = extreme_metrics["NegativeAlphaDailyAbs"]
        enriched_metrics["RawGroupMetrics"] = extreme_metrics["RawGroupMetrics"]
        enriched_metrics["ExtremeGroupDailyTarget"] = EXTREME_GROUP_DAILY_TARGET
        enriched_metrics["ExtremeGroupAnnualTarget"] = EXTREME_GROUP_ANNUAL_TARGET
        enriched_metrics["HitExtremeTarget"] = (
            extreme_metrics["ExtremeGroupDailyExcess"] >= EXTREME_GROUP_DAILY_TARGET
        )
        enriched_metrics["FundLongPositiveDailyFloor"] = FUND_LONG_POSITIVE_DAILY_FLOOR
        enriched_metrics["FundRecentPositiveDailyTarget"] = FUND_RECENT_POSITIVE_DAILY_TARGET
        enriched_metrics["FundLongNegativeDailyTargetAbs"] = FUND_LONG_NEGATIVE_DAILY_TARGET_ABS
        enriched_metrics["FundRecentNegativeDailyTargetAbs"] = FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS
        enriched_metrics["HitFundLongPositiveFloor"] = (
            extreme_metrics["PositiveAlphaDaily"] >= FUND_LONG_POSITIVE_DAILY_FLOOR
        )
        enriched_metrics["HitFundLongNegativeTarget"] = (
            extreme_metrics["NegativeAlphaDailyAbs"] >= FUND_LONG_NEGATIVE_DAILY_TARGET_ABS
        )
        enriched_metrics.update(yearly_metrics)

        final_context.append(
            {
                "name": factor_name,
                "logic": logic_map.get(factor_name, "逻辑描述未匹配到"),
                "code": code_map.get(factor_name, "# 代码未匹配到"),
                "metrics": enriched_metrics,
            }
        )
    return final_context


def get_optimization_queue_fund(decisions, original_context):
    queue = []
    context_map = {item["name"]: item for item in original_context}

    for case in decisions:
        if case["decision"] not in {"OPTIMIZE", "PIVOT"}:
            continue
        factor_name = case["name"]
        source_data = context_map.get(factor_name)
        if not source_data:
            continue

        queue.append(
            {
                "name": factor_name,
                "original_code": source_data["code"],
                "original_logic": source_data["logic"],
                "diagnosis": case.get("diagnosis", ""),
                "reason": case.get("reason", ""),
                "metrics": source_data.get("metrics", {}),
                "action": "PIVOT" if case["decision"] == "PIVOT" else "EVOLVE",
                "pivot_count": 0,
            }
        )

    return queue
