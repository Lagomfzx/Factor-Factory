import json
import os
import time
import uuid

import requests

from factor_engine.common.runtime_env import get_platform_url, load_dotenv_files


load_dotenv_files()


EXTREME_GROUP_DAILY_TARGET = 0.0004
EXTREME_GROUP_ANNUAL_TARGET = round(EXTREME_GROUP_DAILY_TARGET * 252, 4)


def extract_extreme_group_metrics(raw_result_item):
    group_metrics = raw_result_item.get("group_metics") or raw_result_item.get("group_metrics") or {}
    if not isinstance(group_metrics, dict) or not group_metrics:
        return {
            "ExtremeGroupDailyExcess": 0.0,
            "ExtremeGroupMaxExcess": 0.0,
            "BestExtremeSide": "UNKNOWN",
            "RawGroupMetrics": group_metrics,
        }

    def _to_float(value):
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def _pick_group_by_hint(hints):
        for key, value in group_metrics.items():
            key_str = str(key).lower()
            if any(hint in key_str for hint in hints) and isinstance(value, dict):
                return value
        return {}

    long_group = _pick_group_by_hint(["极大", "最大", "long", "top", "high", "group10", "decile10"])
    short_group = _pick_group_by_hint(["极小", "最小", "short", "bottom", "low", "group1", "decile1"])

    long_ret = _to_float(long_group.get("mean_ret"))
    short_ret = _to_float(short_group.get("mean_ret"))

    if long_group or short_group:
        daily_abs_max = max(abs(long_ret), abs(short_ret))
        best_side = "LONG" if abs(long_ret) >= abs(short_ret) else "SHORT"
        return {
            "ExtremeGroupDailyExcess": round(daily_abs_max, 6),
            "ExtremeGroupMaxExcess": round(daily_abs_max * 252, 4),
            "BestExtremeSide": best_side,
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
            if any(hint in key_str for hint in ["极大", "最大", "long", "top", "high"]):
                best_side = "LONG"
            elif any(hint in key_str for hint in ["极小", "最小", "short", "bottom", "low"]):
                best_side = "SHORT"
            else:
                best_side = str(key)

    return {
        "ExtremeGroupDailyExcess": round(daily_abs_max, 6),
        "ExtremeGroupMaxExcess": round(daily_abs_max * 252, 4),
        "BestExtremeSide": best_side,
        "RawGroupMetrics": group_metrics,
    }


def clean_platform_result(raw_result_item):
    if not raw_result_item:
        return {}

    rank_ic = raw_result_item.get("rank_ic")
    rank_icir = raw_result_item.get("rank_icir")
    raw_turnover = raw_result_item.get("turnover") or raw_result_item.get("long_short_turnover")

    extreme_metrics = extract_extreme_group_metrics(raw_result_item)

    clean_data = {
        "Name": raw_result_item.get("col_name", "Unknown"),
        "RankIC": round(rank_ic or 0, 4),
        "ICIR": round(rank_icir or 0, 2),
        "Turnover": round(raw_turnover, 2) if raw_turnover is not None else "N/A",
        "ExtremeGroupDailyExcess": extreme_metrics["ExtremeGroupDailyExcess"],
        "ExtremeGroupMaxExcess": extreme_metrics["ExtremeGroupMaxExcess"],
        "BestExtremeSide": extreme_metrics["BestExtremeSide"],
    }

    group_metrics = extreme_metrics["RawGroupMetrics"]
    if group_metrics:
        try:
            long_group = None
            short_group = None
            for key, value in group_metrics.items():
                key_str = str(key).lower()
                if long_group is None and any(hint in key_str for hint in ["极大", "最大", "long", "top", "high"]):
                    long_group = value
                if short_group is None and any(hint in key_str for hint in ["极小", "最小", "short", "bottom", "low"]):
                    short_group = value

            long_ret = float((long_group or {}).get("mean_ret") or 0)
            short_ret = float((short_group or {}).get("mean_ret") or 0)
            long_short_ret = (long_ret - short_ret) * 252

            clean_data["LongShortRet"] = f"{long_short_ret:.2%}"
            clean_data["TopSharpe"] = round(float((long_group or {}).get("sharpe_ratio") or 0), 2)
        except Exception:
            clean_data["LongShortRet"] = "Error"
            clean_data["TopSharpe"] = 0
    else:
        clean_data["LongShortRet"] = "N/A"
        clean_data["TopSharpe"] = 0

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

        save_path = f"mydata/output/remote_json/{job_id}.json"
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
