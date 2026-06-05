from __future__ import annotations

import json
from pathlib import Path


def _field_set(field_governance: dict | None, key: str) -> set[str]:
    return set((field_governance or {}).get(key) or [])


def _field_notes(field_governance: dict | None) -> dict[str, str]:
    return dict((field_governance or {}).get("field_notes") or {})


def infer_statement(field: str) -> str:
    if field.startswith("BS_"):
        return "资产负债表"
    if field.startswith("IS_"):
        return "利润表"
    if field.startswith("CFS_"):
        return "现金流量表"
    return "未知报表"


def infer_role(field: str, note: str = "") -> tuple[str, str]:
    text = f"{field} {note}".upper()
    note_text = note

    if any(key in text for key in ["REVENUE", "SALESREVENUE", "GOODSSALESERVICE"]):
        return "收入/需求类", "关注增长、趋势、历史位置和超预期，描述需求扩张或收缩状态。"
    if any(key in text for key in ["OPERATINGPROFIT", "TOTALPROFIT", "NETPROFIT", "NPPARENT", "OPERSUSTNETP"]):
        return "利润/盈利类", "关注盈利修复、趋势斜率、标准化意外和持续改善。"
    if any(key in text for key in ["COST", "EXPENSE", "RANDD", "TAX", "DEPRECIATION", "AMORTIZATION"]):
        return "成本费用/税费类", "关注费用压力、成本压力、异常上升或下降，以及自身历史位置变化。"
    if field.startswith("CFS_") and any(key in text for key in ["CASH", "CASHFLOW", "PAID", "PROCEEDS", "INFLOW", "OUTFLOW"]):
        return "现金流类", "关注现金兑现、现金流入流出压力、真实造血和现金端异常变化。"
    if any(key in text for key in ["RECEIVABLE", "INVENTOR", "ADVANCEPAYMENT", "CONTRACTUALASSETS"]):
        return "经营资产/营运资本占用类", "关注资产占用、回款压力、库存压力、异常扩张或释放。"
    if "CONTRACTLIABILITY" in text or "合同负债" in note_text or "预收" in note_text or "订单" in note_text:
        return "经营性负债/订单前置类", "关注预收支撑、订单前置、收入确认节奏和需求景气变化。"
    if any(key in text for key in ["PAYABLE", "LIABILITY", "LOAN", "BORROW", "BONDS", "CONTRACTLIABILITY"]):
        return "负债压力/经营性负债类", "关注杠杆压力、偿债压力、供应链融资、预收支撑或负债收缩。"
    if any(key in text for key in ["TOTALASSETS", "SHAREHOLDEREQUITY", "SEWITHOUTMI", "EQUITY"]):
        return "规模/权益结构类", "作为目标科目时重点观察自身扩张速度、历史位置或异常变化。"
    if any(key in text for key in ["GOODWILL", "IMPAIR", "FAIRVALUE", "NONOPERATING", "INVESTINCOME"]):
        return "风险扰动/非核心项目类", "关注异常冲击、质量修正和风险暴露，不宜机械解释为优势。"
    return "待识别科目", "字段语义置信度较低，优先使用通用的水平、同比、历史异常和历史位置模板，并在解释中保持谨慎。"


def recommend_templates(role: str, field: str) -> list[str]:
    if role in {"收入/需求类", "利润/盈利类", "现金流类"}:
        return [
            "YOY(X)",
            "Delta(YOY(X), 1)",
            "Slope(TTM(X), 3)",
            "TS_Surprise(X, 3, 6)",
            "TS_Rank(YOY(X), 6)",
            "TS_Drawdown(TTM(X), 6)",
            "TS_ConsecutiveGrowth(YOY(X), 3)",
            "TS_ZScore(Delta(TTM(X), 3), 6)",
        ]
    if role == "成本费用/税费类":
        return [
            "TTM(X)",
            "YOY(X)",
            "Delta(YOY(X), 1)",
            "TS_ZScore(X, 6)",
            "TS_Rank(X, 6)",
            "TS_PastHighGap(X, 6)",
            "TS_ConsecutiveGrowth(X, 3)",
            "Sub(0, YOY(X))",
        ]
    if role == "经营资产/营运资本占用类":
        return [
            "X",
            "YOY(X)",
            "Delta(YOY(X), 1)",
            "TS_Rank(X, 6)",
            "TS_ZScore(X, 6)",
            "TS_Drawdown(X, 6)",
            "TS_PastHighGap(X, 6)",
            "TS_RegressionResidual(X, 6)",
        ]
    if role in {"负债压力/经营性负债类", "经营性负债/订单前置类"}:
        return [
            "X",
            "YOY(X)",
            "Delta(YOY(X), 1)",
            "TS_Rank(X, 6)",
            "TS_ZScore(X, 6)",
            "Slope(X, 3)",
            "TS_Drawdown(X, 6)",
            "TS_PastHighGap(X, 6)",
        ]
    if role == "规模/权益结构类":
        return [
            "YOY(X)",
            "Delta(YOY(X), 1)",
            "TS_Rank(X, 6)",
            "TS_ZScore(X, 6)",
            "Slope(X, 3)",
            "TS_PastHighGap(X, 6)",
            "TS_ConsecutiveGrowth(X, 3)",
        ]
    if role == "风险扰动/非核心项目类":
        return [
            "X",
            "YOY(X)",
            "TS_ZScore(X, 6)",
            "TS_Rank(X, 6)",
            "TS_RegressionResidual(X, 6)",
            "TS_PastHighGap(X, 6)",
            "TS_SignFlip(X, 1)",
            "Sub(0, TS_ZScore(X, 6))",
        ]
    return [
        "X",
        "YOY(X)",
        "Delta(X, 1)",
        "TS_ZScore(X, 6)",
        "TS_Rank(X, 6)",
        "TS_PastHighGap(X, 6)",
    ]


def build_field_card(field: str, field_governance: dict | None = None) -> dict[str, object]:
    notes = _field_notes(field_governance)
    note = notes.get(field, "")
    role, role_hint = infer_role(field, note)

    tags = []
    for tag_name, governance_key in [
        ("focus", "focus_fields"),
        ("denominator", "denominator_fields"),
        ("cautious", "cautious_fields"),
        ("note_like", "note_fields"),
        ("blocked", "blocked_fields"),
    ]:
        if field in _field_set(field_governance, governance_key):
            tags.append(tag_name)

    cautions = [
        "不要预设高分组或低分组一定更好，最终由回测验证。",
        "严格单科目模式下，每个因子公式只能包含该目标科目，不要额外引入规模锚或其他财务字段。",
    ]
    if "denominator" in tags:
        cautions.append("该字段常被用作规模锚；但作为本轮目标科目时，只研究其自身扩张速度、历史位置或异常变化。")
    if "cautious" in tags or "note_like" in tags:
        cautions.append("该字段需要谨慎使用，优先作为压力、风险、异常或质量修正观察。")
    if role == "待识别科目":
        cautions.append("该字段语义置信度较低；如果难以解释，请生成保守的通用变换，避免强行编造财务故事。")
    if field.startswith("BS_"):
        cautions.append(
            "资产负债表余额类科目的历史高低点绝对差额可能带有公司体量暴露；"
            "优先尝试 TS_Rank、TS_ZScore、YOY 等自身历史无量纲状态，"
            "再将 TS_PastHighGap/TS_PastLowGap 作为补充观察。"
        )

    return {
        "field": field,
        "statement": infer_statement(field),
        "role": role,
        "role_hint": role_hint,
        "governance_tags": tags or ["allowed"],
        "note": note,
        "recommended_templates": recommend_templates(role, field),
        "cautions": cautions,
        "confidence": "low" if role == "待识别科目" else "normal",
    }


def build_field_cards(
    fields: list[str],
    field_governance: dict | None = None,
    *,
    include_low_confidence: bool = True,
) -> list[dict[str, object]]:
    cards = []
    blocked_fields = _field_set(field_governance, "blocked_fields")
    for field in fields:
        if field in blocked_fields:
            continue
        card = build_field_card(field, field_governance)
        if not include_low_confidence and card.get("confidence") == "low":
            continue
        cards.append(card)
    return cards


def save_field_cards(cards: list[dict[str, object]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "fundamental_single_metric_field_cards_v1",
        "description": "One persistent field card per financial account for single-metric factor generation.",
        "cards": cards,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_field_cards(path: str | Path) -> list[dict[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cards = payload.get("cards") if isinstance(payload, dict) else payload
    if not isinstance(cards, list):
        raise ValueError(f"Field cards JSON must contain a list or a cards list: {path}")
    normalized = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        field = str(card.get("field") or "").strip()
        if field:
            normalized.append(card)
    return normalized


def filter_field_cards(
    cards: list[dict[str, object]],
    *,
    target_fields: list[str] | None = None,
    max_cards: int | None = None,
    allowed_fields: set[str] | None = None,
) -> list[dict[str, object]]:
    allowed = set(allowed_fields or [])
    targets = [field for field in (target_fields or []) if field]
    target_set = set(targets)
    selected = []

    if targets:
        by_field = {str(card.get("field")): card for card in cards}
        selected = [by_field[field] for field in targets if field in by_field]
    else:
        selected = list(cards)

    if allowed:
        selected = [card for card in selected if str(card.get("field")) in allowed]
    if target_set:
        selected = [card for card in selected if str(card.get("field")) in target_set]
    if max_cards is not None and max_cards > 0:
        selected = selected[:max_cards]
    return selected


def render_field_card(card: dict[str, object]) -> str:
    note = str(card.get("note") or "暂无人工备注。")
    tags = ", ".join(card.get("governance_tags") or [])
    templates = "；".join(card.get("recommended_templates") or [])
    cautions = "\n".join(f"- {item}" for item in (card.get("cautions") or []))
    return (
        "【目标科目卡片】\n"
        f"字段名：{card.get('field')}\n"
        f"报表位置：{card.get('statement')}\n"
        f"科目角色：{card.get('role')}\n"
        f"治理标签：{tags}\n"
        f"人工备注：{note}\n"
        f"研究提示：{card.get('role_hint')}\n"
        f"建议优先尝试的变换：{templates}\n"
        "注意事项：\n"
        f"{cautions}"
    )
