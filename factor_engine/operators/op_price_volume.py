# factor_engine/wq_operators.py
"""
算子库
"""
import pandas as pd
import numpy as np
import re

operator_lib_header = r'''
import pandas as pd
import numpy as np


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



# ================= 1. 基础辅助工具 (核心防御) =================
EPS = 1e-10

def _check_window(n):
    return max(1, int(n)) if not pd.isna(n) else 1

def _ensure_df(x):
    """
    维度防御核心：
    如果输入是 Series (T,)，强制转为 DataFrame (T, 1)。
    防止 axis=1 操作报错。
    """
    if isinstance(x, pd.Series):
        return x.to_frame()
    return x

# ================= 2. WQ 基础数学 (Element-wise Matrix Ops) =================
# 矩阵加减乘除天然对齐，无需 align 函数

def abs(x): return x.abs()
def log(x): return np.log(x.abs() + EPS)
def sign(x): return np.sign(x)
def signedpower(x, a): return np.sign(x) * (x.abs() ** a)

def sqrt(x): return np.sqrt(np.maximum(x, 0))
def safe_div(a, b): return a / (b + EPS)
def inv(x): return 1.0 / (x + EPS)

def add(a, b): return a + b
def sub(a, b): return a - b
def mul(a, b): return a * b
def div(a, b): return safe_div(a, b)

def max_elem(a, b): return np.maximum(a, b)
def min_elem(a, b): return np.minimum(a, b)

def if_else(condition, true_val, false_val):
    condition = _ensure_df(condition).astype(bool)

    def _broadcast_branch(value):
        if np.isscalar(value):
            return pd.DataFrame(value, index=condition.index, columns=condition.columns)

        value = _ensure_df(value).copy()
        if value.shape[1] == condition.shape[1]:
            value.columns = condition.columns
        return value.reindex(index=condition.index, columns=condition.columns)

    true_val = _broadcast_branch(true_val)
    false_val = _broadcast_branch(false_val)
    return true_val.where(condition, false_val)

# ================= 3. WQ 截面算子 (Cross-Sectional -> axis=1) =================
# 所有截面算子都加上了 _ensure_df 防御

def rank(x):
    """截面排名 (百分比)"""
    return _ensure_df(x).rank(axis=1, pct=True)

def scale(x, a=1):
    """L1 归一化: sum(abs(x)) = a"""
    x = _ensure_df(x)
    return x.mul(a).div(x.abs().sum(axis=1) + EPS, axis=0)

def indneutralize(x, g=None):
    """行业中性化 (简化版: 全市场去均值)"""
    x = _ensure_df(x)
    return x.sub(x.mean(axis=1), axis=0)

def zscore(x):
    """截面 Z-Score"""
    x = _ensure_df(x)
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1) + EPS, axis=0)

def winsorize(x, n=3.0):
    """截面去极值"""
    x = _ensure_df(x)
    mean = x.mean(axis=1)
    std = x.std(axis=1)
    upper = mean + n * std
    lower = mean - n * std
    return x.clip(lower=lower, upper=upper, axis=0)

def resid(y, x):
    """截面回归残差: Res = Y - beta * X (极速矩阵版)"""
    y = _ensure_df(y)
    x = _ensure_df(x)
    # 1. 去均值
    y_demean = y.sub(y.mean(axis=1), axis=0)
    x_demean = x.sub(x.mean(axis=1), axis=0)
    # 2. 计算 Beta
    numerator = (x_demean * y_demean).sum(axis=1)
    denominator = (x_demean ** 2).sum(axis=1)
    beta = numerator / (denominator + EPS)
    # 3. 残差
    return y - x.mul(beta, axis=0)

# ================= 4. WQ 时序算子 (Time-Series -> axis=0) =================
# 不需要 groupby，直接 rolling

def delay(x, d): return x.shift(_check_window(d))
def delta(x, d): return x.diff(_check_window(d))

def correlation(x, y, d):
    # DataFrame 的 rolling corr 会自动按列 (Code) 计算
    return x.rolling(_check_window(d)).corr(y)

def covariance(x, y, d):
    return x.rolling(_check_window(d)).cov(y)

def decay_linear(x, d):
    d = _check_window(d)
    w = np.arange(1, d + 1)
    w = w / w.sum()
    def _weighted(arr): return np.dot(arr, w)
    return x.rolling(d).apply(_weighted, raw=True)

# --- ts_ 系列 ---
def ts_mean(x, d): return x.rolling(_check_window(d)).mean()
def ts_std(x, d):  return x.rolling(_check_window(d)).std()
def ts_min(x, d):  return x.rolling(_check_window(d)).min()
def ts_max(x, d):  return x.rolling(_check_window(d)).max()
def ts_sum(x, d):  return x.rolling(_check_window(d)).sum()
def ts_product(x, d): return x.rolling(_check_window(d)).apply(np.prod, raw=True)

def ts_rank(x, d):
    return x.rolling(_check_window(d)).rank(pct=True)

def ts_argmax(x, d):
    return x.rolling(_check_window(d)).apply(np.argmax, raw=True)

def ts_argmin(x, d):
    return x.rolling(_check_window(d)).apply(np.argmin, raw=True)

def ts_skew(x, d): return x.rolling(_check_window(d)).skew()
def ts_kurt(x, d): return x.rolling(_check_window(d)).kurt()
def ts_ema(x, d): return x.ewm(span=_check_window(d), adjust=False).mean()

def zhenfu(high, low, close):
    return (high - low) / (close.shift(1) + EPS)

# ================= 5. 别名映射 (兼容模型生成的代码) =================
# 截面类
CS_Rank = rank
CS_ZScore = zscore
CS_Resid = resid
CS_Scale = scale

# 时序类
skew = ts_skew
TS_Mean = ts_mean
TS_Std = ts_std
TS_Max = ts_max
TS_Min = ts_min
TS_Sum = ts_sum
TS_Rank = ts_rank
TS_ArgMax = ts_argmax
TS_ArgMin = ts_argmin
TS_Corr = correlation
ts_corr = correlation
TS_Cov = covariance
Delay = delay
Delta = delta
ts_delta = delta
Decay_Linear = decay_linear

# 辅助
Abs = abs
Log = log
Sign = sign
SignedPower = signedpower
Or = lambda a, b: a | b
And = lambda a, b: a & b
'''



def combine_operator_lib_with_strategy(operator_lib_header1, strategy_code):
    """
    拼接算子库与策略代码，并自动注入装饰器。
    Args:
        operator_lib_header1: 包含算子定义和 @auto_process 装饰器的完整字符串
        strategy_code: LLM 生成的策略代码
    """
    
    # 使用正则全局替换：给所有 calculate_ 函数戴上帽子
    strategy_code_fixed = re.sub(
        r"(def\s+calculate_)", 
        r"@auto_process\n\1", 
        strategy_code
    )

    # 最终合并
    final_script = f"{operator_lib_header1}\n\n# ================= STRATEGY =================\n{strategy_code_fixed}"
    
    return final_script


import pandas as pd
import numpy as np

def matrix_operators():
    """
    【WorldQuant Alpha 101 矩阵算子库 (Matrix/Wide Format 修复版)】
    已加入维度防御，防止 Series 导致 axis=1 报错。
    """
    EPS = 1e-10

    # ------------------------------------------------
    # 0. 核心维度防御 (Critical Fix)
    # ------------------------------------------------
    def _ensure_df(x):
        """
        维度防御核心：
        如果输入是 Series (T,)，强制转为 DataFrame (T, 1)。
        这样 axis=1 的操作就不会报错（虽然对单列做 rank 结果全是 1.0，但保证了 pipeline 不崩）。
        """
        if isinstance(x, pd.Series):
            return x.to_frame()
        return x

    def _check_window(n):
        return max(1, int(n)) if not pd.isna(n) else 1

    # ------------------------------------------------
    # 1. WQ 基础数学
    # ------------------------------------------------
    def abs(x): return x.abs()
    def log(x): return np.log(x.abs() + EPS)
    def sign(x): return np.sign(x)
    
    def signedpower(x, a):
        return np.sign(x) * (x.abs() ** a)

    def sqrt(x):
        return np.sqrt(np.maximum(x, 0))

    def safe_div(a, b):
        return a / (b + EPS)
    
    def inv(x): return 1.0 / (x + EPS)
    def add(a, b): return a + b
    def sub(a, b): return a - b
    def mul(a, b): return a * b
    def div(a, b): return safe_div(a, b)
    
    def max_elem(a, b): return np.maximum(a, b) 
    def min_elem(a, b): return np.minimum(a, b)
    
    def if_else(condition, true_val, false_val):
        condition = _ensure_df(condition).astype(bool)

        def _broadcast_branch(value):
            if np.isscalar(value):
                return pd.DataFrame(value, index=condition.index, columns=condition.columns)

            value = _ensure_df(value).copy()
            if value.shape[1] == condition.shape[1]:
                value.columns = condition.columns
            return value.reindex(index=condition.index, columns=condition.columns)

        true_val = _broadcast_branch(true_val)
        false_val = _broadcast_branch(false_val)
        return true_val.where(condition, false_val)

    # ------------------------------------------------
    # 2. WQ 截面算子 (需加装防弹衣)
    # ------------------------------------------------
    
    def rank(x):
        """[WQ] rank: 横向排名"""
        # 修复：先转 DF 再 rank，防止 Series 报错
        return _ensure_df(x).rank(axis=1, pct=True)

    def scale(x, a=1):
        """[WQ] scale: L1 归一化"""
        x = _ensure_df(x)
        # sum(axis=1) 会返回 Series，利用广播除法
        daily_abs_sum = x.abs().sum(axis=1)
        return x.mul(a).div(daily_abs_sum + EPS, axis=0)

    def indneutralize(x, g=None):
        """[WQ] indneutralize: 全市场去均值"""
        x = _ensure_df(x)
        return x.sub(x.mean(axis=1), axis=0)

    def zscore(x):
        """截面 Z-Score"""
        x = _ensure_df(x)
        mean = x.mean(axis=1)
        std = x.std(axis=1)
        return x.sub(mean, axis=0).div(std + EPS, axis=0)
    
    def winsorize(x, n=3.0):
        """截面去极值"""
        x = _ensure_df(x)
        mean = x.mean(axis=1)
        std = x.std(axis=1)
        upper = mean + n * std
        lower = mean - n * std
        return x.clip(lower=lower, upper=upper, axis=0)

    def resid(y, x):
        """截面回归残差"""
        # 修复：y 和 x 都要防御
        y = _ensure_df(y)
        x = _ensure_df(x)
        
        y_demean = y.sub(y.mean(axis=1), axis=0)
        x_demean = x.sub(x.mean(axis=1), axis=0)
        
        numerator = (x_demean * y_demean).sum(axis=1)
        denominator = (x_demean ** 2).sum(axis=1)
        beta = numerator / (denominator + EPS)
        
        return y - x.mul(beta, axis=0)

    # ------------------------------------------------
    # 3. WQ 时序算子 (Time-Series -> axis=0)
    # ------------------------------------------------
    # 时序算子一般不需要 _ensure_df，因为 rolling 对 Series 和 DataFrame 都有效
    
    def delay(x, d): return x.shift(_check_window(d))
    def delta(x, d): return x.diff(_check_window(d))

    def correlation(x, y, d): return x.rolling(_check_window(d)).corr(y)
    def covariance(x, y, d): return x.rolling(_check_window(d)).cov(y)

    def decay_linear(x, d):
        d = _check_window(d)
        w = np.arange(1, d + 1)
        w = w / w.sum()
        def _weighted(arr): return np.dot(arr, w)
        return x.rolling(d).apply(_weighted, raw=True)

    # --- ts_ 系列 ---
    def ts_mean(x, d): return x.rolling(_check_window(d)).mean()
    def ts_std(x, d):  return x.rolling(_check_window(d)).std()
    def ts_min(x, d):  return x.rolling(_check_window(d)).min()
    def ts_max(x, d):  return x.rolling(_check_window(d)).max()
    def ts_sum(x, d):  return x.rolling(_check_window(d)).sum()
    
    def ts_product(x, d): return x.rolling(_check_window(d)).apply(np.prod, raw=True)
    def ts_rank(x, d):    return x.rolling(_check_window(d)).rank(pct=True)
    
    def ts_argmax(x, d):  return x.rolling(_check_window(d)).apply(np.argmax, raw=True)
    def ts_argmin(x, d):  return x.rolling(_check_window(d)).apply(np.argmin, raw=True)
    
    def ts_skew(x, d): return x.rolling(_check_window(d)).skew()
    def ts_kurt(x, d): return x.rolling(_check_window(d)).kurt()
    
    def ts_count(condition, d):
        return condition.astype(float).rolling(_check_window(d)).sum()
    
    def ts_ema(x, d):
        return x.ewm(span=_check_window(d), adjust=False).mean()

    def zhenfu(high, low, close):
        return (high - low) / (close.shift(1) + EPS)

    # ------------------------------------------------
    # 4. 导出
    # ------------------------------------------------
    ops = locals().copy()
    
    ops['stddev'] = ts_std
    ops['sum'] = ts_sum
    ops['min'] = ts_min
    ops['max'] = ts_max
    ops['product'] = ts_product
    ops['neutralize'] = resid
    ops['skew'] = ts_skew
    
    ops['CS_Rank'] = rank
    ops['CS_ZScore'] = zscore
    ops['CS_Resid'] = resid
    ops['TS_Mean'] = ts_mean
    ops['TS_Std'] = ts_std
    ops['TS_Max'] = ts_max
    ops['TS_Min'] = ts_min
    ops['TS_Sum'] = ts_sum
    ops['TS_Rank'] = ts_rank
    ops['TS_Corr'] = correlation
    ops['ts_corr'] = correlation
    ops['Delay'] = delay
    ops['Delta'] = delta
    ops['ts_delta'] = delta
    
    ops['Or'] = lambda a, b: a | b
    ops['And'] = lambda a, b: a & b
    ops.update({'GT': lambda a,b: a > b, 'LT': lambda a,b: a < b})
    
    return ops



operators_sets ='''
# ================= 1. 基础辅助工具 (核心防御) =================
EPS = 1e-10

def _check_window(n):
    return max(1, int(n)) if not pd.isna(n) else 1

def _ensure_df(x):
    """
    维度防御核心：
    如果输入是 Series (T,)，强制转为 DataFrame (T, 1)。
    防止 axis=1 操作报错。
    """
    if isinstance(x, pd.Series):
        return x.to_frame()
    return x

# ================= 2. WQ 基础数学 (Element-wise Matrix Ops) =================
# 矩阵加减乘除天然对齐，无需 align 函数

def abs(x): return x.abs()
def log(x): return np.log(x.abs() + EPS)
def sign(x): return np.sign(x)
def signedpower(x, a): return np.sign(x) * (x.abs() ** a)

def sqrt(x): return np.sqrt(np.maximum(x, 0))
def safe_div(a, b): return a / (b + EPS)
def inv(x): return 1.0 / (x + EPS)

def add(a, b): return a + b
def sub(a, b): return a - b
def mul(a, b): return a * b
def div(a, b): return safe_div(a, b)

def max_elem(a, b): return np.maximum(a, b)
def min_elem(a, b): return np.minimum(a, b)

def if_else(condition, true_val, false_val):
    condition = _ensure_df(condition).astype(bool)

    def _broadcast_branch(value):
        if np.isscalar(value):
            return pd.DataFrame(value, index=condition.index, columns=condition.columns)

        value = _ensure_df(value).copy()
        if value.shape[1] == condition.shape[1]:
            value.columns = condition.columns
        return value.reindex(index=condition.index, columns=condition.columns)

    true_val = _broadcast_branch(true_val)
    false_val = _broadcast_branch(false_val)
    return true_val.where(condition, false_val)

# ================= 3. WQ 截面算子 (Cross-Sectional -> axis=1) =================
# 所有截面算子都加上了 _ensure_df 防御

def rank(x):
    """截面排名 (百分比)"""
    return _ensure_df(x).rank(axis=1, pct=True)

def scale(x, a=1):
    """L1 归一化: sum(abs(x)) = a"""
    x = _ensure_df(x)
    return x.mul(a).div(x.abs().sum(axis=1) + EPS, axis=0)

def indneutralize(x, g=None):
    """行业中性化 (简化版: 全市场去均值)"""
    x = _ensure_df(x)
    return x.sub(x.mean(axis=1), axis=0)

def zscore(x):
    """截面 Z-Score"""
    x = _ensure_df(x)
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1) + EPS, axis=0)

def winsorize(x, n=3.0):
    """截面去极值"""
    x = _ensure_df(x)
    mean = x.mean(axis=1)
    std = x.std(axis=1)
    upper = mean + n * std
    lower = mean - n * std
    return x.clip(lower=lower, upper=upper, axis=0)

def resid(y, x):
    """截面回归残差: Res = Y - beta * X (极速矩阵版)"""
    y = _ensure_df(y)
    x = _ensure_df(x)
    # 1. 去均值
    y_demean = y.sub(y.mean(axis=1), axis=0)
    x_demean = x.sub(x.mean(axis=1), axis=0)
    # 2. 计算 Beta
    numerator = (x_demean * y_demean).sum(axis=1)
    denominator = (x_demean ** 2).sum(axis=1)
    beta = numerator / (denominator + EPS)
    # 3. 残差
    return y - x.mul(beta, axis=0)

# ================= 4. WQ 时序算子 (Time-Series -> axis=0) =================
# 不需要 groupby，直接 rolling

def delay(x, d): return x.shift(_check_window(d))
def delta(x, d): return x.diff(_check_window(d))

def correlation(x, y, d):
    # DataFrame 的 rolling corr 会自动按列 (Code) 计算
    return x.rolling(_check_window(d)).corr(y)

def covariance(x, y, d):
    return x.rolling(_check_window(d)).cov(y)

def decay_linear(x, d):
    d = _check_window(d)
    w = np.arange(1, d + 1)
    w = w / w.sum()
    def _weighted(arr): return np.dot(arr, w)
    return x.rolling(d).apply(_weighted, raw=True)

# --- ts_ 系列 ---
def ts_mean(x, d): return x.rolling(_check_window(d)).mean()
def ts_std(x, d):  return x.rolling(_check_window(d)).std()
def ts_min(x, d):  return x.rolling(_check_window(d)).min()
def ts_max(x, d):  return x.rolling(_check_window(d)).max()
def ts_sum(x, d):  return x.rolling(_check_window(d)).sum()
def ts_product(x, d): return x.rolling(_check_window(d)).apply(np.prod, raw=True)

def ts_rank(x, d):
    return x.rolling(_check_window(d)).rank(pct=True)

def ts_argmax(x, d):
    return x.rolling(_check_window(d)).apply(np.argmax, raw=True)

def ts_argmin(x, d):
    return x.rolling(_check_window(d)).apply(np.argmin, raw=True)

def ts_skew(x, d): return x.rolling(_check_window(d)).skew()
def ts_kurt(x, d): return x.rolling(_check_window(d)).kurt()
def ts_ema(x, d): return x.ewm(span=_check_window(d), adjust=False).mean()

def zhenfu(high, low, close):
    return (high - low) / (close.shift(1) + EPS)
'''
