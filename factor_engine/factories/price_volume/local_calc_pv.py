# factor_engine/factories/price_volume/local_calc_pv.py

import pandas as pd
import numpy as np
import types
import re
from tqdm import tqdm

def load_data_as_matrices(folder_path):
    # 假设输入是一个包含所有数据的长表 feather
    df_long = pd.read_feather(folder_path)
    
    # 必要的预处理
    df_long['date'] = pd.to_datetime(df_long['date'])
    df_long = df_long[df_long['date'] >= '2016-01-01']
    
    # 核心：透视为矩阵字典
    print("   正在进行长表转宽表 (Pivot)...")
    matrix_dict = {}
    
    # 假设列名是小写
    fields = ['open', 'high', 'low', 'close', 'vol', 'amount', 'turnover_rate', 'pe', 'pb', 'total_mv', 'circ_mv']
    
    for col in fields:
        if col in df_long.columns:
            # pivot: Index=date, Columns=code
            matrix = df_long.pivot(index='date', columns='code', values=col)
            matrix = matrix.sort_index() # 确保时间有序
            matrix_dict[col] = matrix
    
    print(f"   转换完成，包含字段: {list(matrix_dict.keys())}")
    return matrix_dict



def extract_calculators_vectorized(LLM_output: str, ops_dict: dict) -> dict:
    """利用沙箱提取 LLM 生成的函数，注入外部传来的 ops_dict 算子库"""
    
    # 🌟 核心防 Bug 修改：用字符串乘法生成反引号，彻底避开网页 UI 的劫持！
    marker = "`" * 3
    clean_code = LLM_output.replace(marker + "python", "").replace(marker, "").strip()
    
    # 创建独立的模块沙箱
    mod = types.ModuleType("calc_mod")
    
    # 注入算子库和基础包
    mod.__dict__.update(ops_dict)
    mod.__dict__.update({"pd": pd, "np": np})

    # 编译并执行代码字符串
    try:
        exec(clean_code, mod.__dict__)
    except Exception as e:
        print(f"🚨 代码编译失败: {e}")
        return {}

    # 提取所有 calculate_ 开头的函数
    return {k: v for k, v in mod.__dict__.items() if k.startswith("calculate_") and callable(v)}


def apply_matrix_calculators(matrix_dict, calculators):
    results = {}
    from tqdm import tqdm
    
    for name, func in tqdm(calculators.items(), desc="矩阵运算中"):
        factor_name = name.replace("calculate_", "")
        try:
            # 这里的魔法是：我们只传一个 matrix_dict 进去
            # 但之前的 Prompt 里模型生成的是 def calc(df): close = df['close']
            # 所以只要 matrix_dict 像一个 dict (DataFrame 也是 dict-like)，代码就能跑通！
            # 因为 df['close'] 在 DataFrame 里是取列，在 dict 里是取 Key，语法完全一样！
            
            res = func(matrix_dict)
            
            # 结果校验
            if isinstance(res, pd.DataFrame):
                results[factor_name] = res
            else:
                print(f"⚠️ 因子 {factor_name} 返回的不是 DataFrame，跳过。")
                
        except Exception as e:
            print(f"❌ {factor_name} 计算失败: {e}")
            
    return results