from factor_engine.factories.price_volume.prompts_pv import *
from factor_engine.common.storage import save_output_to_file
from factor_engine.common.history import append_factor_history
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from factor_engine.common.deduplicator import parse_markdown_table
# 🚨 终极修复：把解析表格和重建表格的工具也一并导入！
from factor_engine.common.deduplicator import (
    filter_unique_factors_in_memory, 
    parse_markdown_table, 
    rebuild_markdown_table
)

def to_lc_messages(messages_payload):
    lc_messages = []
    for m in messages_payload:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


# def run_three_stages_with_memory(client1, client2, history_text, extra_instruction=""):
#     # Stage 1: Design
#     messages_stage1 = [
#         {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
#         {"role": "user", "content": build_stage1_user_content(history_text, extra_instruction)}
#     ]
    
#     print(">>> Calling Stage 1 (Factor Design)...")
#     resp1 = client1.invoke(to_lc_messages(messages_stage1))
#     text_1 = getattr(resp1, "content", str(resp1))
    
#     save_output_to_file(text_1, file_prefix="model_chain_1_output")
#     # append_factor_history(text_1)

#     # Stage 2: Code Gen
#     messages_stage2 = [
#         {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
#         {"role": "user", "content": build_stage2_user_content(text_1)}
#     ]
    
#     print(">>> Calling Stage 2 (Code Generation)...")
#     resp2 = client2.invoke(to_lc_messages(messages_stage2))
#     text_2 = getattr(resp2, "content", str(resp2))
    
#     save_output_to_file(text_2, file_prefix="model_chain_2_output")

#     # Stage 3: Code Check
#     messages_stage3 = [
#         {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
#         {"role": "user", "content": build_stage3_user_content(text_2)}
#     ]
    
#     print(">>> Calling Stage 3 (Code Correction)...")
#     resp3 = client2.invoke(to_lc_messages(messages_stage3))
#     text_3 = getattr(resp3, "content", str(resp3))
    
#     save_output_to_file(text_3, file_prefix="model_chain_3_output")

#     return text_3, text_1

import json
import os
# 🚨 导入我们刚才写好的内存级去重拦截器
from factor_engine.common.deduplicator import filter_unique_factors_in_memory 

def run_three_stages_with_memory(
    config, client1, client2, history_text, extra_instruction=""):
    # ==========================================
    # Stage 1: Design (因子逻辑构思)
    # ==========================================
    messages_stage1 = [
        {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
        {"role": "user", "content": build_stage1_user_content(history_text, extra_instruction)}
    ]
    
    print(">>> Calling Stage 1 (Factor Design)...")
    resp1 = client1.invoke(to_lc_messages(messages_stage1))
    text_1 = getattr(resp1, "content", str(resp1))
    
    save_output_to_file(text_1, "model_chain_1_output", config)
    
    # ==========================================
    # 🚨 拦截点：去重安检站 (The Interceptor)
    # ==========================================
    db_path = config.db_path
    filtered_text_1 = text_1 
    
    try:
        # 🚨 1. 核心改变：用表格解析器代替 JSON 解析器
        factor_list = parse_markdown_table(text_1)
        
        if not factor_list:
            print("⚠️ 未能在 LLM1 输出中找到有效表格，跳过去重。")
        else:
            # 2. 执行内存级查重拦截
            unique_factors = filter_unique_factors_in_memory(factor_list, db_path)
            
            if not unique_factors:
                print("🍵 [安检拉闸] 本批次生成的因子全是历史重复项，提前终止！")
                return "", "" 
                
            # 🚨 3. 核心改变：把合格的因子重新拼成表格！
            filtered_text_1 = rebuild_markdown_table(unique_factors)
            
            # 只把去重后的新因子写入大模型记忆库
            append_factor_history(filtered_text_1, config)
            
    except Exception as e:
        print(f"⚠️ [安检异常] 表格解析或去重失败，直接全量放行。报错: {e}")
        append_factor_history(text_1, config)
    # ==========================================
    # Stage 2: Code Gen (代码生成)
    # ==========================================
    messages_stage2 = [
        {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
        # 🚨 注意这里：喂给 LLM2 的变成了过滤后的 filtered_text_1
        {"role": "user", "content": build_stage2_user_content(filtered_text_1)} 
    ]
    
    print(f">>> Calling Stage 2 (Code Generation for {len(unique_factors) if 'unique_factors' in locals() else 'ALL'} factors)...")
    resp2 = client2.invoke(to_lc_messages(messages_stage2))
    text_2 = getattr(resp2, "content", str(resp2))
    
    save_output_to_file(text_2, "model_chain_2_output",config)

    # ==========================================
    # Stage 3: Code Check (代码纠错)
    # ==========================================
    messages_stage3 = [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {"role": "user", "content": build_stage3_user_content(text_2)}
    ]
    
    print(">>> Calling Stage 3 (Code Correction)...")
    resp3 = client2.invoke(to_lc_messages(messages_stage3))
    text_3 = getattr(resp3, "content", str(resp3))
    
    save_output_to_file(text_3, "model_chain_3_output",config)

    # 🚨 返回最终的代码 (text_3) 和 过滤后的设计原稿 (filtered_text_1)
    return text_3, filtered_text_1