"""Optimizer package facade.

Public optimizer APIs are exposed from the strategy-specific subpackages:
- ``factor_engine.optimizer.price_volume``
- ``factor_engine.optimizer.fundamental``
"""

from factor_engine.optimizer.price_volume.data_bridge import (
    build_judge_context,
    extract_and_sync_genius_factors,
    get_optimization_queue,
    load_json_data,
)
from factor_engine.optimizer.price_volume.evolution_loop import run_evolutionary_loop
from factor_engine.optimizer.price_volume.llm_agents import (
    parse_markdown_table_to_list,
    run_coder_step,
    run_doctor_step,
    run_judge_workflow,
)
from factor_engine.optimizer.price_volume.prompts_opt import (
    CODER_PROMPT_TEMPLATE,
    DOCTOR_SYSTEM_BASE,
    DOCTOR_TABLE_SYSTEM_PROMPT,
    DOCTOR_TABLE_USER_TEMPLATE,
    DOCTOR_USER_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_TEMPLATE,
    REFEREE_PROMPT,
)

__all__ = [
    "build_judge_context",
    "extract_and_sync_genius_factors",
    "get_optimization_queue",
    "load_json_data",
    "run_evolutionary_loop",
    "parse_markdown_table_to_list",
    "run_coder_step",
    "run_doctor_step",
    "run_judge_workflow",
    "CODER_PROMPT_TEMPLATE",
    "DOCTOR_SYSTEM_BASE",
    "DOCTOR_TABLE_SYSTEM_PROMPT",
    "DOCTOR_TABLE_USER_TEMPLATE",
    "DOCTOR_USER_TEMPLATE",
    "JUDGE_SYSTEM_PROMPT",
    "JUDGE_USER_TEMPLATE",
    "REFEREE_PROMPT",
]
