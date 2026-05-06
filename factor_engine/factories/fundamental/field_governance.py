from __future__ import annotations

import json
from pathlib import Path


DEFAULT_DENOMINATOR_CANDIDATES = [
    "BS_TOTALASSETS",
    "BS_TOTALSHAREHOLDEREQUITY",
    "BS_TOTALEQUITY",
    "IS_OPERATINGREVENUE",
    "IS_REVENUE",
    "CFS_NETOPERATECASHFLOW",
]


def _normalize_field_list(items) -> list[str]:
    normalized = []
    for item in items or []:
        value = str(item).strip()
        if value:
            normalized.append(value)
    return sorted(set(normalized))


def _normalize_field_map(payload) -> dict[str, str]:
    normalized = {}
    for key, value in (payload or {}).items():
        field = str(key).strip()
        note = str(value).strip()
        if field and note:
            normalized[field] = note
    return normalized


def _filter_known_fields(items, known_fields: set[str]) -> tuple[list[str], list[str]]:
    valid = []
    unknown = []
    for field in _normalize_field_list(items):
        if field in known_fields:
            valid.append(field)
        else:
            unknown.append(field)
    return valid, unknown


def _resolve_governance_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    return candidate.expanduser()


def _build_default_governance(useful_fields: list[str]) -> dict:
    known_fields = set(_normalize_field_list(useful_fields))
    denominator_fields = [
        field for field in DEFAULT_DENOMINATOR_CANDIDATES if field in known_fields
    ]
    return {
        "source_path": "",
        "has_manual_rules": False,
        "allowed_fields": sorted(known_fields),
        "focus_fields": [],
        "denominator_fields": denominator_fields,
        "cautious_fields": [],
        "note_fields": [],
        "blocked_fields": [],
        "field_notes": {},
        "unknown_fields": {},
    }


def load_field_governance(
    useful_fields: list[str],
    path: str | Path | None = None,
) -> dict:
    governance = _build_default_governance(useful_fields)
    governance_path = _resolve_governance_path(path)
    if governance_path is None or not governance_path.exists():
        return governance

    payload = json.loads(governance_path.read_text(encoding="utf-8"))
    known_fields = set(governance["allowed_fields"])

    allowed_override, unknown_allowed = _filter_known_fields(
        payload.get("allowed_fields", []),
        known_fields,
    )
    blocked_fields, unknown_blocked = _filter_known_fields(
        payload.get("blocked_fields", []),
        known_fields,
    )

    if allowed_override:
        allowed_fields = sorted(set(allowed_override) - set(blocked_fields))
    else:
        allowed_fields = sorted(known_fields - set(blocked_fields))

    allowed_set = set(allowed_fields)

    focus_fields, unknown_focus = _filter_known_fields(
        payload.get("focus_fields", []),
        allowed_set,
    )
    denominator_fields, unknown_denominator = _filter_known_fields(
        payload.get("denominator_fields", []),
        allowed_set,
    )
    cautious_fields, unknown_cautious = _filter_known_fields(
        payload.get("cautious_fields", []),
        allowed_set,
    )
    note_fields, unknown_note = _filter_known_fields(
        payload.get("note_fields", []),
        allowed_set,
    )

    field_notes = {}
    for field, note in _normalize_field_map(payload.get("field_notes")).items():
        if field in allowed_set:
            field_notes[field] = note

    if not denominator_fields:
        denominator_fields = [
            field for field in DEFAULT_DENOMINATOR_CANDIDATES if field in allowed_set
        ]

    governance.update(
        {
            "source_path": str(governance_path),
            "has_manual_rules": True,
            "allowed_fields": allowed_fields,
            "focus_fields": focus_fields,
            "denominator_fields": denominator_fields,
            "cautious_fields": cautious_fields,
            "note_fields": note_fields,
            "blocked_fields": blocked_fields,
            "field_notes": field_notes,
            "unknown_fields": {
                "allowed_fields": unknown_allowed,
                "blocked_fields": unknown_blocked,
                "focus_fields": unknown_focus,
                "denominator_fields": unknown_denominator,
                "cautious_fields": unknown_cautious,
                "note_fields": unknown_note,
            },
        }
    )
    return governance


def summarize_field_governance(governance: dict) -> dict[str, int]:
    return {
        "allowed_fields": len(governance.get("allowed_fields", [])),
        "focus_fields": len(governance.get("focus_fields", [])),
        "denominator_fields": len(governance.get("denominator_fields", [])),
        "cautious_fields": len(governance.get("cautious_fields", [])),
        "note_fields": len(governance.get("note_fields", [])),
        "blocked_fields": len(governance.get("blocked_fields", [])),
        "field_notes": len(governance.get("field_notes", {})),
    }


def save_field_governance_snapshot(governance: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(governance, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
