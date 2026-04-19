# factor_engine/operators/op_fundamental

import pandas as pd
import numpy as np
import os
import ast
import traceback

# =========================================================================
# 1. 全局算子定义 (扁平化结构，解决 NameError)
# =========================================================================
EPS = 1e-10
DAYS_PER_QUARTER = 60

# def _ensure_df(x): return x.to_frame() if isinstance(x, pd.Series) else x
# def _check_window(d): return max(1, int(d * DAYS_PER_QUARTER))

# 🔥 核心修改：不再需要 DAYS_PER_QUARTER，所有窗口 d 直接代表“期数”
def _ensure_df(x): return x.to_frame() if isinstance(x, pd.Series) else x
def _check_window(d): return max(1, int(d)) # d=1 就是回溯1个切片

# --- 基础截面 ---
def CS_Rank(x): return _ensure_df(x).rank(axis=1, pct=True)

# --- 高级截面 (行业中性) ---
def CS_Indus_Rank(x, indus_matrix):
    x = _ensure_df(x)
    if indus_matrix is None: return CS_Rank(x)
    try:
        if isinstance(indus_matrix, pd.Series): indus_matrix = indus_matrix.to_frame()
        df_long = pd.concat([x.stack(), indus_matrix.stack()], axis=1, keys=['val', 'ind'], join='inner')
        ranked = df_long.groupby([df_long.index.get_level_values(0), 'ind'])['val'].rank(pct=True)
        return ranked.unstack()
    except: return CS_Rank(x)

# 建议添加到算子库
def TTM(x):
    """滚动12个月求和 (假设数据为单季度值)"""
    return x.rolling(_check_window(3)).sum()

# --- 元素/数学 ---
# def YOY(x): prev = x.shift(250); return (x - prev) / (prev.abs() + EPS)
def YOY(x): 
    """
    同比 (Year-Over-Year):
    在 4.30/8.30/10.30 的体系下，每年3个点。
    因此去年的同一期，是往前推 3 个单位。
    """
    prev = x.shift(3) 
    return (x - prev) / (prev.abs() + EPS)

# def QOQ(x): prev = x.shift(60); return (x - prev) / (prev.abs() + EPS)
def QOQ(x): 
    """
    环比 (Quarter-Over-Quarter):
    直接与上一期（shift 1）比较。
    注意：在4.30时，对比的是去年10.30的三季报数据（逻辑上虽有跳跃，但这是数据流的真实情况）
    """
    prev = x.shift(1)
    return (x - prev) / (prev.abs() + EPS)
# def Delay(x, d): return x.shift(_check_window(d))
def Delay(x, d): 
    """季频滞后: d=1 代表取上一期财报 (如当前是中报，Delay(1)就是一季报)"""
    return x.shift(int(d))
    
# def Delta(x, d):
#     """时序差分: x_t - x_{t-d}"""
#     return x.diff(int(d))

def Inv(x): return 1.0 / (x + EPS)
def Abs(x): return x.abs()
def Sign(x): return np.sign(x)
def Log(x): return np.log(x.abs() + EPS)
def Exp(x): return np.exp(x.clip(upper=20))
def Sqrt(x): return np.sqrt(x.abs())
def Pow(x, y): return np.sign(x) * (x.abs() ** y)

# --- 关系/复合 ---
def Add(x, y): return x + y
def Sub(x, y): return x - y
def Mul(x, y): return x * y
def Div(x, y): return x / (y + EPS)
def Rank_Add(x, y): return CS_Rank(x) + CS_Rank(y)
def Rank_Sub(x, y): return CS_Rank(x) - CS_Rank(y)
def Rank_Mul(x, y): return CS_Rank(x) * CS_Rank(y)
def Rank_Div(x, y): return CS_Rank(x) / (CS_Rank(y) + EPS)

# --- 时序 ---
def TS_Mean(x, d): return x.rolling(_check_window(d)).mean()
def TS_Std(x, d): return x.rolling(_check_window(d)).std()
def TS_Sum(x, d): return x.rolling(_check_window(d)).sum()
def TS_Corr(x, y, d): return x.rolling(_check_window(d)).corr(y)
# def ts_delay(x, d): return x.shift(int(d)) # 日频专用
def delta(x, d):    return x.diff(_check_window(d))

# --- 核心修复：增加 Delta 算子 ---
def Delta(x, d): 
    """时序差分：x_t - x_{t-d}"""
    return x.diff(_check_window(d))

# Delta = delta
# --- [新增] 极值与位置 (华泰图表9要求) ---
def TS_Min(x, d): return x.rolling(_check_window(d)).min()
def TS_Max(x, d): return x.rolling(_check_window(d)).max()
def TS_Argmin(x, d): return x.rolling(_check_window(d)).apply(np.argmin) # 最小值发生的位置
def TS_Argmax(x, d): return x.rolling(_check_window(d)).apply(np.argmax) # 最大值发生的位置

# --- [新增] 趋势与回归 (东吴Alpha158常用) ---
# 注意：滚动回归计算较慢，如果追求速度可暂时不加，但对挖掘Alpha很重要
def Slope(x, d):
    """计算x在过去d天的线性回归斜率 (简单实现版)"""
    w = _check_window(d)
    # 使用 numpy polyfit 的简化版或 pandas 的 cov/var 实现
    # Slope = Cov(x, t) / Var(t)
    # 这里为了性能，通常简化为时序上的变化率，或者用 rolling_apply
    # 既然是因子挖掘，建议先用简单的 Delta 代替，或者使用以下 pandas 实现：
    return x.diff(w) / w # 简易版斜率，如果要精确回归斜率需用 rolling().apply

# 修正 TTM 逻辑 (重要提醒)
# 如果你的数据是日频(每天都有值)，且进行了向前填充。
# rolling(240).sum() 会把每一天的值都加起来，导致数值巨大错误。
# 建议 TTM 改为如下逻辑 (假设 x 是单季度值，且每季度只变一次):
# 或者，最安全的做法是让 AI 使用 TS_Sum(x, 4) 但明确 x 必须是稀疏数据。
# 鉴于日频数据处理的复杂性，建议暂时保留你现有的 TTM，但需确保输入数据的频率。

# --- 算子打包函数 ---
def matrix_operators():
    return {k: v for k, v in globals().items() if callable(v) and not k.startswith('_')}


# =================================================================
# 1. 定义算子库头文件 (用于发送给远程平台)
# =================================================================
# 【核心原则】本地 matrix_operators 有什么，这里就必须有什么
# =================================================================

OPERATOR_HEADER_STR = r'''
import pandas as pd
import numpy as np

# --- 0. 核心装饰器 ---
# ================= 0. 核心装饰器: 双向数据适配器 (动态提取版) =================
def auto_process(func):
    def wrapper(data, *args, **kwargs):
        try:
            # [模式 A] 本地调用: 输入已经是矩阵字典 -> 直接计算，直接返回矩阵
            if isinstance(data, dict):
                return func(data, *args, **kwargs)
            
            # [模式 B] 远程调用: 输入是长表 DataFrame -> "拆解计算，组装返回"
            if isinstance(data, pd.DataFrame):
                # --- 1. Input Adapter: 长表 -> 矩阵字典 ---
                df_long = data.copy()
                # 记录原始索引，用于最后还原对齐
                original_index = df_long.index
                
                # 确保有 date/code 列用于 Pivot
                if isinstance(df_long.index, pd.MultiIndex):
                    df_long = df_long.reset_index()
                
                # 识别 date 和 code 列名 (忽略大小写进行匹配，但保留原表列名)
                date_col = next((c for c in df_long.columns if 'date' in str(c).lower()), 'date')
                code_col = next((c for c in df_long.columns if 'code' in str(c).lower() or 'asset' in str(c).lower()), 'code')
                
                matrix_dict = {}
                
                if date_col in df_long.columns and code_col in df_long.columns:
                    # 统一转 datetime 方便排序
                    df_long[date_col] = pd.to_datetime(df_long[date_col])
                    
                    # 🚀 核心优化：动态提取目标字段（排除坐标轴后，剩下的全是财务科目）
                    exclude_cols = {date_col, code_col}
                    target_fields = [c for c in df_long.columns if c not in exclude_cols]
                    
                    for field in target_fields:
                        # Pivot: Index=Date, Columns=Code, Values=原始列名
                        matrix = df_long.pivot(index=date_col, columns=code_col, values=field)
                        matrix = matrix.sort_index()
                        
                        # 存入字典（直接使用原始列名作为 Key）
                        matrix_dict[field] = matrix

                # --- 2. Core Execution: 执行矩阵运算 ---
                if not matrix_dict:
                    # 没提取到数据，尝试直接传原数据(死马当活马医)
                    print("⚠️ [AutoProcess Warning] 未能生成宽表字典，降级透传原表。")
                    return func(data, *args, **kwargs)
                
                # 执行你的因子计算逻辑
                result_matrix = func(matrix_dict, *args, **kwargs)
                
                # --- 3. Output Adapter: 矩阵 -> 长表 Series (闭环还原) ---
                # 平台期望得到一个与输入 data 索引一一对应的 Series
                if isinstance(result_matrix, pd.DataFrame):
                    # 3.1 宽变长 (Stack): 变成 (Date, Code) 的 Series
                    # stack() 自动忽略 NaN
                    series_long = result_matrix.stack()
                    
                    # 3.2 构造目标索引 (Target Index)
                    target_df = df_long[[date_col, code_col]].copy()
                    
                    series_name = '_factor_temp_'
                    series_long.name = series_name
                    
                    # 变成 DataFrame: Index=(Date, Code), Value=Factor
                    factor_long_df = series_long.reset_index()
                    factor_long_df.columns = [date_col, code_col, series_name]
                    
                    # 3.3 Merge 回原始顺序 (使用 left join 保证行数和顺序严格一致)
                    merged = pd.merge(target_df, factor_long_df, on=[date_col, code_col], how='left')
                    
                    # 3.4 提取 Series 并恢复原始索引
                    result_series = merged[series_name]
                    result_series.index = original_index 
                    
                    return result_series
                
                # 如果返回的不是 DF (比如是常数或已有 Series)，直接返回
                return result_matrix

            # 其他情况直接透传
            return func(data, *args, **kwargs)

        except Exception as e:
            print(f"❌ [AutoProcess Error] {str(e)}")
            raise e
            
    return wrapper

# --- 1. 全局配置 ---
EPS = 1e-10
DAYS_PER_QUARTER = 60

def _ensure_df(x): return x.to_frame() if isinstance(x, pd.Series) else x
def _check_window(d): return max(1, int(d)) # d=1 就是回溯1个切片

# --- 2. 截面算子 ---
def CS_Rank(x): return _ensure_df(x).rank(axis=1, pct=True)

def CS_Indus_Rank(x, indus_matrix):
    x = _ensure_df(x)
    if indus_matrix is None: return CS_Rank(x)
    try:
        if isinstance(indus_matrix, pd.Series): indus_matrix = indus_matrix.to_frame()
        df_long = pd.concat([x.stack(), indus_matrix.stack()], axis=1, keys=['val', 'ind'], join='inner')
        ranked = df_long.groupby([df_long.index.get_level_values(0), 'ind'])['val'].rank(pct=True)
        return ranked.unstack()
    except: return CS_Rank(x)

# --- 3. 基础变换 ---
def TTM(x): 
    """[新增] 滚动12个月求和"""
    return x.rolling(_check_window(3)).sum()

def YOY(x): prev = x.shift(3); return (x - prev) / (prev.abs() + EPS)
def QOQ(x): prev = x.shift(1); return (x - prev) / (prev.abs() + EPS)
def Delay(x, d): return x.shift(_check_window(d))
def Delta(x, d): return x.diff(_check_window(d))

def Inv(x): return 1.0 / (x + EPS)
def Abs(x): return x.abs()
def Sign(x): return np.sign(x)
def Log(x): return np.log(x.abs() + EPS)
def Exp(x): return np.exp(x.clip(upper=20))
def Sqrt(x): return np.sqrt(x.abs())
def Pow(x, y): return np.sign(x) * (x.abs() ** y)

# --- 4. 复合运算 ---
def Add(x, y): return x + y
def Sub(x, y): return x - y
def Mul(x, y): return x * y
def Div(x, y): return x / (y + EPS)
def Rank_Add(x, y): return CS_Rank(x) + CS_Rank(y)
def Rank_Sub(x, y): return CS_Rank(x) - CS_Rank(y)
def Rank_Mul(x, y): return CS_Rank(x) * CS_Rank(y)
def Rank_Div(x, y): return CS_Rank(x) / (CS_Rank(y) + EPS)

# --- 5. 时序统计 (补全华泰研报需求) ---
def TS_Mean(x, d): return x.rolling(int(d)).mean()
def TS_Std(x, d): return x.rolling(int(d)).std()
def TS_Sum(x, d): return x.rolling(int(d)).sum()
def TS_Corr(x, y, d): return x.rolling(int(d)).corr(y)

# [新增] 极值类算子
def TS_Min(x, d): return x.rolling(int(d)).min()
def TS_Max(x, d): return x.rolling(int(d)).max()
def TS_Argmin(x, d): return x.rolling(_check_window(d)).apply(np.argmin, raw=True)
def TS_Argmax(x, d): return x.rolling(_check_window(d)).apply(np.argmax, raw=True)

def Slope(x, d):
    """计算x在过去d天的线性回归斜率 (简单实现版)"""
    w = _check_window(d)
    # 使用 numpy polyfit 的简化版或 pandas 的 cov/var 实现
    # Slope = Cov(x, t) / Var(t)
    # 这里为了性能，通常简化为时序上的变化率，或者用 rolling_apply
    # 既然是因子挖掘，建议先用简单的 Delta 代替，或者使用以下 pandas 实现：
    return x.diff(w) / w # 简易版斜率，如果要精确回归斜率需用 rolling().apply

# 兼容性别名
delta = Delta
delay = Delay
'''