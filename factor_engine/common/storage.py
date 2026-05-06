# # factor_engine/common/storage.py
# import re
# from datetime import datetime
# import glob
# import pandas as pd
# import os
# # import datetime
# import copy

# class OptimizationStorage:
#     def __init__(self, file_path="mydata/output/opt_data/job_id_output/factor_evolution_history.csv"):
#         self.file_path = file_path
#         self.cols = ["Job_ID", "Parent_Name", "Factor_Name", "Logic", "Formula", "Code"]
#         os.makedirs(os.path.dirname(file_path), exist_ok=True)

#     def save_prescriptions(self, job_id, data_list):
#         if not data_list: return
#         to_save = copy.deepcopy(data_list)
#         for item in to_save:
#             item['Job_ID'] = job_id
#             if 'Code' not in item: item['Code'] = ""
            
#         df = pd.DataFrame(to_save)
#         for col in self.cols:
#             if col not in df.columns: df[col] = ""
#         df = df[self.cols]
        
#         header = not os.path.exists(self.file_path)
#         df.to_csv(self.file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
#         print(f"💾 [存储] 已追加 {len(df)} 条处方记录到 {os.path.basename(self.file_path)}")

#     def update_codes(self, job_id, data_with_codes):
#         if not os.path.exists(self.file_path): 
#             print("⚠️ [存储] 找不到目标文件，无法回填代码。")
#             return
        
#         df = pd.read_csv(self.file_path)
#         df['Job_ID'] = df['Job_ID'].astype(str)
#         df['Factor_Name'] = df['Factor_Name'].astype(str)
#         job_id_str = str(job_id)
        
#         updated = 0
#         code_map = {str(item['Factor_Name']): item['Code'] for item in data_with_codes if item.get('Code')}
        
#         for idx, row in df.iterrows():
#             f_name = str(row['Factor_Name'])
#             if str(row['Job_ID']) == job_id_str and f_name in code_map:
#                 if pd.isna(row['Code']) or row['Code'] == "":
#                     df.at[idx, 'Code'] = code_map[f_name]
#                     updated += 1
                    
#         df.to_csv(self.file_path, index=False, encoding='utf-8-sig')
#         print(f"💾 [存储] 已成功回填 {updated} 条因子的实现代码。")

#     def save_full_records(self, round_label, full_data_list):
#         if not full_data_list: return
#         # 注意这里将 round_label 当做 Job_ID 的位置存下来，或者你可以存真正的 Job_ID
#         for item in full_data_list:
#             item['Job_ID'] = round_label 
            
#         df = pd.DataFrame(full_data_list)
#         for col in self.cols:
#             if col not in df.columns: df[col] = ""
#         df = df[self.cols]
        
#         header = not os.path.exists(self.file_path)
#         df.to_csv(self.file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
#         print(f"💾 [存储] 一步到位：已保存 {len(df)} 条完整因子档案。")
        
#     def save_judge_log(self, round_idx, judge_results):
#         if not judge_results: return
#         log_path = "mydata/output/opt_data/job_id_output/research_notes.csv"
#         df = pd.DataFrame(judge_results)
#         df['Round'] = round_idx
#         header = not os.path.exists(log_path)
#         df.to_csv(log_path, mode='a', header=header, index=False, encoding='utf-8-sig')
#         print(f"📗 [研究笔记] 已记录第 {round_idx} 轮的研发心得。")
        
#     def save_decisions(self, round_label, decisions_list):
#         if not decisions_list: return
#         file_path = "mydata/output/opt_data/job_id_output/research_referee_notes.csv"
#         df = pd.DataFrame(decisions_list)
#         df.insert(0, "Round", round_label)
#         header = not os.path.exists(file_path)
#         df.to_csv(file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
#         print(f"📄 [裁判席] 战略判决书已存档至: research_referee_notes.csv")

# def tag_kept_factors(decisions, job_id, tag_file_path="mydata/output/opt_data/factor_tags_registry.csv"):
#     tags_list = []
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     print(f"🏷️ [打标] 正在为 {len(decisions)} 个因子登记状态...")
    
#     for dec in decisions:
#         if dec['decision'] != 'KEEP':
#             continue
#         record = {
#             "Update_Time": timestamp,
#             "Job_ID": job_id,
#             "Factor_Name": dec['name'],
#             "Status": dec['decision'], 
#             "Judge_Reason": dec['reason'],
#             "Diagnosis": dec.get('diagnosis', '') 
#         }
#         tags_list.append(record)
#         if dec['decision'] == 'KEEP':
#             print(f"   🌟 标记为优选: {dec['name']}")

#     if not tags_list: return

#     df_new = pd.DataFrame(tags_list)
#     os.makedirs(os.path.dirname(tag_file_path), exist_ok=True)
    
#     if os.path.exists(tag_file_path):
#         df_new.to_csv(tag_file_path, mode='a', header=False, index=False, encoding='utf-8-sig')
#     else:
#         cols = ["Update_Time", "Job_ID", "Factor_Name", "Status", "Judge_Reason", "Diagnosis"]
#         df_new = df_new[cols]
#         df_new.to_csv(tag_file_path, index=False, encoding='utf-8-sig')
#     print(f"✅ 状态标签已更新至: {os.path.basename(tag_file_path)}")


# # factor_engine/storage.py 的末尾添加：

# def sync_to_streamlit_registry(job_id, factor_tasks, save_path="mydata/output/job_id_output/job_id_output_v6.csv"):
#     """
#     【可视化兼容接口】将优化模块生成的因子，以与生成模块完全相同的格式，追加到总库中。
#     确保 Streamlit 前端能够无缝读取和展示进化后的因子。
#     """
#     if not factor_tasks:
#         return
        
#     print(f"🔗 [可视化对接] 正在将 {len(factor_tasks)} 个优化因子同步至 Streamlit 主注册表...")
    
#     # 将字典列表转为 DataFrame
#     df = pd.DataFrame(factor_tasks)
#     df['Job_ID'] = job_id
    
#     # 强制对齐 Streamlit 需要的列（顺序必须一致）
#     save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    
#     # 补全可能缺失的列（防御性编程）
#     for col in save_cols:
#         if col not in df.columns:
#             df[col] = "N/A"
            
#     df = df[save_cols]
    
#     # 追加保存
#     os.makedirs(os.path.dirname(save_path), exist_ok=True)
#     header = not os.path.exists(save_path)
#     df.to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    
#     print(f"✅ [可视化对接] 成功同步，前端可通过 Job_ID: {job_id} 进行查看。")


# # 追加到 factor_engine/common/storage.py 尾部：



# # -------------------- 文件保存逻辑 --------------------
# def save_output_to_file(output: str, file_prefix: str, save_directory: str = 'mydata/output/llm_output/llm_output_v6') -> str:
#     os.makedirs(save_directory, exist_ok=True)
#     filename = os.path.join(save_directory, f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
#     with open(filename, 'w', encoding='utf-8') as f:
#         f.write(output)
#     print(f"文件已保存: {filename}")
#     return filename


# # -------------------- 合并指定类型的 chain 输出（支持 model_chain_1/2/3...） --------------------
# def combine_model_chain_outputs(
#     input_dir: str = 'mydata/output/llm_output/llm_output_v6',
#     output_dir: str = 'mydata/output/llm_output/combined_v6',
#     chain_prefix: str = "model_chain_3_output_",  # 如 "model_chain_2_output_"
#     # chain_prefix:str,
#     include_timestamp: bool = True
# ):
#     """
#     将 input_dir 中所有以 {chain_prefix}*_.txt 结尾的文件按时间戳排序，
#     合并到 output_dir 下对应的 combined_{chain_prefix}.txt 文件中。

#     参数：
#         input_dir: 原始输出文件所在目录
#         output_dir: 合并后的文件保存目录
#         chain_prefix: 要合并的文件前缀，如 "model_chain_1_output_"
#         include_timestamp: 是否在合并内容中标注时间
#     """
#     import os
#     import glob
#     from datetime import datetime

#     # 确保输出目录存在
#     os.makedirs(output_dir, exist_ok=True)

#     # 构建搜索模式：model_chain_1_output_YYYYMMDD_HHMMSS.txt
#     pattern = os.path.join(input_dir, f"{chain_prefix}*_*.txt")
#     files = glob.glob(pattern)

#     if not files:
#         print(f"⚠️ 在 {input_dir} 中未找到任何匹配 {chain_prefix}*_.txt 的文件。")
#         return

#     def extract_time(filepath):
#         basename = os.path.basename(filepath)
#         try:
#             # 提取 time_str: model_chain_1_output_20251110_163759.txt -> 20251110_163759
#             time_str = basename.replace(chain_prefix, "").replace(".txt", "")
#             date_part, time_part = time_str.split("_")
#             dt_str = f"{date_part}_{time_part}"
#             return datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
#         except Exception as e:
#             print(f"无法解析时间戳: {basename}, 错误: {e}")
#             return datetime.min

#     # 按时间排序
#     sorted_files = sorted(files, key=extract_time)

#     # 输出文件名基于 chain_prefix 定制
#     safe_prefix = chain_prefix.rstrip("_")  # 去掉末尾下划线便于命名
#     output_file = os.path.join(output_dir, f"combined_{safe_prefix}.txt")

#     print(f"📦 发现 {len(sorted_files)} 个 '{chain_prefix}' 类型文件，开始合并至:\n   {output_file}")

#     with open(output_file, 'w', encoding='utf-8') as out_f:
#         for file_path in sorted_files:
#             basename = os.path.basename(file_path)
#             timestamp_str = basename.replace(chain_prefix, "").replace(".txt", "")
#             date_part, time_part = timestamp_str.split("_")
#             formatted_time = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:]}"

#             try:
#                 with open(file_path, 'r', encoding='utf-8') as in_f:
#                     content = in_f.read().strip()
#                     if not content:
#                         content = "<空文件>"

#                 # 写入分隔块
#                 out_f.write(f"\n{'='*60}\n")
#                 out_f.write(f"📌 源文件: {basename}\n")
#                 if include_timestamp:
#                     out_f.write(f"🕒 生成时间: {formatted_time}\n")
#                 out_f.write(f"{'-'*60}\n")
#                 out_f.write(content)
#                 out_f.write(f"\n{'='*60}\n\n")

#             except Exception as e:
#                 print(f"❌ 读取文件失败: {file_path}, 错误: {e}")

#     print(f"✅ 已完成合并: {len(sorted_files)} 个文件 → {output_file}")



# def index_and_save_job_details(job_id, llm1_text, llm3_text, save_path="mydata/output/job_id_output/job_id_output_v6.csv"):
#     """
#     【升级版】解析并保存：因子名、原始公式、逻辑解释、实现代码
#     """
    
#     # 1. 解析 LLM1 (Markdown 表格)
#     logic_list = []
#     lines = llm1_text.split('\n')
#     for line in lines:
#         # 过滤有效行
#         if '|' in line and '因子名称' not in line and '---' not in line:
#             parts = [p.strip() for p in line.split('|')]
#             # Markdown 表格通常分割后 index 为: [空, 名字, 公式, 解释, 空]
#             if len(parts) >= 4:
#                 raw_name = parts[1].replace('**', '').replace('`', '').strip()
                
#                 # 🟢 新增：提取公式列 (去除代码反引号 `)
#                 raw_formula = parts[2].replace('`', '').strip()
                
#                 logic_desc = parts[3].strip()
                
#                 logic_list.append({
#                     'Factor_Name': raw_name, 
#                     'Formula': raw_formula,  # <--- 这里保留了公式
#                     'Logic': logic_desc
#                 })
#     df_logic = pd.DataFrame(logic_list)

#     # 2. 解析 LLM3 (Python 代码)
#     code_list = []
#     chunks = llm3_text.split('def ')
#     for chunk in chunks:
#         if not chunk.strip(): continue
#         first_line = chunk.split('\n')[0]
#         match = re.search(r'calculate_(\w+)\(df\):', first_line)
#         if match:
#             factor_name = match.group(1)
#             full_code = "def " + chunk.strip()
#             code_list.append({'Factor_Name': factor_name, 'Code': full_code})
#     df_code = pd.DataFrame(code_list)

#     # 3. 对齐与合并
#     if df_logic.empty or df_code.empty:
#         print(f"⚠️ Job {job_id} 解析为空，请检查输入文本。")
#         return

#     merged_df = pd.merge(df_logic, df_code, on='Factor_Name', how='inner')
    
#     # 4. 生成 ID
#     merged_df = merged_df.sort_values('Factor_Name').reset_index(drop=True)
# #     merged_df['Unique_ID'] = [f"{job_id}_{i+1:02d}" for i in range(len(merged_df))]
#     merged_df['Job_ID'] = job_id

#     # 5. 保存 (列顺序优化)
#     # 现在的表格将非常完美：ID -> 名字 -> 公式 -> 解释 -> 代码
# #     save_cols = ['Unique_ID', 'Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
#     save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    
#     os.makedirs(os.path.dirname(save_path), exist_ok=True)
#     header = not os.path.exists(save_path)
#     merged_df[save_cols].to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    
#     print(f"✅ [索引更新] Job {job_id} 已录入 {len(merged_df)} 个因子 (含公式列)。")


# def sync_to_v6_1_registry(job_id, kept_factors_list, save_path="mydata/output/job_id_output/job_id_output_v6.1.csv"):
#     """
#     【精选库接口】
#     严格执行前端契约：只存入被 LLM4 判为 KEEP 的优质因子。
#     数据结构与 v6 保持绝对一致。
#     """
#     if not kept_factors_list:
#         return
        
#     df = pd.DataFrame(kept_factors_list)
#     df['Job_ID'] = job_id
    
#     # 强制对齐 5 大标准列，满足前端读取契约
#     save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    
#     for col in save_cols:
#         if col not in df.columns:
#             df[col] = "N/A"
            
#     df = df[save_cols]
    
#     os.makedirs(os.path.dirname(save_path), exist_ok=True)
#     header = not os.path.exists(save_path)
#     df.to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    
#     print(f"🌟 [精选入库] 已将 {len(df)} 个 KEEP 因子同步至 v6.1 专属大表！")

# factor_engine/common/storage.py
import re
from datetime import datetime
import glob
import pandas as pd
import os
import copy

class OptimizationStorage:
    # 🚨 构造函数不再接收写死的路径，而是接收 config 图纸！
    def __init__(self, config):
        self.config = config
        self.file_path = config.evolution_history_csv
        self.cols = ["Job_ID", "Parent_Name", "Factor_Name", "Logic", "Formula", "Code"]

    def save_prescriptions(self, job_id, data_list):
        if not data_list: return
        to_save = copy.deepcopy(data_list)
        for item in to_save:
            item['Job_ID'] = job_id
            if 'Code' not in item: item['Code'] = ""
            
        df = pd.DataFrame(to_save)
        for col in self.cols:
            if col not in df.columns: df[col] = ""
        df = df[self.cols]
        
        header = not os.path.exists(self.file_path)
        df.to_csv(self.file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
        print(f"💾 [存储] 已追加 {len(df)} 条处方记录到 {os.path.basename(self.file_path)}")

    def update_codes(self, job_id, data_with_codes):
        if not os.path.exists(self.file_path): 
            print("⚠️ [存储] 找不到目标文件，无法回填代码。")
            return
        
        df = pd.read_csv(self.file_path)
        df['Job_ID'] = df['Job_ID'].astype(str)
        df['Factor_Name'] = df['Factor_Name'].astype(str)
        job_id_str = str(job_id)
        
        updated = 0
        code_map = {str(item['Factor_Name']): item['Code'] for item in data_with_codes if item.get('Code')}
        
        for idx, row in df.iterrows():
            f_name = str(row['Factor_Name'])
            if str(row['Job_ID']) == job_id_str and f_name in code_map:
                if pd.isna(row['Code']) or row['Code'] == "":
                    df.at[idx, 'Code'] = code_map[f_name]
                    updated += 1
                    
        df.to_csv(self.file_path, index=False, encoding='utf-8-sig')
        print(f"💾 [存储] 已成功回填 {updated} 条因子的实现代码。")

    def save_full_records(self, round_label, full_data_list):
        if not full_data_list: return
        for item in full_data_list:
            item['Job_ID'] = round_label 
            
        df = pd.DataFrame(full_data_list)
        for col in self.cols:
            if col not in df.columns: df[col] = ""
        df = df[self.cols]
        
        header = not os.path.exists(self.file_path)
        df.to_csv(self.file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
        print(f"💾 [存储] 一步到位：已保存 {len(df)} 条完整因子档案。")
        
    def save_judge_log(self, round_idx, judge_results):
        if not judge_results: return
        log_path = self.config.research_notes_csv # 🚨 使用 config
        df = pd.DataFrame(judge_results)
        df['Round'] = round_idx
        header = not os.path.exists(log_path)
        df.to_csv(log_path, mode='a', header=header, index=False, encoding='utf-8-sig')
        print(f"📗 [研究笔记] 已记录第 {round_idx} 轮的研发心得。")
        
    def save_decisions(self, round_label, decisions_list):
        if not decisions_list: return
        file_path = self.config.referee_notes_csv # 🚨 使用 config
        df = pd.DataFrame(decisions_list)
        df.insert(0, "Round", round_label)
        header = not os.path.exists(file_path)
        df.to_csv(file_path, mode='a', header=header, index=False, encoding='utf-8-sig')
        print(f"📄 [裁判席] 战略判决书已存档至: {os.path.basename(file_path)}")

# =====================================================================
# 独立存储函数（全部引入 config）
# =====================================================================

def tag_kept_factors(decisions, job_id, config): # 🚨 传入 config
    tags_list = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_file_path = config.tags_registry_csv # 🚨 使用 config
    
    print(f"🏷️ [打标] 正在为 {len(decisions)} 个因子登记状态...")
    for dec in decisions:
        if dec['decision'] != 'KEEP': continue
        record = {
            "Update_Time": timestamp, "Job_ID": job_id, "Factor_Name": dec['name'],
            "Status": dec['decision'], "Judge_Reason": dec['reason'], "Diagnosis": dec.get('diagnosis', '') 
        }
        tags_list.append(record)
        print(f"   🌟 标记为优选: {dec['name']}")

    if not tags_list: return
    df_new = pd.DataFrame(tags_list)
    if os.path.exists(tag_file_path):
        df_new.to_csv(tag_file_path, mode='a', header=False, index=False, encoding='utf-8-sig')
    else:
        cols = ["Update_Time", "Job_ID", "Factor_Name", "Status", "Judge_Reason", "Diagnosis"]
        df_new = df_new[cols]
        df_new.to_csv(tag_file_path, index=False, encoding='utf-8-sig')
    print(f"✅ 状态标签已更新至: {os.path.basename(tag_file_path)}")

def sync_to_streamlit_registry(job_id, factor_tasks, config): # 🚨 传入 config
    if not factor_tasks: return
    save_path = config.registry_csv # 🚨 替代原来的 job_id_output_v6.csv
    print(f"🔗 [可视化对接] 同步至总库 ({os.path.basename(save_path)})...")
    df = pd.DataFrame(factor_tasks)
    df['Job_ID'] = job_id
    save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    for col in save_cols:
        if col not in df.columns: df[col] = "N/A"
    df = df[save_cols]
    header = not os.path.exists(save_path)
    df.to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    print(f"✅ [可视化对接] 同步成功！")

def save_output_to_file(output: str, file_prefix: str, config) -> str: # 🚨 传入 config
    save_directory = config.llm_output_dir # 🚨 动态路径
    filename = os.path.join(save_directory, f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"文件已保存: {filename}")
    return filename

def index_and_save_job_details(job_id, llm1_text, llm3_text, config): # 🚨 传入 config
    save_path = config.registry_csv # 🚨 替代 job_id_output_v6.csv
    logic_list = []
    for line in llm1_text.split('\n'):
        if '|' in line and '因子名称' not in line and '---' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                raw_name = parts[1].replace('**', '').replace('`', '').strip()
                raw_formula = parts[2].replace('`', '').strip()
                logic_desc = parts[3].strip()
                logic_list.append({'Factor_Name': raw_name, 'Formula': raw_formula, 'Logic': logic_desc})
    df_logic = pd.DataFrame(logic_list)

    code_list = []
    for chunk in llm3_text.split('def '):
        if not chunk.strip(): continue
        first_line = chunk.split('\n')[0]
        # match = re.search(r'calculate_(\w+)\(df\):', first_line)
        match = re.search(r'calculate_(\w+)\s*\([^)]*\)\s*:', first_line)

        if match:
            factor_name = match.group(1)
            full_code = "def " + chunk.strip()
            code_list.append({'Factor_Name': factor_name, 'Code': full_code})
    df_code = pd.DataFrame(code_list)

    if df_logic.empty or df_code.empty:
        print(f"⚠️ Job {job_id} 解析为空。")
        return

    merged_df = pd.merge(df_logic, df_code, on='Factor_Name', how='inner')
    merged_df = merged_df.sort_values('Factor_Name').reset_index(drop=True)
    merged_df['Job_ID'] = job_id
    save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    
    header = not os.path.exists(save_path)
    merged_df[save_cols].to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    print(f"✅ [索引更新] Job {job_id} 已录入 {len(merged_df)} 个因子。")

def sync_to_v6_1_registry(job_id, kept_factors_list, config): # 🚨 传入 config
    if not kept_factors_list: return
    save_path = config.premium_registry_csv # 🚨 替代 v6.1.csv
    df = pd.DataFrame(kept_factors_list)
    df['Job_ID'] = job_id
    save_cols = ['Job_ID', 'Factor_Name', 'Formula', 'Logic', 'Code']
    for col in save_cols:
        if col not in df.columns: df[col] = "N/A"
    df = df[save_cols]
    
    header = not os.path.exists(save_path)
    df.to_csv(save_path, mode='a', header=header, index=False, encoding='utf-8-sig')
    print(f"🌟 [精选入库] 已同步至 {os.path.basename(save_path)} 专属大表！")