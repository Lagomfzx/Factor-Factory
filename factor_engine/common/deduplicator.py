# factor_engine/common/deduplicator.py

import re
import hashlib
import logging
import sqlite3
import os
import json
from typing import List
from contextlib import contextmanager

# =========================
# 日志配置
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H%S'
)
logger = logging.getLogger(__name__)

# =========================
# 字典配置区
# =========================
OP_ALIAS = {
    "ts_mean": "ts_mean", "TS_Mean": "ts_mean", "rolling_mean": "ts_mean", "ma": "ts_mean", "mean": "ts_mean",
    "ts_std": "ts_std", "TS_Std": "ts_std", "rolling_std": "ts_std", "std": "ts_std",
    "ts_max": "ts_max", "ts_min": "ts_min", "ts_corr": "ts_corr", "correlation": "ts_corr",
    "ts_delta": "ts_delta", "delta": "ts_delta", "ts_rank": "ts_rank",
    "rank": "cs_rank", "CS_Rank": "cs_rank", "CS_Resid": "cs_resid", "CS_MAD": "cs_mad",
    "CS_Median": "cs_median", "CS_ZScore": "cs_zscore",
    "log": "log", "Log": "log", "abs": "abs", "Abs": "abs", "sqrt": "sqrt", "Sqrt": "sqrt",
    "pow": "pow", "Pow": "pow", "sign": "sign", "Sign": "sign",
    "inv": "inv", "Inv": "inv", "safe_div": "div"
}

FIELD_UNIFY = {
    "close": "Close", "open": "Open", "high": "High", "low": "Low",
    "pe": "PE", "pb": "PB",
    "total_mv": "MarketCap", "circ_mv": "FloatCap", "circ_mv / total_mv": "FloatRatio",
    "amount": "Amount", "vol": "Volume", "turnover_rate": "Turnover",
    "zhengfu": "Amplitude",
}

COMMUTATIVE_OPS = {"add", "mul"}
MONOTONIC_FUNCS = {"zscore"}

def bucket_window(n: int) -> str:
    if n <= 5: return "SHORT"
    elif n <= 20: return "MEDIUM"
    elif n <= 60: return "LONG"
    else: return "VERY_LONG"

# =========================
# SQLite数据库管理 (高可用版)
# =========================
# @contextmanager
# def get_db_connection(db_path: str):
#     """【高可用版】增加耐心等待和高级并发模式，彻底告别 database is locked"""
#     conn = sqlite3.connect(db_path, timeout=15.0)
#     try:
#         conn.execute('PRAGMA journal_mode=WAL;')
#         yield conn
#     finally:
#         conn.close()

# def init_database(db_path: str):
#     with get_db_connection(db_path) as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS formula_hashes (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 hash_value TEXT UNIQUE NOT NULL,
#                 canonical_formula TEXT NOT NULL,
#                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#             )
#         """)
#         cursor.execute("CREATE INDEX IF NOT EXISTS idx_hash ON formula_hashes(hash_value)")
#         conn.commit()

# def insert_hash(db_conn, hash_value: str, canonical_formula: str):
#     cursor = db_conn.cursor()
#     try:
#         cursor.execute(
#             "INSERT INTO formula_hashes (hash_value, canonical_formula) VALUES (?, ?)",
#             (hash_value, canonical_formula)
#         )
#         db_conn.commit()
#         return True
#     except sqlite3.IntegrityError:
#         return False

# def check_hash_exists(db_conn, hash_value: str) -> bool:
#     cursor = db_conn.cursor()
#     cursor.execute("SELECT 1 FROM formula_hashes WHERE hash_value = ? LIMIT 1", (hash_value,))
#     return cursor.fetchone() is not None

# =========================
# 1. AST Node 定义与公式解析
# =========================
class Node:
    def __init__(self, op: str, children=None, params=None):
        self.op = op
        self.children = children or []
        self.params = params or {}

    def canonical(self) -> str:
        child_strs = [c.canonical() for c in self.children]
        if self.op in COMMUTATIVE_OPS:
            child_strs.sort()
        param_str = ""
        if self.params:
            param_str = "[" + ",".join(f"{k}={v}" for k, v in sorted(self.params.items())) + "]"
        return f"{self.op}({','.join(child_strs)}){param_str}"

FUNC_PATTERN = re.compile(r"(\w+)\((.*)\)")

def split_args(arg_str: str) -> List[str]:
    args, depth, buf = [], 0, ""
    for ch in arg_str:
        if ch == "," and depth == 0:
            args.append(buf.strip())
            buf = ""
        else:
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            buf += ch
    if buf: args.append(buf.strip())
    return args

def parse_formula(expr: str) -> Node:
    expr = expr.strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
       field_name = expr.lower()
       unified_field = FIELD_UNIFY.get(field_name, field_name)
       return Node(f"field:{unified_field}")

    for op, opname in [("/", "div"), ("+", "add"), ("*", "mul"), ("-", "sub")]:
        parts = split_by_op(expr, op)
        if parts:
            return Node(opname, [parse_formula(p) for p in parts])

    m = FUNC_PATTERN.match(expr)
    if not m: return Node(f"raw:{expr}")

    func, arg_str = m.groups()
    func = OP_ALIAS.get(func.lower(), func.lower()).lower()
    args = split_args(arg_str)

    params = {}
    children = []
    for a in args:
        if re.fullmatch(r"\d+", a): params["window"] = bucket_window(int(a))
        else: children.append(parse_formula(a))

    if func == "rank" and children:
        child = children[0]
        if child.op in MONOTONIC_FUNCS and child.children:
            children = child.children

    return Node(func, children, params)

def split_by_op(expr: str, op: str):
    depth, parts, buf = 0, [], ""
    for ch in expr:
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        
        if ch == op and depth == 0:
            parts.append(buf.strip())
            buf = ""
        else: buf += ch
    if parts:
        parts.append(buf.strip())
        return parts
    return None

def formula_hash(canonical: str) -> str:
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()

# =========================
# Markdown 表格解析器
# =========================
def parse_markdown_table(md_text):
    factors = []
    for line in md_text.strip().split('\n'):
        if '|' not in line: continue
        cols = [c.strip() for c in line.split('|')][1:-1]
        if len(cols) >= 3:
            name = cols[0].replace('**', '').strip()
            formula = cols[1].replace('`', '').strip()
            logic = cols[2].strip()
            if '因子名称' in name or '---' in name: continue
            factors.append({"Factor_Name": name, "Formula": formula, "Logic": logic})
    return factors

def rebuild_markdown_table(factor_list):
    if not factor_list: return ""
    lines = ["| 因子名称 | 计算公式 | 逻辑解释 |", "| :--- | :--- | :--- |"]
    for f in factor_list:
        name = f.get('Factor_Name', 'Unknown')
        formula = f.get('Formula', 'N/A')
        logic = f.get('Logic', 'N/A')
        lines.append(f"| **{name}** | `{formula}` | {logic} |")
    return "\n".join(lines)

# =========================
# SQLite数据库管理 (批量极速版)
# =========================
@contextmanager
def get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path, timeout=15.0)
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
        yield conn
    finally:
        conn.close()

def init_database(db_path: str):
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS formula_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_value TEXT UNIQUE NOT NULL,
                canonical_formula TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hash ON formula_hashes(hash_value)")
        conn.commit()

# 🚨 新增：一次性读取所有指纹到内存
def get_all_hashes(db_path: str) -> set:
    hashes = set()
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT hash_value FROM formula_hashes")
            for row in cursor.fetchall():
                hashes.add(row[0])
    except Exception as e:
        print(f"⚠️ 读取历史指纹警告: {e}")
    return hashes

# 🚨 新增：一次性批量写入新指纹
def insert_hashes_batch(db_path: str, new_records: list):
    if not new_records:
        return
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            # 使用 INSERT OR IGNORE 极速批量写入，自动忽略潜在重复
            cursor.executemany(
                "INSERT OR IGNORE INTO formula_hashes (hash_value, canonical_formula) VALUES (?, ?)",
                new_records
            )
            conn.commit()
    except Exception as e:
        print(f"⚠️ 批量写入指纹警告: {e}")


# =========================
# 内存级安检拦截器 (彻底解决锁库问题)
# =========================
def filter_unique_factors_in_memory(factor_list: list, db_path: str) -> list:
    if not factor_list:
        return []
        
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    init_database(db_path)
    
    # 🚨 1. 提档：把全量历史指纹一次性加载到 Python 内存！(数据库立刻释放锁)
    existing_hashes = get_all_hashes(db_path)
    
    unique_factors = []
    new_records_to_db = [] # 暂存新因子的指纹
    duplicate_count = 0

    # 🚨 2. 纯内存比对：循环期间绝对不碰硬盘！
    for factor in factor_list:
        formula = factor.get('Formula') or factor.get('formula') or factor.get('math', '')
        factor_name = factor.get('Factor_Name') or factor.get('name', 'Unknown')
        
        if not formula or formula == "N/A":
            unique_factors.append(factor)
            continue
            
        try:
            ast = parse_formula(str(formula))
            canonical = ast.canonical()
            h = formula_hash(canonical)
            
            # 直接在 Python 的 set 里查，极速且无锁！
            if h in existing_hashes:
                duplicate_count += 1
                print(f"   ♻️ [安检拦截] {factor_name} 逻辑已在历史库中，舍弃！")
            else:
                existing_hashes.add(h) # 更新内存集合，防止同一批次内出现双胞胎
                new_records_to_db.append((h, canonical)) # 记下这笔新账
                unique_factors.append(factor)
        except Exception as e:
            print(f"   ⚠️ 公式解析异常，默认放行: {factor_name}. 报错: {e}")
            unique_factors.append(factor)

    # 🚨 3. 落盘：只有在一切比对结束后，才开一次门把新账本批量存进去
    if new_records_to_db:
        insert_hashes_batch(db_path, new_records_to_db)

    print(f"🛡️ [安检完毕] 提交 {len(factor_list)} 个 -> 拦截重复 {duplicate_count} 个 -> 放行全新 {len(unique_factors)} 个。")
    return unique_factors