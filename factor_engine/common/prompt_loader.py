from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROMPT_ASSET_ROOT = Path(__file__).resolve().parents[1] / "prompt_assets"


@lru_cache(maxsize=None)
def _load_prompt_bundle(relative_path: str) -> dict[str, Any]:
    asset_path = PROMPT_ASSET_ROOT / relative_path
    if not asset_path.exists():
        raise FileNotFoundError(f"Prompt asset not found: {asset_path}")
    with asset_path.open(encoding="utf-8") as file:
        loaded = yaml.safe_load(file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Prompt asset must be a mapping: {asset_path}")
    return loaded


def load_prompt_bundle(relative_path: str) -> dict[str, Any]:
    return copy.deepcopy(_load_prompt_bundle(relative_path))


def replace_prompt_tokens(template: str, replacements: dict[str, object] | None = None) -> str:
    rendered = str(template)
    for token, value in (replacements or {}).items():
        rendered = rendered.replace(str(token), "" if value is None else str(value))
    return rendered
