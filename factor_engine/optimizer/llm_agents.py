# factor_engine/llm_agents.py

import re
import json
from factor_engine.optimizer.prompts_opt import (  # 注意路径变了
    DOCTOR_TABLE_SYSTEM_PROMPT, 
    DOCTOR_TABLE_USER_TEMPLATE,
    CODER_PROMPT_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_TEMPLATE
)

def parse_markdown_table_to_list(markdown_text, job_id, round_num):
    """【世代命名版】精准解析并由 Python 自动分配 G1, G2 世代名称"""
    data = []
    lines = [line.strip() for line in markdown_text.strip().split('\n') if line.strip()]
    
    start_row = -1
    col_map = {}
    for i, line in enumerate(lines):
        if '|' in line and 'Parent_Name' in line and 'Formula' in line:
            cols = [c.strip() for c in line.split('|') if c.strip()]
            col_map = {name: idx for idx, name in enumerate(cols)}
            start_row = i + 2
            break
            
    if start_row == -1: return []

    variant_counter = {}

    for line in lines[start_row:]:
        if '|' in line:
            parts = [p.strip() for p in line.strip('|').split('|')]
            if len(parts) >= 3:
                p_name = parts[col_map.get('Parent_Name', 0)].replace('`','').replace('*','')
                formula = parts[col_map.get('Formula', 1)]
                logic = parts[col_map.get('Logic', 2)]
                
                # 核心命名逻辑：提取祖先名，拼接 G 世代后缀
                root_name = p_name.split('_G')[0] 
                variant_counter[p_name] = variant_counter.get(p_name, 0) + 1
                v_idx = variant_counter[p_name]
                
                f_name = f"{root_name}_G{round_num}_v{v_idx}"
                
                data.append({
                    "Job_ID": job_id,
                    "Parent_Name": p_name,
                    "Factor_Name": f_name,
                    "Logic": logic,
                    "Formula": formula,
                    "Code": "" 
                })
    return data

def run_doctor_step(optimization_tasks, client_doctor, round_num):
    """【医生开方 v3.2 - 配合世代命名版】"""
    if not optimization_tasks:
        return []
        
    print(f"🏥 [LLM5] 正在为 {len(optimization_tasks)} 个因子开具处方...")
    
    tasks_desc = ""
    for t in optimization_tasks:
        action = t.get('action', 'PIVOT') 
        num_variants = 3 if action == 'PIVOT' else 1
        
        tasks_desc += f"- 原名: {t['name']}\n"
        tasks_desc += f"  当前状态: {action}\n"
        tasks_desc += f"  🔥要求生成方案数: {num_variants} 个\n"
        tasks_desc += f"  诊断意见: {t.get('diagnosis', '请进行全方位探索优化')}\n"
        tasks_desc += f"  原逻辑: {t.get('original_logic', '无')}\n\n"
    
    try:
        user_content = DOCTOR_TABLE_USER_TEMPLATE.format(tasks_description=tasks_desc)
        
        resp = client_doctor.invoke([
            {"role": "system", "content": DOCTOR_TABLE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ])
        content = getattr(resp, "content", str(resp))
        
        round_label = f"round_{round_num}"
        prescriptions = parse_markdown_table_to_list(content, round_label, round_num)
        
        print(f"   ✅ 医生根据状态共开出了 {len(prescriptions)} 张精细化处方。")
        return prescriptions
        
    except Exception as e:
        print(f"   ❌ 医生推理失败: {e}")
        return []

def run_coder_step(prescriptions, client_coder):
    """【修复版】强制清洗 Factor_Name，确保代码安全"""
    if not prescriptions: return []
    
    print(f"👨‍💻 [LLM6] 正在编写 {len(prescriptions)} 个因子的 Python 代码...")
    results = []
    
    for item in prescriptions:
        raw_f_name = item['Factor_Name']
        # 只保留字母、数字和下划线，其余全部转为下划线
        safe_f_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_f_name)
        item['Factor_Name'] = safe_f_name 
        
        print(f"   -> 正在编写安全代码: calculate_{safe_f_name} ...")
        
        try:
            prompt = CODER_PROMPT_TEMPLATE.format(
                name=safe_f_name, 
                formula=item['Formula'],
                logic=item['Logic']
            )
            
            resp = client_coder.invoke(prompt) 
            content = getattr(resp, "content", str(resp))
            
            if "```python" in content:
                clean_code = content.split("```python")[1].split("```")[0].strip()
            else:
                clean_code = content.replace("```", "").strip()
            
            item['Code'] = clean_code
            results.append(item)
        except Exception as e:
            print(f"      ❌ 生成失败 ({safe_f_name}): {e}")
            
    return results


def run_judge_workflow(full_factor_context, client_llm):
    """
    【初审判官】执行判官工作流：输入完整档案 -> 输出决策结果
    """
    if not full_factor_context:
        return []
        
    print(f"⚖️ [LLM4 初审] 正在审阅 {len(full_factor_context)} 份因子档案...")
    
    # 1. 序列化数据
    context_str = json.dumps(full_factor_context, ensure_ascii=False, indent=2)
    
    # 2. 构造 Prompt
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": JUDGE_USER_TEMPLATE.format(context_json=context_str)}
    ]
    
    # 3. 调用大模型
    try:
        response = client_llm.invoke(messages)
        content = getattr(response, "content", str(response))
        
        # 4. 清洗 Markdown 标记
        clean_content = content.replace("```json", "").replace("```", "").strip()
        decisions = json.loads(clean_content)
        
        return decisions
        
    except Exception as e:
        print(f"❌ 判官调用失败: {e}")
        print("Raw output:", content if 'content' in locals() else "None")
        return []