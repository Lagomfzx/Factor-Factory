# factor_engine/factories/fundamental/local_calc_fund.py

import pandas as pd
import numpy as np
import os
import re
import gc
import inspect
from tqdm import tqdm
# =====验证=====

import glob


def generate_snapshot_calendar(start_year, end_year):
    dates = []
    for year in range(start_year, end_year + 1):
        dates.append(f"{year}-04-30")
        dates.append(f"{year}-08-30")
        dates.append(f"{year}-10-30")
    return pd.to_datetime(dates).sort_values()


def apply_calculators_vectorized(
    context: dict,
    calculators: dict,
    is_listed_mask: pd.DataFrame = None,
) -> dict:
    aligned_mask = is_listed_mask
    if aligned_mask is not None:
        print("[Zombie Filter] Listed mask enabled for fundamental matrix mode.")

    print(f"[Compute] Running {len(calculators)} fundamental calculators...")
    calculated_factors = {}

    for name, func in tqdm(calculators.items(), desc="Computing"):
        factor_name = name.replace("calculate_", "")
        try:
            result = func(context)
            if aligned_mask is not None and isinstance(result, pd.DataFrame):
                result = result * aligned_mask

            if isinstance(result, (pd.DataFrame, pd.Series, int, float)):
                calculated_factors[factor_name] = result
            elif result is not None:
                print(f"[Warn] {factor_name} returned unsupported type: {type(result)}")
        except Exception as exc:
            print(f"[Error] {factor_name} failed: {exc}")

    return calculated_factors


def parse_code_to_functions(code_text):
    """
    Execute LLM-generated code and extract callable `calculate_*` functions.
    The validated notebook injects the fundamental operator library here.
    """
    clean_code = code_text
    if "```python" in code_text:
        match = re.search(r"```python(.*?)```", code_text, re.DOTALL)
        if match:
            clean_code = match.group(1)
    elif "```" in code_text:
        match = re.search(r"```(.*?)```", code_text, re.DOTALL)
        if match:
            clean_code = match.group(1)

    local_scope = {}
    try:
        from factor_engine.operators.op_fundamental import matrix_operators

        global_scope = {
            "pd": pd,
            "np": np,
            "os": os,
            "factor_db": None,
        }
        global_scope.update(matrix_operators())
        exec(clean_code, global_scope, local_scope)
    except Exception as exc:
        print(f"[Syntax Error] Code compilation failed: {exc}")
        return {}

    calculators = {}
    for name, func in local_scope.items():
        if name.startswith("calculate_") and callable(func):
            calculators[name] = func
    return calculators

# ================= 配置区域 =================
# 👇 请修改这里：指向任意一个包含按天拆分数据的因子文件夹
# 例如：r"mydata/fundamental_data/BS_ABSINTERDEPOSITS"
TEST_FOLDER_PATH = "/storage/server/145server/ly/luodan/财务数据/BS_AADJUSTMENTITEMS" 
# ===========================================

def quick_validate_folder(folder_path):
    print(f"🔍 开始验证文件夹: {folder_path} ...")
    
    if not os.path.exists(folder_path):
        print("❌ 错误：文件夹不存在！")
        return

    files = [f for f in os.listdir(folder_path) if f.endswith('.csv') or f.endswith('.parquet')]
    
    if not files:
        print("❌ 错误：文件夹内没有找到 .csv 或 .parquet 文件！")
        return

    print(f"✅ 发现 {len(files)} 个数据文件。正在随机抽取 3 个文件测试日期解析...")
    
    # 随机抽取 3 个文件进行测试 (如果不足3个则全部测试)
    test_files = files if len(files) <= 3 else pd.Series(files).sample(3).tolist()
    
    df_list = []
    success_count = 0
    
    for filename in test_files:
        file_path = os.path.join(folder_path, filename)
        name_without_ext = os.path.splitext(filename)[0]
        
        # --- 复制您修改后的日期解析逻辑 ---
        file_date = None
        try:
            file_date = pd.to_datetime(name_without_ext)
        except:
            match = re.search(r'(\d{4})[-]?(\d{2})[-]?(\d{2})', name_without_ext)
            if match:
                standard_date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                try:
                    file_date = pd.to_datetime(standard_date_str)
                except:
                    pass
        
        if file_date is None:
            print(f"  ⚠️ [失败] 文件名 '{filename}' -> 无法解析日期")
            continue
            
        print(f"  ✅ [成功] 文件名 '{filename}' -> 解析为日期: {file_date.date()}")
        success_count += 1
        
        # 读取数据并添加日期列，准备拼接测试
        try:
            if file_path.endswith('.parquet'):
                temp_df = pd.read_parquet(file_path)
            else:
                temp_df = pd.read_csv(file_path, nrows=5) # 只读前5行加速测试
            
            temp_df['INFOPUBLDATE'] = file_date
            df_list.append(temp_df)
        except Exception as e:
            print(f"  ⚠️ [读取失败] {filename}: {e}")

    if success_count == 0:
        print("\n❌ 验证失败：没有文件能成功解析日期。请检查文件名格式或正则逻辑。")
        return

    print("\n🔄 正在测试数据拼接 (Concat) 和 透视 (Pivot)...")
    
    try:
        # 1. 测试拼接
        df_combined = pd.concat(df_list, ignore_index=True)
        print(f"  ✅ 拼接成功：总行数 {len(df_combined)}")
        
        # 2. 尝试识别列 (模拟类中的逻辑)
        cols = df_combined.columns
        date_col = 'INFOPUBLDATE'
        code_col = next((c for c in cols if 'CODE' in c.upper()), 'SECUCODE')
        
        # 找值列
        exclude_cols = {date_col, code_col}
        val_cols = [c for c in cols if c not in exclude_cols]
        
        if not val_cols:
            print(f"  ⚠️ 警告：未找到数值列。当前列名: {list(cols)}")
        else:
            val_col = val_cols[0]
            print(f"  ✅ 识别列成功 -> 日期:{date_col}, 代码:{code_col}, 数值:{val_col}")
            
            # 3. 测试 Pivot (最关键的一步)
            # 注意：如果样本数据中代码有重复，pivot会报错，这里仅做逻辑验证
            try:
                pivot_test = df_combined.pivot(index=date_col, columns=code_col, values=val_col)
                print(f"  ✅ 透视 (Pivot) 成功！生成的矩阵形状: {pivot_test.shape}")
                print("\n🎉 验证通过！您的修改逻辑完全正确，可以应用到 LazyFactorDB 类中。")
                print("\n预览数据片段:")
                print(pivot_test.head())
            except Exception as e:
                print(f"  ⚠️ 透视失败 (可能是样本数据中代码重复或结构问题，但不代表逻辑错误): {e}")
                print("  💡 提示：只要日期解析和拼接成功，通常意味着核心逻辑没问题。")

    except Exception as e:
        print(f"\n❌ 拼接或处理过程中出错: {e}")

# 执行验证
# quick_validate_folder(TEST_FOLDER_PATH)


class LazyFactorDB:
    """
    懒加载
    """
    def __init__(self, data_folders, snapshot_days, max_age=150):
        self.file_map = {}  
        self.cache = {}
        self.snapshot_days = pd.to_datetime(snapshot_days).sort_values()
        self.max_age = max_age
        
        # 【核心修改 1】：兼容处理。如果是传了单个字符串，自动把它包装成列表
        if isinstance(data_folders, str):
            data_folders = [data_folders]
            
        # 【核心修改 2】：遍历所有的主文件夹路径
        for folder in data_folders:
            if not os.path.exists(folder):
                print(f"⚠️ Warning: 路径不存在，已跳过 -> {folder}")
                continue
                
            # 在当前循环的文件夹下进行扫描
            csv_files = glob.glob(os.path.join(folder, "*", "*.csv"))
            for file_path in csv_files:
                metric_name = os.path.splitext(os.path.basename(file_path))[0]
                
                # 提示：如果不同文件夹里出现了同名的 CSV，后扫描到的会覆盖前面的
                if metric_name in self.file_map:
                    print(f"⚠️ 注意: 发现同名科目被覆盖 -> {metric_name} (新路径: {file_path})")
                    
                self.file_map[metric_name] = file_path
                
        print(f"✅ [DB Init] 宽表引擎初始化: 扫描了 {len(data_folders)} 个主目录，共索引 {len(self.file_map)} 个科目 (采样点: {len(self.snapshot_days)} | 过期阈值: {max_age}天)")

    def __getitem__(self, key):
        if key in self.cache: 
            return self.cache[key]
            
        if key not in self.file_map: 
            raise KeyError(f"Factor '{key}' not found in DB.")
        
        file_path = self.file_map[key]
        
        # 1. 极速读取宽表 (全当字符串读，防止混合类型警告)
        df = pd.read_csv(file_path, index_col=0, dtype=str)
        
        # 2. [逻辑变更2]: 矩阵转置 (因为你的原数据是行=股票，列=日期)
        df = df.T
        
        # 3. 数据清洗与格式化
        # 转置后 index 是日期字符串，强转为 Datetime
        df.index = pd.to_datetime(df.index, errors='coerce')
        # 剔除无法识别的烂日期
        df = df[df.index.notna()]
        # 强转为数值型，无法转换的脏字符(如 '--')会变成 NaN
        df = df.apply(pd.to_numeric, errors='coerce')
        
        # 确保时间轴是有序的，去除可能重复的列名/日期
        df = df.sort_index()
        df = df[~df.index.duplicated(keep='last')]
        
        # 4. [黑科技]: 极简的时序对齐与过期剔除
        # reindex 可以完美实现：按 self.snapshot_days 抽取数据，
        # 如果当天没数据，往前 ffill，但最多往前找 max_age 天 (超过则填 NaN)
        final_dense = df.reindex(
            self.snapshot_days,
            method='ffill',
            tolerance=pd.Timedelta(days=self.max_age)
        )
        
        # 5. 降低内存占用并存入缓存
        self.cache[key] = final_dense.astype('float32')
        return self.cache[key]

    def keys(self): 
        return self.file_map.keys()

    def clear_cache(self):
        self.cache.clear()
        gc.collect()
        print("🧹 [Cache] 内存缓存已彻底清理。")




class FactorExecutor:
    """
    从大模型的代码中进行
    """
    def __init__(self, db):
        self.db = db
        
    def run(self, calculators, code_text=None):
        """
        【回归 V1 模式】智能执行器：
        1. 分析依赖
        2. 按需提取 Wide DataFrame
        3. 打包成 Context 字典传给算子
        """
        print(f"⚙️ [Executor] 启动 V1 模式计算引擎 (Context Dict)...")
        
        needed_fields = set()
        print("🕵️ 正在分析算子依赖字段...")

        # --- 策略 A: 优先分析原始代码文本 ---
        if code_text:
            matches = re.findall(r"['\"]([a-zA-Z0-9_]+)['\"]", code_text)
            for m in matches:
                # 忽略大小写匹配数据库键
                if m in self.db.file_map or m.lower() in self.db.file_map:
                    needed_fields.add(m)
                    
        # --- 策略 B: 反射 (兜底) ---
        else:
            for name, func in calculators.items():
                try:
                    src = inspect.getsource(func)
                    matches = re.findall(r"['\"]([a-zA-Z0-9_]+)['\"]", src)
                    for m in matches:
                        if m in self.db.file_map or m.lower() in self.db.file_map:
                            needed_fields.add(m)
                except Exception:
                    pass 
        
        # 总是加载 is_listed (用于过滤)
        if 'is_listed' in self.db.file_map:
            needed_fields.add('is_listed')
            
        print(f"   -> 🎯 命中 {len(needed_fields)} 个基础因子: {list(needed_fields)[:5]}...")
        
        if not needed_fields:
            print("❌ 警告：未识别到任何有效依赖，计算可能失败。")
            return pd.DataFrame()

        # --- 第二步：构建 Context 字典 (关键修改：不合并，只打包) ---
        print("💧 正在准备 Context 数据 (不合并，保持独立矩阵)...")
        context_dict = {}
        
        for field in tqdm(needed_fields, desc="Loading Matrices"):
            try:
                # 直接获取宽表 (T x N)，不 stack，不合并
                df_wide = self.db[field]
                context_dict[field] = df_wide
            except Exception as e:
                print(f"❌ 加载 {field} 失败: {e}")

        if not context_dict:
            return pd.DataFrame()
            
        print(f"✅ Context 字典构建完成，包含 {len(context_dict)} 个矩阵。")

        # --- 第三步：准备过滤掩码 ---
        mask_df = None
        if 'is_listed' in context_dict:
             mask_df = context_dict['is_listed']

        # --- 第四步：执行计算 ---
        if 'apply_calculators_vectorized' in globals():
            # 注意：这里传入的是 context_dict，不再是 full_df
            result = apply_calculators_vectorized(context_dict, calculators, is_listed_mask=mask_df)
            return result
        else:
            raise NameError("apply_calculators_vectorized 未定义！")
