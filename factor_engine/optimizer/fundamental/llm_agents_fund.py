import json
import re

from factor_engine.common.platform_api import (
    FUND_LONG_NEGATIVE_DAILY_TARGET_ABS,
    FUND_LONG_POSITIVE_DAILY_FLOOR,
    FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS,
    FUND_RECENT_POSITIVE_DAILY_TARGET,
)
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


def _format_doctor_field_context(useful_fields=None, field_governance=None):
    fields = []
    if field_governance and field_governance.get("allowed_fields"):
        fields = field_governance.get("allowed_fields") or []
    elif useful_fields:
        fields = useful_fields

    clean_fields = sorted({str(field).strip() for field in fields if str(field).strip()})
    lines = []
    if clean_fields:
        lines.append("【可用字段白名单】")
        lines.append("Doctor 可以新增字段，但只能从以下白名单中选择，禁止臆造字段或添加 _TTM/_YOY 等不存在的字段后缀：")
        lines.append(", ".join(clean_fields))

    if field_governance:
        focus_fields = field_governance.get("focus_fields") or []
        denominator_fields = field_governance.get("denominator_fields") or []
        cautious_fields = field_governance.get("cautious_fields") or []
        note_fields = field_governance.get("note_fields") or []
        field_notes = field_governance.get("field_notes") or {}

        if focus_fields:
            lines.append("【优先关注字段】" + ", ".join(focus_fields[:40]))
        if denominator_fields:
            lines.append("【优先分母/规模锚】" + ", ".join(denominator_fields[:30]))
        if cautious_fields:
            lines.append("【谨慎主干字段】这些字段可以用，但不要轻易作为唯一主信号：" + ", ".join(cautious_fields[:40]))
        if note_fields:
            lines.append("【附注/验证型字段】更适合作为确认、修正或过滤：" + ", ".join(note_fields[:40]))
        if field_notes:
            note_lines = [
                f"{field}: {note}"
                for field, note in sorted(field_notes.items())
                if field in clean_fields
            ][:60]
            if note_lines:
                lines.append("【字段备注】")
                lines.extend(note_lines)

    return "\n".join(lines) if lines else "【可用字段白名单】未传入；请尽量沿用原因子已有字段，不要臆造新字段。"


def run_doctor_step_fund(
    optimization_tasks,
    client_doctor,
    round_num,
    useful_fields=None,
    field_governance=None,
):
    if not optimization_tasks:
        return []

    print(f"[FUND-LLM5] Generating prescriptions for {len(optimization_tasks)} factors...")
    tasks_desc = ""
    for task in optimization_tasks:
        action = task.get("action", "PIVOT")
        num_variants = 3 if action == "PIVOT" else 2
        metrics = task.get("metrics", {})

        tasks_desc += f"- 原名: {task['name']}\n"
        tasks_desc += f"  当前状态: {action}\n"
        tasks_desc += f"  要求生成方案数: {num_variants}\n"
        tasks_desc += f"  RankIC: {metrics.get('RankIC', 'N/A')}\n"
        tasks_desc += f"  ICIR: {metrics.get('ICIR', 'N/A')}\n"
        tasks_desc += f"  BestExtremeSide: {metrics.get('BestExtremeSide', 'N/A')}\n"
        tasks_desc += f"  TopGroupDailyRet: {metrics.get('TopGroupDailyRet', 0)}\n"
        tasks_desc += f"  BottomGroupDailyRet: {metrics.get('BottomGroupDailyRet', 0)}\n"
        tasks_desc += f"  PositiveAlphaDaily: {metrics.get('PositiveAlphaDaily', 0)}\n"
        tasks_desc += f"  NegativeAlphaDailyAbs: {metrics.get('NegativeAlphaDailyAbs', 0)}\n"
        tasks_desc += f"  RecentYears: {metrics.get('RecentYears', [])}\n"
        tasks_desc += f"  RecentTopGroupDailyRetList: {metrics.get('RecentTopGroupDailyRetList', [])}\n"
        tasks_desc += f"  RecentBottomGroupDailyRetList: {metrics.get('RecentBottomGroupDailyRetList', [])}\n"
        tasks_desc += f"  RecentPositiveAlphaDaily: {metrics.get('RecentPositiveAlphaDaily', 0)}\n"
        tasks_desc += f"  RecentNegativeAlphaAbs: {metrics.get('RecentNegativeAlphaAbs', 0)}\n"
        tasks_desc += f"  RecentPositiveAllPositive: {metrics.get('RecentPositiveAllPositive', False)}\n"
        tasks_desc += f"  RecentNegativeAllNegative: {metrics.get('RecentNegativeAllNegative', False)}\n"
        tasks_desc += f"  ExtremeGroupDailyExcess: {metrics.get('ExtremeGroupDailyExcess', 0)}\n"
        tasks_desc += f"  ExtremeGroupMaxExcess: {metrics.get('ExtremeGroupMaxExcess', 0)}\n"
        tasks_desc += (
            f"  正向长周期底线(日频): PositiveAlphaDaily >= {FUND_LONG_POSITIVE_DAILY_FLOOR}\n"
        )
        tasks_desc += (
            f"  正向近两年理想(日频): RecentPositiveAlphaDaily 接近 {FUND_RECENT_POSITIVE_DAILY_TARGET} 且持续为正\n"
        )
        tasks_desc += (
            f"  负向长周期底线(日频): NegativeAlphaDailyAbs >= {FUND_LONG_NEGATIVE_DAILY_TARGET_ABS}\n"
        )
        tasks_desc += (
            f"  负向近两年理想(日频): RecentNegativeAlphaAbs 接近 {FUND_RECENT_NEGATIVE_DAILY_TARGET_ABS} 且持续为负\n"
        )
        tasks_desc += (
            "  诊断意见: "
            f"{task.get('diagnosis', '请优先满足正向长周期万2底线，并让近两年高值组持续为正、靠近万4；只有明确风险/排雷因子才强化长周期负万4与近两年负万6')}\n"
        )
        tasks_desc += f"  原始逻辑: {task.get('original_logic', '无')}\n\n"

    try:
        field_context = _format_doctor_field_context(
            useful_fields=useful_fields,
            field_governance=field_governance,
        )
        user_content = FUND_DOCTOR_TABLE_USER_TEMPLATE.format(
            tasks_description=tasks_desc,
            field_context=field_context,
        )
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


def run_coder_step_fund(
    prescriptions,
    client_coder,
    useful_fields=None,
    field_governance=None,
):
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
                field_governance=field_governance,
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
