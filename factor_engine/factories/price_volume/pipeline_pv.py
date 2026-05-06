from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

from factor_engine.common.history import load_factor_history
from factor_engine.common.platform_api import submit_to_platform, wait_and_save_remote_result
from factor_engine.common.runtime_env import get_platform_url, load_dotenv_files
from factor_engine.common.storage import index_and_save_job_details
from factor_engine.factories.price_volume.llm_chains_pv import run_three_stages_with_memory
from factor_engine.factories.price_volume.local_calc_pv import (
    apply_matrix_calculators,
    extract_calculators_vectorized,
)
from factor_engine.operators.op_price_volume import (
    combine_operator_lib_with_strategy,
    matrix_operators,
)


load_dotenv_files()


def _strip_code_fences(text: str) -> str:
    if not text:
        return text
    return text.replace("```python", "").replace("```", "").strip()


def run_pipeline_matrix_v2(
    config,
    matrix_dict,
    input_data,
    client1,
    client2,
    operator_lib_header,
    stage1_system_prompt=None,
):
    """
    Price-volume generation pipeline.
    Accepts in-memory matrices directly and returns:
    remote_job_id, factor_table_text, factor_code_text, remote_result_json
    """
    history_text = load_factor_history(config, max_rounds=30)
    print("2️⃣ [模型生成] 正在调用 LLM...")
    factor_code_text, factor_table_text = run_three_stages_with_memory(
        config,
        client1,
        client2,
        history_text,
        extra_instruction=input_data,
        stage1_system_prompt=stage1_system_prompt,
    )

    if not factor_code_text or not factor_table_text:
        print("⚠️ 检测到流水线已被安检拦截，跳过后续所有投递和计算环节。")
        return None, "", "", None

    clean_factor_code_text = _strip_code_fences(factor_code_text)
    final_py_code = combine_operator_lib_with_strategy(
        operator_lib_header,
        clean_factor_code_text,
    )

    remote_job_id = submit_to_platform(
        py_code=final_py_code,
        explain_text=factor_table_text,
    )

    if remote_job_id:
        index_and_save_job_details(
            remote_job_id,
            factor_table_text,
            clean_factor_code_text,
            config,
        )

    print("3️⃣ [本地计算] 开始极速矩阵运算...")
    try:
        if not matrix_dict:
            print("⚠️ matrix_dict 为空，跳过本地矩阵计算。")
        else:
            ops_dict = matrix_operators()
            calculators = extract_calculators_vectorized(clean_factor_code_text, ops_dict)

            if not calculators:
                print("⚠️ 没有解析出有效的 calculator，跳过本地保存。")
            else:
                factor_results = apply_matrix_calculators(matrix_dict, calculators)
                round_dir_name = (
                    str(remote_job_id)
                    if remote_job_id
                    else f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                run_dir = os.path.join(config.factor_out_dir, round_dir_name)
                os.makedirs(run_dir, exist_ok=True)

                saved_count = 0
                for factor_name, factor_df in factor_results.items():
                    if not isinstance(factor_df, pd.DataFrame):
                        continue

                    save_df = factor_df.reset_index()
                    save_df.columns = save_df.columns.astype(str)
                    save_path = os.path.join(run_dir, f"{factor_name}.parquet")
                    save_df.to_parquet(save_path)
                    saved_count += 1

                print(f"✅ 本地保存了 {saved_count} 个因子至: {run_dir}")
    except Exception as exc:
        print(f"❌ 本地计算出错: {exc}")

    res_json = None
    if remote_job_id:
        print("5️⃣ [远程获取] 准备同步平台结果...")
        remote_url = get_platform_url()
        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{remote_job_id}.json"
        res_json = wait_and_save_remote_result(
            base_url=remote_url,
            job_id=remote_job_id,
            save_path=os.path.join(config.remote_result_dir, file_name),
        )

    print("🎉 Pipeline (Matrix) 生成阶段执行完毕！")
    return remote_job_id, factor_table_text, clean_factor_code_text, res_json
