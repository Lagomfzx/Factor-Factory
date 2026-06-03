import json
import os
import time
import uuid

import requests

from factor_engine.common.runtime_env import get_platform_url, load_dotenv_files


load_dotenv_files()


EXTREME_GROUP_DAILY_TARGET = 0.0004
EXTREME_GROUP_ANNUAL_TARGET = round(EXTREME_GROUP_DAILY_TARGET * 252, 4)

PRICE_VOLUME_LONG_DAILY_TARGET = 0.0008
PRICE_VOLUME_SHORT_DAILY_TARGET_ABS = 0.0002

FUND_LONG_POSITIVE_DAILY_FLOOR = 0.0002
FUND_RECENT_POSITIVE_DAILY_TARGET = 0.0004
FUND_LONG_NEGATIVE_DAILY_TARGET_ABS = 0.0004
FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS = 0.0006
FUND_RECENT_YEAR_COUNT = 2


def _to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _matches_hint(key_str, hint):
    if hint in {"group1", "group10", "decile1", "decile10"}:
        normalized = key_str.replace("_", "").replace("-", "").replace(" ", "")
        return normalized.endswith(hint)
    return hint in key_str


def _pick_group_by_hint(group_metrics, hints):
    for key, value in group_metrics.items():
        key_str = str(key).lower()
        if any(_matches_hint(key_str, hint) for hint in hints) and isinstance(value, dict):
            return value
    return {}


def _safe_mean(values):
    clean_values = [_to_float(value) for value in values if value is not None]
    if not clean_values:
        return 0.0
    return sum(clean_values) / len(clean_values)


def _metrics_by_year_rows(metrics_by_year):
    if isinstance(metrics_by_year, list):
        return [row for row in metrics_by_year if isinstance(row, dict)]

    if not isinstance(metrics_by_year, dict):
        return []

    list_lengths = [
        len(value)
        for value in metrics_by_year.values()
        if isinstance(value, list)
    ]
    if not list_lengths:
        return []

    row_count = min(list_lengths)
    rows = []
    for idx in range(row_count):
        row = {}
        for key, value in metrics_by_year.items():
            row[key] = value[idx] if isinstance(value, list) and idx < len(value) else value
        rows.append(row)
    return rows


def extract_yearly_group_metrics(raw_result_item, recent_year_count=FUND_RECENT_YEAR_COUNT):
    rows = _metrics_by_year_rows(raw_result_item.get("metrics_by_year"))
    if not rows:
        return {
            "RecentYears": [],
            "YearlyTopGroupDailyRet": {},
            "YearlyBottomGroupDailyRet": {},
            "RecentTopGroupDailyRetList": [],
            "RecentBottomGroupDailyRetList": [],
            "RecentTopGroupAvgDaily": 0.0,
            "RecentBottomGroupAvgDaily": 0.0,
            "RecentPositiveAlphaDaily": 0.0,
            "RecentNegativeAlphaAbs": 0.0,
            "RecentPositiveAllPositive": False,
            "RecentNegativeAllNegative": False,
            "HitFundRecentPositiveTarget": False,
            "HitFundRecentNegativeTarget": False,
        }

    top_by_year = {}
    bottom_by_year = {}
    years = set()
    for row in rows:
        year_value = row.get("年份")
        group_value = row.get("分组")
        try:
            year = int(year_value)
        except Exception:
            continue

        years.add(year)
        group_num = _to_float(group_value)
        group_str = str(group_value).strip().lower()
        daily_ret = _to_float(row.get("日均收益"))
        is_top_group = abs(group_num - 10.0) < 1e-9 or any(
            _matches_hint(group_str, hint)
            for hint in ["极大", "最大", "long", "top", "high", "group10", "decile10"]
        )
        is_bottom_group = abs(group_num - 1.0) < 1e-9 or any(
            _matches_hint(group_str, hint)
            for hint in ["极小", "最小", "short", "bottom", "low", "group1", "decile1"]
        )
        if is_top_group:
            top_by_year[year] = daily_ret
        elif is_bottom_group:
            bottom_by_year[year] = daily_ret

    sorted_years = sorted(years)
    recent_years = sorted_years[-recent_year_count:] if recent_year_count > 0 else []
    recent_top = [top_by_year[year] for year in recent_years if year in top_by_year]
    recent_bottom = [bottom_by_year[year] for year in recent_years if year in bottom_by_year]

    top_avg = _safe_mean(recent_top)
    bottom_avg = _safe_mean(recent_bottom)
    recent_positive_all_positive = (
        len(recent_top) == len(recent_years) and bool(recent_top) and all(value > 0 for value in recent_top)
    )
    recent_negative_all_negative = (
        len(recent_bottom) == len(recent_years) and bool(recent_bottom) and all(value < 0 for value in recent_bottom)
    )
    recent_positive_alpha = max(top_avg, 0.0)
    recent_negative_alpha_abs = max(-bottom_avg, 0.0)

    return {
        "RecentYears": recent_years,
        "YearlyTopGroupDailyRet": {str(year): round(value, 6) for year, value in sorted(top_by_year.items())},
        "YearlyBottomGroupDailyRet": {str(year): round(value, 6) for year, value in sorted(bottom_by_year.items())},
        "RecentTopGroupDailyRetList": [round(value, 6) for value in recent_top],
        "RecentBottomGroupDailyRetList": [round(value, 6) for value in recent_bottom],
        "RecentTopGroupAvgDaily": round(top_avg, 6),
        "RecentBottomGroupAvgDaily": round(bottom_avg, 6),
        "RecentPositiveAlphaDaily": round(recent_positive_alpha, 6),
        "RecentNegativeAlphaAbs": round(recent_negative_alpha_abs, 6),
        "RecentPositiveAllPositive": recent_positive_all_positive,
        "RecentNegativeAllNegative": recent_negative_all_negative,
        "HitFundRecentPositiveTarget": (
            recent_positive_all_positive and recent_positive_alpha >= FUND_RECENT_POSITIVE_DAILY_TARGET
        ),
        "HitFundRecentNegativeTarget": (
            recent_negative_all_negative and recent_negative_alpha_abs >= FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS
        ),
    }


def _extract_group_curve_summary(group_metrics):
    curve_pairs = []
    for idx in range(1, 11):
        bucket = group_metrics.get(f"组{idx}")
        if isinstance(bucket, dict):
            curve_pairs.append(
                (
                    f"组{idx}",
                    _to_float(bucket.get("mean_ret")),
                    _to_float(bucket.get("sharpe_ratio")),
                )
            )

    if not curve_pairs:
        return {
            "GroupCurveDailyRet": {},
            "GroupCurveDailyRetText": "N/A",
            "GroupCurveDailySharpe": {},
            "TopBottomSpreadDaily": 0.0,
            "BestGroupName": "UNKNOWN",
            "WorstGroupName": "UNKNOWN",
            "BestGroupDailyRet": 0.0,
            "WorstGroupDailyRet": 0.0,
            "MonotonicityScore": 0.0,
            "MonotonicityLabel": "UNKNOWN",
            "TailDominance": "UNKNOWN",
        }

    daily_curve = {name: round(mean_ret, 6) for name, mean_ret, _ in curve_pairs}
    sharpe_curve = {name: round(sharpe, 2) for name, _, sharpe in curve_pairs}
    curve_text = ", ".join(f"{name}={mean_ret:.6f}" for name, mean_ret, _ in curve_pairs)

    mean_values = [mean_ret for _, mean_ret, _ in curve_pairs]
    pair_count = max(len(mean_values) - 1, 1)
    increasing_pairs = sum(1 for left, right in zip(mean_values, mean_values[1:]) if right >= left)
    decreasing_pairs = sum(1 for left, right in zip(mean_values, mean_values[1:]) if right <= left)

    monotonicity_score = max(increasing_pairs, decreasing_pairs) / pair_count
    if monotonicity_score >= 0.8:
        monotonicity_label = "INCREASING" if increasing_pairs >= decreasing_pairs else "DECREASING"
    elif monotonicity_score >= 0.6:
        monotonicity_label = "PARTIAL"
    else:
        monotonicity_label = "MIXED"

    best_group_name, best_group_ret, _ = max(curve_pairs, key=lambda item: item[1])
    worst_group_name, worst_group_ret, _ = min(curve_pairs, key=lambda item: item[1])
    top_bottom_spread_daily = best_group_ret - worst_group_ret

    if abs(best_group_ret) > abs(worst_group_ret):
        tail_dominance = "LONG"
    elif abs(best_group_ret) < abs(worst_group_ret):
        tail_dominance = "SHORT"
    else:
        tail_dominance = "BALANCED"

    return {
        "GroupCurveDailyRet": daily_curve,
        "GroupCurveDailyRetText": curve_text,
        "GroupCurveDailySharpe": sharpe_curve,
        "TopBottomSpreadDaily": round(top_bottom_spread_daily, 6),
        "BestGroupName": best_group_name,
        "WorstGroupName": worst_group_name,
        "BestGroupDailyRet": round(best_group_ret, 6),
        "WorstGroupDailyRet": round(worst_group_ret, 6),
        "MonotonicityScore": round(monotonicity_score, 3),
        "MonotonicityLabel": monotonicity_label,
        "TailDominance": tail_dominance,
    }


def extract_extreme_group_metrics(raw_result_item):
    group_metrics = raw_result_item.get("group_metics") or raw_result_item.get("group_metrics") or {}
    curve_summary = _extract_group_curve_summary(group_metrics) if isinstance(group_metrics, dict) else _extract_group_curve_summary({})

    if not isinstance(group_metrics, dict) or not group_metrics:
        return {
            "ExtremeGroupDailyExcess": 0.0,
            "ExtremeGroupMaxExcess": 0.0,
            "BestExtremeSide": "UNKNOWN",
            "TopGroupDailyRet": 0.0,
            "BottomGroupDailyRet": 0.0,
            "TopGroupSharpe": 0.0,
            "BottomGroupSharpe": 0.0,
            "PositiveAlphaDaily": 0.0,
            "NegativeAlphaDailyAbs": 0.0,
            "HitLongTarget": False,
            "HitShortTarget": False,
            **curve_summary,
            "RawGroupMetrics": group_metrics,
        }

    top_group = _pick_group_by_hint(group_metrics, ["极大", "最大", "long", "top", "high", "group10", "decile10"])
    bottom_group = _pick_group_by_hint(group_metrics, ["极小", "最小", "short", "bottom", "low", "group1", "decile1"])

    top_ret = _to_float((top_group or {}).get("mean_ret"))
    bottom_ret = _to_float((bottom_group or {}).get("mean_ret"))
    top_sharpe = _to_float((top_group or {}).get("sharpe_ratio"))
    bottom_sharpe = _to_float((bottom_group or {}).get("sharpe_ratio"))

    positive_alpha = max(top_ret, 0.0)
    negative_alpha_abs = max(-bottom_ret, 0.0)
    hit_long_target = positive_alpha >= PRICE_VOLUME_LONG_DAILY_TARGET
    hit_short_target = negative_alpha_abs >= PRICE_VOLUME_SHORT_DAILY_TARGET_ABS

    if top_group or bottom_group:
        daily_abs_max = max(abs(top_ret), abs(bottom_ret))
        best_side = "LONG" if abs(top_ret) >= abs(bottom_ret) else "SHORT"
        return {
            "ExtremeGroupDailyExcess": round(daily_abs_max, 6),
            "ExtremeGroupMaxExcess": round(daily_abs_max * 252, 4),
            "BestExtremeSide": best_side,
            "TopGroupDailyRet": round(top_ret, 6),
            "BottomGroupDailyRet": round(bottom_ret, 6),
            "TopGroupSharpe": round(top_sharpe, 2),
            "BottomGroupSharpe": round(bottom_sharpe, 2),
            "PositiveAlphaDaily": round(positive_alpha, 6),
            "NegativeAlphaDailyAbs": round(negative_alpha_abs, 6),
            "HitLongTarget": hit_long_target,
            "HitShortTarget": hit_short_target,
            **curve_summary,
            "RawGroupMetrics": group_metrics,
        }

    best_side = "UNKNOWN"
    daily_abs_max = 0.0
    for key, value in group_metrics.items():
        if not isinstance(value, dict):
            continue
        mean_ret = _to_float(value.get("mean_ret"))
        if abs(mean_ret) > daily_abs_max:
            daily_abs_max = abs(mean_ret)
            key_str = str(key).lower()
            if any(_matches_hint(key_str, hint) for hint in ["极大", "最大", "long", "top", "high", "group10", "decile10"]):
                best_side = "LONG"
            elif any(_matches_hint(key_str, hint) for hint in ["极小", "最小", "short", "bottom", "low", "group1", "decile1"]):
                best_side = "SHORT"
            else:
                best_side = str(key)

    return {
        "ExtremeGroupDailyExcess": round(daily_abs_max, 6),
        "ExtremeGroupMaxExcess": round(daily_abs_max * 252, 4),
        "BestExtremeSide": best_side,
        "TopGroupDailyRet": 0.0,
        "BottomGroupDailyRet": 0.0,
        "TopGroupSharpe": 0.0,
        "BottomGroupSharpe": 0.0,
        "PositiveAlphaDaily": 0.0,
        "NegativeAlphaDailyAbs": 0.0,
        "HitLongTarget": False,
        "HitShortTarget": False,
        **curve_summary,
        "RawGroupMetrics": group_metrics,
    }


def clean_platform_result(raw_result_item):
    if not raw_result_item:
        return {}

    rank_ic = raw_result_item.get("rank_ic")
    rank_icir = raw_result_item.get("rank_icir")
    raw_turnover = raw_result_item.get("turnover") or raw_result_item.get("long_short_turnover")

    extreme_metrics = extract_extreme_group_metrics(raw_result_item)
    yearly_metrics = extract_yearly_group_metrics(raw_result_item)
    top_ret = extreme_metrics["TopGroupDailyRet"]
    bottom_ret = extreme_metrics["BottomGroupDailyRet"]

    clean_data = {
        "Name": raw_result_item.get("col_name", "Unknown"),
        "RankIC": round(rank_ic or 0, 4),
        "ICIR": round(rank_icir or 0, 2),
        "Turnover": round(raw_turnover, 2) if raw_turnover is not None else "N/A",
        "ExtremeGroupDailyExcess": extreme_metrics["ExtremeGroupDailyExcess"],
        "ExtremeGroupMaxExcess": extreme_metrics["ExtremeGroupMaxExcess"],
        "BestExtremeSide": extreme_metrics["BestExtremeSide"],
        "TopGroupDailyRet": top_ret,
        "BottomGroupDailyRet": bottom_ret,
        "TopGroupSharpe": extreme_metrics["TopGroupSharpe"],
        "BottomGroupSharpe": extreme_metrics["BottomGroupSharpe"],
        "PositiveAlphaDaily": extreme_metrics["PositiveAlphaDaily"],
        "NegativeAlphaDailyAbs": extreme_metrics["NegativeAlphaDailyAbs"],
        "HitLongTarget": extreme_metrics["HitLongTarget"],
        "HitShortTarget": extreme_metrics["HitShortTarget"],
        "FundLongPositiveDailyFloor": FUND_LONG_POSITIVE_DAILY_FLOOR,
        "FundRecentPositiveDailyTarget": FUND_RECENT_POSITIVE_DAILY_TARGET,
        "FundLongNegativeDailyTargetAbs": FUND_LONG_NEGATIVE_DAILY_TARGET_ABS,
        "FundRecentNegativeDailyTargetAbs": FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS,
        "HitFundLongPositiveFloor": (
            extreme_metrics["PositiveAlphaDaily"] >= FUND_LONG_POSITIVE_DAILY_FLOOR
        ),
        "HitFundLongNegativeTarget": (
            extreme_metrics["NegativeAlphaDailyAbs"] >= FUND_LONG_NEGATIVE_DAILY_TARGET_ABS
        ),
        "LongDailyTarget": PRICE_VOLUME_LONG_DAILY_TARGET,
        "ShortDailyTargetAbs": PRICE_VOLUME_SHORT_DAILY_TARGET_ABS,
        "GroupCurveDailyRet": extreme_metrics["GroupCurveDailyRet"],
        "GroupCurveDailyRetText": extreme_metrics["GroupCurveDailyRetText"],
        "GroupCurveDailySharpe": extreme_metrics["GroupCurveDailySharpe"],
        "TopBottomSpreadDaily": extreme_metrics["TopBottomSpreadDaily"],
        "BestGroupName": extreme_metrics["BestGroupName"],
        "WorstGroupName": extreme_metrics["WorstGroupName"],
        "BestGroupDailyRet": extreme_metrics["BestGroupDailyRet"],
        "WorstGroupDailyRet": extreme_metrics["WorstGroupDailyRet"],
        "MonotonicityScore": extreme_metrics["MonotonicityScore"],
        "MonotonicityLabel": extreme_metrics["MonotonicityLabel"],
        "TailDominance": extreme_metrics["TailDominance"],
        "LongTargetGap": round(PRICE_VOLUME_LONG_DAILY_TARGET - max(top_ret, 0.0), 6),
        "ShortTargetGap": round(PRICE_VOLUME_SHORT_DAILY_TARGET_ABS - max(-bottom_ret, 0.0), 6),
    }
    clean_data.update(yearly_metrics)

    try:
        long_short_ret = (top_ret - bottom_ret) * 252
        clean_data["LongShortRet"] = f"{long_short_ret:.2%}"
    except Exception:
        clean_data["LongShortRet"] = "Error"

    return clean_data


def wait_and_save_remote_result(base_url, job_id, save_path, max_retries=60 * 15, sleep_time=3):
    target_url = f"{base_url}/jobs/{job_id}"
    print(f"[Remote Sync] Monitoring job: {job_id}")

    save_dir = os.path.dirname(save_path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    for i in range(max_retries):
        try:
            res = requests.get(target_url)
            if res.status_code == 200:
                res_json = res.json()
                current_status = res_json.get("status")
                results = res_json.get("results")

                if current_status == "running":
                    if i % 10 == 0:
                        print(
                            f"[Remote Sync] still running "
                            f"(status={current_status}, elapsed={i * sleep_time}s)"
                        )
                elif results is not None or current_status in ["success", "completed", "finished"]:
                    print(f"[Remote Sync] completed (status={current_status})")
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(res_json, f, ensure_ascii=False, indent=4)
                    print(f"[Remote Sync] archived result: {os.path.basename(save_path)}")
                    return res_json
                elif current_status in ["failed", "error"]:
                    error_msg = res_json.get("payload", {}).get("message", "Unknown error")
                    print(f"[Remote Sync] failed: {error_msg}")
                    return None
                else:
                    print(f"[Remote Sync] unknown status={current_status}, keep waiting...")
            else:
                print(f"[Remote Sync] polling http error: {res.status_code}")
        except Exception as exc:
            print(f"[Remote Sync] network error: {exc}")
        time.sleep(sleep_time)

    print("[Remote Sync] timeout waiting for result.")
    return None


def submit_batch_factors(
    factor_tasks,
    operator_header,
    remote_result_dir,
    base_url=None,
    extra_payload=None,
):
    if base_url is None:
        base_url = get_platform_url()
    all_factor_code = "\n\n".join([task["Code"] for task in factor_tasks])
    final_payload_code = operator_header + "\n" + all_factor_code

    session_id = str(uuid.uuid4())
    payload = {
        "explain": f"Batch_Optimization_{session_id}",
        "py_code": final_payload_code,
        "session_id": session_id,
        "exec_type": "cs",
    }
    if extra_payload:
        payload.update(extra_payload)

    print(f"[Batch Submit] sending {len(factor_tasks)} factors...")

    try:
        res = requests.post(f"{base_url}/jobs", json=payload)
        job_id = res.json().get("job_id")

        os.makedirs(remote_result_dir, exist_ok=True)
        save_path = os.path.join(remote_result_dir, f"{job_id}.json")
        wait_and_save_remote_result(base_url, job_id, save_path)

        with open(save_path, "r", encoding="utf-8") as f:
            full_data = json.load(f)

        results_map = {}
        for res_item in full_data.get("results", []):
            name = res_item.get("col_name")
            results_map[name] = clean_platform_result(res_item)

        return job_id, results_map
    except Exception as exc:
        print(f"[Batch Submit] failed: {exc}")
        return None, {}


def submit_to_platform(
    py_code,
    explain_text,
    exec_type="cs",
    url=None,
    extra_payload=None,
):
    if url is None:
        url = get_platform_url()
    session_id = str(uuid.uuid4())
    payload = {
        "explain": explain_text,
        "py_code": py_code,
        "session_id": session_id,
        "exec_type": exec_type,
    }
    if extra_payload:
        payload.update(extra_payload)

    try:
        print(f"[Remote Submit] sending job (session={session_id[:8]}...)")
        res = requests.post(url + "/jobs", json=payload)
        if res.status_code == 200:
            data = res.json()
            job_id = data.get("job_id") or data.get("id")
            print(f"[Remote Submit] success, job_id={job_id}")
            return job_id
        print(f"[Remote Submit] failed, http={res.status_code}, body={res.text}")
        return None
    except Exception as exc:
        print(f"[Remote Submit] network error: {exc}")
        return None
