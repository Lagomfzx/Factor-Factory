# factor_engine/data_bridge.py

import json
import re
from pathlib import Path
from factor_engine.common.storage import sync_to_v6_1_registry

def load_json_data(filepath):
    """读取平台返回的 JSON 结果文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error: {e}")
        return None

def build_judge_context(clean_metrics_list, llm1_raw_text, llm3_raw_text):
    """
    【数据整合器】将 LLM1逻辑、LLM3代码、平台绩效 整合为 LLM4 所需的格式
    """
    # 1. 提取逻辑字典
    logic_map = {}
    lines = llm1_raw_text.strip().split('\n')
    for line in lines:
        if '|' in line and '因子名称' not in line and '---' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                raw_name = parts[1].replace('**', '').replace('`', '').strip()
                raw_logic = parts[3].strip()
                if raw_name: logic_map[raw_name] = raw_logic

    # 2. 提取代码字典
    code_map = {}
    clean_code_text = llm3_raw_text.replace('```python', '').replace('```', '')
    pattern = r"(def\s+calculate_(\w+)\s*\(.*?\):.*?)(?=\ndef\s+calculate_|\Z)"
    matches = re.findall(pattern, clean_code_text, re.DOTALL)
    for full_code, factor_name in matches:
        code_map[factor_name] = full_code.strip()

    # 3. 核心整合
    final_context = []
    for item in clean_metrics_list:
        f_name = item.get('Name')
        final_context.append({
            "name": f_name,
            "logic": logic_map.get(f_name, "逻辑描述未匹配到"), 
            "code": code_map.get(f_name, "# 代码未匹配到"),
            "metrics": item
        })
    return final_context

def get_optimization_queue(decisions, original_context):
    """
    【桥接核心】从初次判决中，提取出需要优化的因子，转换为进化引擎的种子格式
    """
    queue = []
    context_map = {item['name']: item for item in original_context}
    
    for case in decisions:
        if case['decision'] == 'OPTIMIZE':
            f_name = case['name']
            source_data = context_map.get(f_name)
            
            if source_data:
                queue.append({
                    "name": f_name,
                    "original_code": source_data['code'],
                    "original_logic": source_data['logic'],
                    "diagnosis": case['diagnosis'], 
                    "reason": case['reason'],
                    # ⚠️ 关键：赋予它们初始的 Action 和计数器
                    "action": "PIVOT",
                    "pivot_count": 0
                })
    return queue

import os
import pandas as pd
from factor_engine.common.storage import sync_to_v6_1_registry

# def extract_and_sync_genius_factors(decisions, gen_job_id, config):
#     """
#     【正统提档器】
#     回归初心：根据 LLM4 的录取名单，直接去 V6 原始总库调取完整档案，送入 V6.1。
#     """
#     print("🌟 正在将初审通过的【天才因子】从 V6 提档至 V6.1 精品库...")
    
#     # 1. 拿到被录取的名单 (KEEP 因子名)
#     kept_names = []
#     for dec in decisions:
#         if str(dec.get('decision', '')).strip().upper() == 'KEEP':
#             kept_names.append(str(dec.get('name', '')))
            
#     if not kept_names:
#         print("🌟 初审强力拦截：发掘出 0 个天才因子！")
#         return []
        
#     # 2. 回归初心：去 V6 仓库提原始档案！
#     v6_path = "mydata/output/job_id_output/job_id_output_v6.csv"
#     if not os.path.exists(v6_path):
#         print("⚠️ 找不到 V6 总库文件，提档失败！")
#         return []
        
#     try:
#         v6_df = pd.read_csv(v6_path)
#         # 缩小搜索范围：只找当前批次的
#         batch_df = v6_df[v6_df['Job_ID'] == gen_job_id]
        
#         # 🚨 核心修复：模糊匹配！对付大模型乱加 _II 后缀的问题
#         matched_factors = []
#         for _, row in batch_df.iterrows():
#             v6_name = str(row['Factor_Name'])
#             for k_name in kept_names:
#                 # 只要互相包含（比如 Alpha_XXX_II 包含 Alpha_XXX），就视为匹配成功！
#                 if k_name in v6_name or v6_name in k_name:
#                     matched_factors.append(row.to_dict())
#                     break  # 找到了就跳出内层循环，找下一个
                    
#         print(f"🌟 初审强力拦截：成功从 V6 发掘出 {len(matched_factors)} 个天才因子的完整档案！")
        
#         # 3. 抄送 6.1 精品库
#         if matched_factors:
#             sync_to_v6_1_registry(gen_job_id, matched_factors)
            
#         return matched_factors
        
#     except Exception as e:
#         print(f"⚠️ 从 V6 库读取天才因子失败: {e}")
#         return []

import pandas as pd
import os
from factor_engine.common.storage import sync_to_v6_1_registry

def extract_and_sync_genius_factors(decisions, gen_job_id, config):
    """
    【正统提档器】(彻底解耦版)
    回归初心：根据 LLM4 的录取名单，直接去当前车间的总库调取完整档案，送入精品库。
    """
    version_tag = config.version.upper()
    print(f"🌟 正在将初审通过的【天才因子】从 {version_tag} 提档至精品库...")
    
    # 1. 拿到被录取的名单 (KEEP 因子名)
    kept_names = []
    for dec in decisions:
        if str(dec.get('decision', '')).strip().upper() == 'KEEP':
            kept_names.append(str(dec.get('name', '')))
            
    if not kept_names:
        print("🌟 初审强力拦截：发掘出 0 个天才因子！")
        return []
        
    # 2. 🚨 核心修复 1：回归初心，去 config 里拿当前车间的总账本路径！
    db_path = config.registry_csv
    
    if not os.path.exists(db_path):
        print(f"⚠️ 找不到 {version_tag} 总库文件，提档失败！路径: {db_path}")
        return []
        
    try:
        v6_df = pd.read_csv(db_path)
        # 缩小搜索范围：只找当前批次的
        batch_df = v6_df[v6_df['Job_ID'] == gen_job_id]
        
        # 模糊匹配！对付大模型乱加 _II 后缀的问题
        matched_factors = []
        for _, row in batch_df.iterrows():
            v6_name = str(row['Factor_Name'])
            for k_name in kept_names:
                # 只要互相包含（比如 Alpha_XXX_II 包含 Alpha_XXX），就视为匹配成功！
                if k_name in v6_name or v6_name in k_name:
                    matched_factors.append(row.to_dict())
                    break  # 找到了就跳出内层循环，找下一个
                    
        print(f"🌟 初审强力拦截：成功从 {version_tag} 发掘出 {len(matched_factors)} 个天才因子的完整档案！")
        
        # 3. 抄送精品库
        if matched_factors:
            # 🚨 核心修复 2：千万别忘了把 config 图纸传给这个存储工具！
            sync_to_v6_1_registry(gen_job_id, matched_factors, config)
            
        return matched_factors
        
    except Exception as e:
        print(f"⚠️ 从 {version_tag} 库读取天才因子失败: {e}")
        return []