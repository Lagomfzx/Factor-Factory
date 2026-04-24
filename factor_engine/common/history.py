import re
from pathlib import Path
import os
from datetime import datetime

# ================= 新增这两行常量定义 =================
CHN_RANGE = r"\u4e00-\u9fff"
# HISTORY_FILE_v6 = "mydata/output/llm_output/factor_gpt_history_v6.txt"
# HISTORY_FILE_v7 = "mydata/output/llm_output/factor_gpt_history_v7.txt"
# ===================================================

def compress_factor_table(md_text: str) -> str:
    """
    从 LLM 返回的 markdown 因子表格中提取【因子名称 + 计算方式】两列，
    以纯文本形式返回，用于历史记忆瘦身。
    行格式示例：
        Volatility-Adjusted Momentum: VAM_t = ...
    """
    lines = md_text.splitlines()
    rows = []

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue

        # 去掉两侧竖线
        inner = line.strip("|").strip()

        # 跳过分隔线行：比如 '---------|---------|---------'、':---|:---|' 等
        inner_no_pipes = inner.replace("|", "").strip()
        if inner_no_pipes and set(inner_no_pipes) <= set("-:"):
            continue

        # 用“| + 中文”确定【公式列】和【解释说明】之间的那根竖线（取最后一个）
        cn_bar_match = None
        pattern = rf"\|[ \t]*[{CHN_RANGE}]"
        for m in re.finditer(pattern, inner):
            cn_bar_match = m

        # 如果这一行根本没有“| + 中文”，大概率不是标准的因子行，直接跳过
        if not cn_bar_match:
            continue

        bar_idx = cn_bar_match.start()   # 竖线所在的位置
        left = inner[:bar_idx].rstrip()  # 左侧：名称 + 公式两列
        # right = inner[bar_idx+1:].lstrip()  # 右侧是中文解释，你要丢掉就不用管

        # 再在左侧拆一次：只拆第一个“未被反斜杠转义”的 '|'
        parts = [c.strip() for c in re.split(r'(?<!\\)\|', left, maxsplit=1)]
        if len(parts) < 2:
            continue

        name, formula = parts[0], parts[1]

        # 跳过表头
        if name in ("因子名称", "Factor Name", "名称"):
            continue

        # 清理公式两侧的反引号
        formula = formula.strip()
        if formula.startswith("`") and formula.endswith("`"):
            formula = formula[1:-1].strip()

        # 反转义 '\|' → '|'
        formula = formula.replace(r"\|", "|")

        if name and formula:
            rows.append(f"{name}: {formula}")

    # 如果没解析出任何行，就退回原文，避免写入空历史
    return "\n".join(rows) if rows else md_text.strip()


def append_factor_history(text: str, config) -> None:
    """
    将本轮 LLM 生成的因子表格写入历史文件。
    写入前先用 compress_factor_table 做瘦身，只保留“因子名称: 公式”。
    """
    path = config.history_file
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 🌟 核心：先瘦身，再写入
    slim_text = compress_factor_table(text)

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n\n" + "="*80 + f"\n# ROUND @ {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
        f.write(slim_text.strip())


def load_factor_history(config, max_rounds: int = 30) -> str:
    """读取最近 max_rounds 段历史（按 '# ROUND' 分割）。不存在则返回空串。"""
    path = config.history_file
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    blocks = [b.strip() for b in txt.split("\n# ROUND ") if b.strip()]
    if not blocks:
        return ""
    return "\n\n".join("# ROUND " + b for b in blocks[-max_rounds:])