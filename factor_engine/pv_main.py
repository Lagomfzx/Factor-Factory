from __future__ import annotations

from pathlib import Path

from langchain_openai import ChatOpenAI

from factor_engine.common.config import FactoryConfig
from factor_engine.common.platform_api import clean_platform_result
from factor_engine.common.runtime_env import (
    get_env,
    get_int_env,
    load_dotenv_files,
    project_root,
    require_env,
)
from factor_engine.common.storage import tag_kept_factors
from factor_engine.factories.price_volume.local_calc_pv import load_data_as_matrices
from factor_engine.factories.price_volume.pipeline_pv import run_pipeline_matrix_v2
from factor_engine.factories.price_volume.prompts_pv import CICC_STRATEGIES, build_stage1_system_prompt
from factor_engine.operators.op_price_volume import operator_lib_header
from factor_engine.optimizer.price_volume.data_bridge import (
    build_judge_context,
    extract_and_sync_genius_factors,
    get_optimization_queue,
)
from factor_engine.optimizer.price_volume.evolution_loop import run_evolutionary_loop
from factor_engine.optimizer.price_volume.llm_agents import run_judge_workflow


load_dotenv_files()

PROJECT_ROOT = project_root()
DEFAULT_PV_DATA_PATH = PROJECT_ROOT / "mydata" / "cs_wfq_data.feather"


def _build_chat_client(*, model_name: str) -> ChatOpenAI:
    api_key = require_env(
        "FACTOR_FACTORY_LLM_API_KEY",
        aliases=["OPENAI_API_KEY"],
        hint="set it in .env or .env.local before running pv_main.py",
    )
    base_url = get_env("FACTOR_FACTORY_LLM_BASE_URL", aliases=["OPENAI_BASE_URL"])
    timeout = get_int_env("FACTOR_FACTORY_LLM_TIMEOUT", default=120)
    max_retries = get_int_env("FACTOR_FACTORY_LLM_MAX_RETRIES", default=5)

    kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": 0,
        "max_retries": max_retries,
        "timeout": timeout,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


# def _strip_code_fences(text: str) -> str:
#     if not text:
#         return text

#     text = text.strip()

#     match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.S)
#     if match:
#         return match.group(1).strip()

#     return text.replace("```python", "").replace("```", "").strip()


def build_clients() -> tuple[ChatOpenAI, ChatOpenAI]:
    judge_model = get_env("FACTOR_FACTORY_PV_JUDGE_MODEL", default="qwen3-max") or "qwen3-max"
    coder_model = get_env("FACTOR_FACTORY_PV_CODER_MODEL", default=judge_model) or judge_model
    return _build_chat_client(model_name=judge_model), _build_chat_client(model_name=coder_model)


def main() -> None:
    # folder_path = Path(get_env("FACTOR_FACTORY_PV_DATA_PATH", default=str(DEFAULT_PV_DATA_PATH)) or DEFAULT_PV_DATA_PATH)
    # macro_rounds = get_int_env("FACTOR_FACTORY_PV_MACRO_ROUNDS", default=90)
    # pv_version = get_env("FACTOR_FACTORY_PV_VERSION", default="v6") or "v6"
    # pv_output_base_dir = get_env("FACTOR_FACTORY_PV_OUTPUT_BASE_DIR", default="mydata/output") or "mydata/output"

    # input_data = get_env("FACTOR_FACTORY_PV_INPUT_DATA", default="请开始你的挖掘") or "请开始你的挖掘"

    # client_judge_doctor, client_coder = build_clients()

    # matrix_dict = load_data_as_matrices(str(folder_path))
    # style_keys = list(CICC_STRATEGIES.keys())
    # pv_config = FactoryConfig(factory_name="pv", version=pv_version)
    folder_path = Path(get_env("FACTOR_FACTORY_PV_DATA_PATH", default=str(DEFAULT_PV_DATA_PATH)) or DEFAULT_PV_DATA_PATH)
    macro_rounds = get_int_env("FACTOR_FACTORY_PV_MACRO_ROUNDS", default=90)
    pv_version = get_env("FACTOR_FACTORY_PV_VERSION", default="v6") or "v6"
    pv_output_base_dir = (
        get_env(
            "FACTOR_FACTORY_PV_OUTPUT_BASE_DIR",
            default="/storage/server/145server/ly/luodan/data/output",
        )
        or "/storage/server/145server/ly/luodan/data/output"
    )
    input_data = get_env("FACTOR_FACTORY_PV_INPUT_DATA", default="请开始你的挖掘") or "请开始你的挖掘"
    
    client_judge_doctor, client_coder = build_clients()
    
    matrix_dict = load_data_as_matrices(str(folder_path))
    style_keys = list(CICC_STRATEGIES.keys())
    pv_config = FactoryConfig(
        factory_name="pv",
        version=pv_version,
        base_dir=pv_output_base_dir,
    )


    for round_idx in range(macro_rounds):
        current_style_name = style_keys[round_idx % len(style_keys)]
        style_info = CICC_STRATEGIES[current_style_name]
        current_stage1_system_prompt = build_stage1_system_prompt(current_style_name, style_info)
        current_input_data = (
            f"{input_data}\n"
            f"【本轮风格聚焦】{current_style_name}\n"
            f"核心命题：{style_info.get('desc', '')}\n"
            f"研究提示：{style_info.get('logic', '')}\n"
            f"公式提示：\n{style_info.get('formula_guidance', '')}"
        )

        print(f"\n{'=' * 60}")
        print(f"🏭 因子工厂 宏观生产线 - 第 {round_idx + 1}/{macro_rounds} 批次启动")
        print(f"🎯 本轮专家模式: {current_style_name}")
        print("============================================================")

        gen_job_id, llm1_text, llm3_text, gen_res_json = run_pipeline_matrix_v2(
            config=pv_config,
            matrix_dict=matrix_dict,
            input_data=current_input_data,
            client1=client_judge_doctor,
            client2=client_coder,
            operator_lib_header=operator_lib_header,
            stage1_system_prompt=current_stage1_system_prompt,
        )

        if not gen_res_json or not gen_res_json.get("results"):
            print("⚠️ 本批次生成模块回测失败或无有效结果，跳过后续环节。")
            continue

        print("\n🌉 [桥接中] 正在将生成模块产物送入战略质检局...")
        clean_list = [clean_platform_result(item) for item in gen_res_json["results"]]
        judge_context = build_judge_context(clean_list, llm1_text, llm3_text)

        decisions = run_judge_workflow(judge_context, client_judge_doctor)
        extract_and_sync_genius_factors(decisions, gen_job_id, config=pv_config)
        tag_kept_factors(decisions, gen_job_id, config=pv_config)

        opt_tasks = get_optimization_queue(decisions, judge_context)
        if opt_tasks:
            print(f"\n🚑 共有 {len(opt_tasks)} 个潜力粗胚被送入进化车间，开始深加工...")
            run_evolutionary_loop(
                config=pv_config,
                initial_tasks=opt_tasks,
                client1=client_judge_doctor,
                client2=client_coder,
                matrix_dict=matrix_dict,
                max_rounds=3,
            )
        else:
            print("🍵 本批次没有挖掘到值得优化的潜力因子，直接进入下一轮宏观挖掘。")

    print("\n🎉🎉🎉 所有批次运行圆满结束！请前往 Streamlit 查看你的战果！")


if __name__ == "__main__":
    main()
