import json
import re

from factor_engine.optimizer.price_volume.prompts_opt import (
    CODER_PROMPT_TEMPLATE,
    DOCTOR_TABLE_SYSTEM_PROMPT,
    DOCTOR_TABLE_USER_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_TEMPLATE,
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


def run_doctor_step(optimization_tasks, client_doctor, round_num):
    if not optimization_tasks:
        return []

    print(f"[LLM5] Generating prescriptions for {len(optimization_tasks)} factors...")

    tasks_desc = ""
    for task in optimization_tasks:
        action = task.get("action", "PIVOT")
        num_variants = 3 if action == "PIVOT" else 1

        tasks_desc += f"- 原名: {task['name']}\n"
        tasks_desc += f"  当前状态: {action}\n"
        tasks_desc += f"  要求生成方案数: {num_variants}\n"
        tasks_desc += f"  诊断意见: {task.get('diagnosis', '请进行全方位探索优化')}\n"
        tasks_desc += f"  原逻辑: {task.get('original_logic', '无')}\n\n"

    try:
        user_content = DOCTOR_TABLE_USER_TEMPLATE.format(tasks_description=tasks_desc)
        resp = client_doctor.invoke(
            [
                {"role": "system", "content": DOCTOR_TABLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
        content = getattr(resp, "content", str(resp))
        round_label = f"round_{round_num}"
        prescriptions = parse_markdown_table_to_list(content, round_label, round_num)
        print(f"[LLM5] Generated {len(prescriptions)} prescriptions.")
        return prescriptions
    except Exception as exc:
        print(f"[LLM5] Doctor step failed: {exc}")
        return []


def run_coder_step(prescriptions, client_coder):
    if not prescriptions:
        return []

    print(f"[LLM6] Writing code for {len(prescriptions)} factors...")
    results = []

    for item in prescriptions:
        raw_name = item["Factor_Name"]
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
        item["Factor_Name"] = safe_name
        print(f"[LLM6] Writing calculate_{safe_name} ...")

        try:
            prompt = CODER_PROMPT_TEMPLATE.format(
                name=safe_name,
                formula=item["Formula"],
                logic=item["Logic"],
            )
            resp = client_coder.invoke(prompt)
            content = getattr(resp, "content", str(resp))

            if "```python" in content:
                clean_code = content.split("```python")[1].split("```")[0].strip()
            else:
                clean_code = content.replace("```", "").strip()

            item["Code"] = clean_code
            results.append(item)
        except Exception as exc:
            print(f"[LLM6] Code generation failed for {safe_name}: {exc}")

    return results


def run_judge_workflow(full_factor_context, client_llm):
    if not full_factor_context:
        return []

    print(f"[LLM4] Judging {len(full_factor_context)} factors...")
    context_str = json.dumps(full_factor_context, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": JUDGE_USER_TEMPLATE.format(context_json=context_str)},
    ]

    try:
        response = client_llm.invoke(messages)
        content = getattr(response, "content", str(response))
        clean_content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_content)
    except Exception as exc:
        print(f"[LLM4] Judge step failed: {exc}")
        print("Raw output:", content if "content" in locals() else "None")
        return []
