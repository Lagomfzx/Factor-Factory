# factor_engine/optimizer/evolution_loop.py

import json
import os
import pandas as pd
from factor_engine.factories.price_volume.local_calc_pv import extract_calculators_vectorized, apply_matrix_calculators
from factor_engine.operators.op_price_volume import matrix_operators
from factor_engine.common.storage import OptimizationStorage, sync_to_streamlit_registry, sync_to_v6_1_registry
from factor_engine.common.platform_api import submit_batch_factors
from factor_engine.optimizer.llm_agents import run_doctor_step, run_coder_step
from factor_engine.operators.op_price_volume import operator_lib_header  
from factor_engine.optimizer.prompts_opt import REFEREE_PROMPT


# 🚨 终极改造 1：签名里开除 base_out，迎接 config 图纸！
def run_evolutionary_loop(config, initial_tasks, client1, client2, matrix_dict, max_rounds=3):
    """
    【进化引擎 v5.0 - 全局图纸解耦版】
    彻底消灭所有硬编码，全系统由 config 统一调度。
    """
    current_queue = initial_tasks 
    hall_of_fame = [] 
    
    # 🚨 终极改造 2：不再手写路径，直接把图纸扔给存储器！
    storage = OptimizationStorage(config)

    for round_idx in range(1, max_rounds + 1):
        round_label = f"round_{round_idx}"
        print(f"\n🔄 ========== 第 {round_idx} 轮批量进化启动 ({round_label}) ==========")
        
        if not current_queue: 
            print("🍵 任务队列已空，进化提前结束。")
            break

        prescriptions = run_doctor_step(current_queue, client1, round_idx)
        
        new_factors = run_coder_step(prescriptions, client2)
        if not new_factors:
            print(f"⚠️ 第 {round_idx} 轮未能生成有效代码，跳过。")
            continue

        storage.save_full_records(round_label, new_factors)

        batch_job_id, batch_results = submit_batch_factors(new_factors, operator_lib_header)
        
        if batch_job_id:
            # 🚨 终极改造 3：必须把 config 传给总账本同步器！
            sync_to_streamlit_registry(batch_job_id, new_factors, config)
            
            # ==========================================
            # 实体数据本地计算并落盘
            # ==========================================
            print(f"🧮 [本地运算] 正在为 {batch_job_id} 计算因子实体文件...")
            try:
                batch_code_text = "\n\n".join([f["Code"] for f in new_factors])
                
                ops_dict = matrix_operators()
                calculators = extract_calculators_vectorized(batch_code_text, ops_dict)
                factor_results = apply_matrix_calculators(matrix_dict, calculators)
                
                # 🚨 终极改造 4：抛弃 base_out，从图纸读取因子存放的根目录！
                run_dir = os.path.join(config.factor_out_dir, str(batch_job_id))
                os.makedirs(run_dir, exist_ok=True)
                
                saved_count = 0
                for fname, factor_df in factor_results.items():
                    if isinstance(factor_df, pd.DataFrame):
                        save_df = factor_df.reset_index()
                        save_df.columns = save_df.columns.astype(str) 
                        save_df.to_parquet(os.path.join(run_dir, f"{fname}.parquet"))
                        saved_count += 1
                print(f"✅ [实体落盘] 已保存 {saved_count} 个进化因子的 parquet 文件至 {run_dir}")
            except Exception as e:
                print(f"❌ 本地计算/落盘出错: {e}")
            # ==========================================
        
        # Step 5: 战略判决与定向分流
        print(f"⚖️ [LLM4 战略裁判] 正在复盘进化成果...")
        next_round_queue = []
        this_round_decisions = [] 
        this_round_kept_factors = []

        for task in new_factors:
            f_name = task['Factor_Name']
            child_metrics = batch_results.get(f_name)
            
            if not child_metrics or child_metrics.get('RankIC') == "N/A":
                continue
            
            parent_task = next((p for p in current_queue if p['name'] == task['Parent_Name']), None)
            parent_ic = parent_task.get('metrics', {}).get('RankIC', 0) if parent_task else 0
            parent_icir = parent_task.get('metrics', {}).get('ICIR', 0) if parent_task else 0
            parent_pivot_count = parent_task.get('pivot_count', 0) if parent_task else 0

            prompt_compare = REFEREE_PROMPT.format(
                parent_name=task['Parent_Name'],
                parent_ic=parent_ic,
                parent_icir=parent_icir,
                parent_turnover="N/A",
                child_name=f_name,
                child_ic=child_metrics['RankIC'],
                child_icir=child_metrics['ICIR'],
                child_turnover="N/A",
                doctor_prescription=task['Logic']
            )
            
            try:
                resp = client1.invoke([{"role": "user", "content": prompt_compare}])
                content = getattr(resp, "content", str(resp))
                clean_json = content.replace("```json", "").replace("```", "").strip()
                ref_res = json.loads(clean_json)
            except Exception as e:
                print(f"   ⚠️ 判官反馈异常: {e}，启动备用硬核逻辑...")
                ref_res = {
                    "decision": "WIN" if abs(child_metrics['RankIC']) > abs(parent_ic) else "LOSE",
                    "action": "EVOLVE" if abs(child_metrics['RankIC']) > 0.01 else "TERMINATE",
                    "reason": "由于解析错误，系统自动通过数值大小判定",
                    "diagnosis": "请继续增强信号强度"
                }

            this_round_decisions.append({
                "name": f_name,
                "decision": ref_res.get('decision'),
                "action": ref_res.get('action'),
                "reason": ref_res.get('reason'),
                "diagnosis": ref_res.get('diagnosis')
            })

            action = ref_res.get('action')
            ic_val = abs(float(child_metrics.get('RankIC', 0)))
            icir_val = abs(float(child_metrics.get('ICIR', 0)))

            if action == 'KEEP':
                print(f"   🏆 战略入库: {f_name} (IC: {ic_val:.4f}, ICIR: {icir_val:.2f})")
                hall_of_fame.append({**task, "metrics": child_metrics})
                this_round_kept_factors.append(task)
            
            elif action == 'EVOLVE':
                print(f"   🧬 指挥衔接: {f_name} 将执行 [EVOLVE] 指令进入下轮。")
                next_round_queue.append({
                    "name": f_name, "original_logic": task['Logic'], "code": task['Code'],
                    "metrics": child_metrics, "diagnosis": ref_res.get('diagnosis', '顺着该方向继续深化'),
                    "action": "EVOLVE", "pivot_count": 0 
                })
                
            elif action == 'PIVOT':
                if ic_val >= 0.005:
                    if parent_pivot_count >= 1:
                        print(f"   ☠️ 两次转向连败: {f_name} 该基因分支彻底枯竭，执行强制毁灭！")
                    else:
                        print(f"   🔄 战略转向: {f_name} 遇阻，给予最后一次换路机会 [PIVOT]。")
                        next_round_queue.append({
                            "name": f_name, "original_logic": task['Logic'], "code": task['Code'],
                            "metrics": child_metrics, "diagnosis": ref_res.get('diagnosis', '当前方向失效，请彻底更换数学逻辑'),
                            "action": "PIVOT", "pivot_count": parent_pivot_count + 1 
                        })
                else:
                    print(f"   ✂️ 硬性剪枝: {f_name} 虽被判 PIVOT，但 IC ({ic_val:.4f}) 过低如纯噪音，直接剥夺繁衍权。")
                    
            else: 
                print(f"   🔴 路线终结: {f_name} 被战略淘汰 (理由: {ref_res.get('reason')})")

        # 🚨 终极改造 5：千万别忘了把 config 传给精品同步器！
        if this_round_kept_factors and batch_job_id:
            sync_to_v6_1_registry(batch_job_id, this_round_kept_factors, config)
        
        storage.save_decisions(round_label, this_round_decisions)
        current_queue = next_round_queue
        
    print(f"\n✅ 自动化进化流程圆满结束。")
    print(f"🌟 名人堂 (Hall of Fame) 因子数: {len(hall_of_fame)}")
    return hall_of_fame