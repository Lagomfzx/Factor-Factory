
import os
import uuid
import requests
from datetime import datetime
import pandas as pd
from factor_engine.common.platform_api import wait_and_save_remote_result, submit_to_platform
from factor_engine.common.runtime_env import get_platform_url, load_dotenv_files
from factor_engine.common.history import load_factor_history
from factor_engine.common.storage import index_and_save_job_details
# from factor_engine.common.platform_api import wait_and_save_remote_result
from factor_engine.factories.price_volume.llm_chains_pv import run_three_stages_with_memory
from factor_engine.factories.price_volume.local_calc_pv import extract_calculators_vectorized, apply_matrix_calculators
from factor_engine.operators.op_price_volume import combine_operator_lib_with_strategy, matrix_operators


load_dotenv_files()

# 🚨 仔细看这里：第一个参数已经改成了 matrix_dict
def run_pipeline_matrix_v2(
<<<<<<< ours
    config,matrix_dict, input_data, client1, client2, operator_lib_header):
=======
    config,matrix_dict, input_data, client1, client2, operator_lib_header, stage1_system_prompt=None):
>>>>>>> theirs
    """
    量价生成流水线 (重构解耦版)
    直接接收内存中的 matrix_dict，无需再传 folder_path
    """
    # 1. 模型生成
    history_text = load_factor_history(config,max_rounds=30)
    print("2️⃣ [模型生成] 正在调用 LLM...")
<<<<<<< ours
    factor_code_text, factor_table_text = run_three_stages_with_memory(config,client1, client2, history_text, extra_instruction=input_data)
=======
    factor_code_text, factor_table_text = run_three_stages_with_memory(
        config,
        client1,
        client2,
        history_text,
        extra_instruction=input_data,
        stage1_system_prompt=stage1_system_prompt,
    )
>>>>>>> theirs

    # 🚨🚨🚨 核心熔断机制：如果拿到的是空字符串，说明触发了全量拦截，直接提前结束本批次！
    if not factor_code_text or not factor_table_text:
        print("⚠️ 检测到流水线已被安检拦截，跳过后续所有投递和计算环节。")
        # 返回空值，让主控制台直接 continue 进入下一轮
        return None, "", "", None, []
    # 🚨🚨🚨

    final_py_code = combine_operator_lib_with_strategy(operator_lib_header, factor_code_text)

    # 2. 远程投递
    # url = platform base url from environment
    # session_id = str(uuid.uuid4())
    # payload = {"explain": factor_table_text, "py_code": final_py_code, "session_id": session_id, "exec_type": "cs"}
    
    # remote_job_id = None
    # try:
    #     print(f"🚀 [远程投递] 发送任务 Session: {session_id} ...")
    #     res = requests.post(url + "/jobs", json=payload)
    #     if res.status_code == 200:
    #         remote_job_id = res.json().get('job_id') or res.json().get('id')
    #         print(f"✅ 投递成功! 远程 Job ID: {remote_job_id}")
    #     else:
    #         print(f"❌ 投递失败: {res.status_code} - {res.text}")
    # except Exception as e: 
    #     print(f"⚠️ 网络出错: {e}")



    # 2. 远程投递 (极简调用)
    remote_job_id = submit_to_platform(py_code=final_py_code, explain_text=factor_table_text)

        # 保存 Job ID 索引 (极其重要，供给优化模块和前端)
    if remote_job_id:
        index_and_save_job_details(remote_job_id,
                                   factor_table_text, 
                                   factor_code_text,
                                   config)

    # 3. 本地计算
    print("3️⃣ [本地计算] 开始极速矩阵运算...")
    try:
        ops_dict = matrix_operators() # 获取量价算子字典
        calculators = extract_calculators_vectorized(factor_code_text, ops_dict)
        factor_results = apply_matrix_calculators(matrix_dict, calculators)
        
        round_dir_name = str(remote_job_id) if remote_job_id else f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # run_dir = os.path.join(base_out, round_dir_name)
        run_dir = os.path.join(config.factor_out_dir, round_dir_name)
        os.makedirs(run_dir, exist_ok=True)
        
        # saved_count = 0
        # for fname, factor_df in factor_results.items():
        #     if isinstance(factor_df, pd.DataFrame):
        #         factor_df.reset_index().to_feather(os.path.join(run_dir, f"{fname}.feather"))
        #         saved_count += 1
        saved_count = 0
        for fname, factor_df in factor_results.items():
            if isinstance(factor_df, pd.DataFrame):
                # 1. 释放索引（把日期变成普通列）
                save_df = factor_df.reset_index()
                
                # 🚨 核心防警告：强制把所有列名转为字符串！
                save_df.columns = save_df.columns.astype(str)
                
                # 2. 极速落盘
                # save_df.to_feather(os.path.join(run_dir, f"{fname}.feather"))
                # saved_count += 1
                # 🚨 核心修改：从 to_feather 改为 to_parquet
                save_path = os.path.join(run_dir, f"{fname}.parquet")
                save_df.to_parquet(save_path)
                saved_count += 1
        print(f"✅ 本地保存了 {saved_count} 个因子至: {run_dir}")
    except Exception as e:
        print(f"❌ 本地计算出错: {e}")

    # 4. 远程同步
    res_json = None
    if remote_job_id:
        print("5️⃣ [远程获取] 准备同步平台结果...")
        url = get_platform_url()
        
        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{remote_job_id}.json"
        res_json = wait_and_save_remote_result(
            base_url=url, 
            job_id=remote_job_id,
            # save_path=os.path.join(remote_calculate_path, file_name)
            save_path=os.path.join(config.remote_result_dir, file_name)
        )

    print("🎉 Pipeline (Matrix) 生成阶段执行完毕！")
    return remote_job_id, factor_table_text, factor_code_text, res_json
