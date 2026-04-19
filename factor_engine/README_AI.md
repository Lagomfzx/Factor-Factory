# 给接手 AI 的项目说明

这份文档的目标很明确：

当你把它发给另一个 AI 时，对方应该能在极短时间内理解：

1. 这个项目到底在做什么
2. 项目的完整流程如何运转
3. 量价工厂和财务工厂分别以什么为准
4. 哪些模块已经成熟，哪些模块刚完成接线
5. 接下来应该从哪里继续开发，而不是重新摸索一遍

## 1. 项目目标

这是一个“因子工厂”项目，不是单纯的因子脚本集合。

项目的核心目标是借助大模型与本地/远程计算能力，形成一条自动化因子研发闭环：

1. 生成候选因子
2. 本地与远程评估因子表现
3. 对生成结果进行判官初审
4. 将优秀因子保留并入库
5. 将有潜力但不够好的因子送入优化/进化模块
6. 持续迭代并沉淀历史、标签、精品库

可以把整个项目理解成：

`因子生成工厂 + 判官筛选系统 + 进化优化系统 + 注册表/精品库存储系统`

## 2. 最重要的理解方式

理解这个项目最有效的方法，是把它拆成两个大模块：

### A. 生成模块

这一部分负责：

- Prompt 组装
- 三阶段大模型调用
- 代码生成与纠错
- 本地因子计算
- 远程平台提交
- 回测结果拉取

### B. 优化模块

这一部分负责：

- 把生成因子整理成判官可读上下文
- 判官做初审
- `KEEP / OPTIMIZE` 分流
- 优质因子同步到精品库
- 待优化因子进入进化循环
- 保存进化历史、判官记录、标签记录

量价工厂已经完整拥有这两部分。

财务工厂目前的策略是：

- **生成模块**：严格以已验证 notebook 为准
- **优化模块**：复用量价工厂已经成熟的判官/进化/入库框架

## 3. 当前项目中的真实基准

### 量价工厂基准

量价工厂的主入口是：

- [`factor_engine/pv_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/pv_main.py)

这个文件可以视为“成熟总控模板”。
如果另一个 AI 想理解什么叫完整工厂流程，先看它。

### 财务工厂基准

财务工厂的生成逻辑基准不是旧模块，而是已经被验证过有效的 notebook：

- [`因子工厂jbm_4.1_dj_q (1).ipynb`](</C:/Users/Administrator/Desktop/因子工厂代码/因子工厂jbm_4.1_dj_q (1).ipynb>)

这是财务工厂最重要的事实来源。

如果财务模块里的旧代码与 notebook 有冲突，**一律以 notebook 为准**。

财务工厂当前 Python 入口是：

- [`factor_engine/fund_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/fund_main.py)

它的职责不是重新发明财务逻辑，而是把 notebook 中已验证的“前半段生成模块”接进项目原有的“后半段判官与进化框架”。

## 4. 项目总体架构

### 4.1 公共基础设施

- [`factor_engine/common/config.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/common/config.py)
  定义 `FactoryConfig`，负责统一管理工厂版本、输出目录、注册表路径、历史文件路径等。

- [`factor_engine/common/platform_api.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/common/platform_api.py)
  负责远程平台任务提交、轮询、回测结果保存、平台结果清洗。

- [`factor_engine/common/storage.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/common/storage.py)
  负责主注册表、精品注册表、标签表、研究记录、进化记录的存储。

- [`factor_engine/common/history.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/common/history.py)
  负责生成历史记忆，供下一轮 Prompt 参考，减少重复生成。

- [`factor_engine/common/deduplicator.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/common/deduplicator.py)
  负责公式规范化与 hash 去重。

### 4.2 算子库

- [`factor_engine/operators/op_price_volume.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/operators/op_price_volume.py)
- [`factor_engine/operators/op_fundamental.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/operators/op_fundamental.py)

这两个文件是生成代码时会注入的大类算子库。

### 4.3 量价工厂模块

- [`factor_engine/factories/price_volume/pipeline_pv.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/price_volume/pipeline_pv.py)
- [`factor_engine/factories/price_volume/local_calc_pv.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/price_volume/local_calc_pv.py)
- [`factor_engine/factories/price_volume/llm_chains_pv.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/price_volume/llm_chains_pv.py)
- [`factor_engine/factories/price_volume/prompts_pv.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/price_volume/prompts_pv.py)

### 4.4 财务工厂模块

- [`factor_engine/factories/fundamental/pipeline_fund.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/fundamental/pipeline_fund.py)
- [`factor_engine/factories/fundamental/local_calc_fund.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/fundamental/local_calc_fund.py)
- [`factor_engine/factories/fundamental/llm_chain_fund.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/fundamental/llm_chain_fund.py)
- [`factor_engine/factories/fundamental/prompt_fund.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/factories/fundamental/prompt_fund.py)

### 4.5 判官与优化模块

- [`factor_engine/optimizer/data_bridge.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/optimizer/data_bridge.py)
- [`factor_engine/optimizer/llm_agents.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/optimizer/llm_agents.py)
- [`factor_engine/optimizer/evolution_loop.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/optimizer/evolution_loop.py)
- [`factor_engine/optimizer/fundamental/evolution_loop_fund.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/optimizer/fundamental/evolution_loop_fund.py)

## 5. 完整流程

## 5.1 量价工厂完整流程

量价工厂入口是 [`pv_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/pv_main.py)。

它的完整流程是：

1. 构建 `FactoryConfig(factory_name="pv", version="v6")`
2. 加载量价底层矩阵 `matrix_dict`
3. 按 `CICC_STRATEGIES` 的风格轮询生成
4. 调用 `run_pipeline_matrix_v2(...)`
5. 得到：
   - `gen_job_id`
   - `llm1_text`
   - `llm3_text`
   - `gen_res_json`
6. 使用 `clean_platform_result` 清洗远程回测指标
7. 用 `build_judge_context` 组装判官上下文
8. 用 `run_judge_workflow` 进行初审
9. 用 `extract_and_sync_genius_factors` 把 `KEEP` 因子同步到精品库
10. 用 `tag_kept_factors` 给优秀因子打标签
11. 用 `get_optimization_queue` 提取需要继续优化的因子
12. 调用 `run_evolutionary_loop(...)` 进入进化循环

这是项目中最成熟、最完整的参考链路。

## 5.2 财务工厂完整流程

财务工厂入口是 [`fund_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/fund_main.py)。

它的完整流程设计为：

1. 构建 `FactoryConfig(factory_name="fund", version="v7")`
2. 用 `generate_snapshot_calendar(2016, 2025)` 构建季频快照日历
3. 从财务数据目录读取可用字段
4. 按财务风格策略 `prompt_fund.CICC_STRATEGIES` 轮询生成
5. 构建当前轮的 system prompt 和 user instruction
6. 调用 `run_hybrid_pipeline(...)`

### `run_hybrid_pipeline(...)` 内部流程

这部分严格对齐 notebook 的有效逻辑：

1. 初始化 `LazyFactorDB`
2. 初始化 `FactorExecutor`
3. 调用 `run_three_stages_with_memory(...)` 进行三阶段大模型生成
4. 将生成代码提交远程平台，并带上 `use_fundamental = 1`
5. 将本轮生成的逻辑、公式、代码写入主注册表
6. 通过 `parse_code_to_functions + FactorExecutor.run` 做本地财务因子计算
7. 本地落盘为 parquet
8. 轮询远程回测结果并保存 JSON

### 回到 `fund_main.py` 之后

1. 对平台结果做 `clean_platform_result`
2. 调用 `build_judge_context`
3. 用 `run_judge_workflow` 做初审
4. 用 `extract_and_sync_genius_factors` 同步优秀因子到精品库
5. 用 `tag_kept_factors` 打标签
6. 用 `get_optimization_queue` 提取需要继续优化的财务因子
7. 调用 `run_evolutionary_loop_fund(...)` 进行财务因子的进化优化

## 5.3 财务工厂的关键原则

财务工厂不是简单照搬量价工厂。

它的正确理解是：

- **前半段生成模块**：以 notebook 为准
- **后半段判官/筛选/优化模块**：接入量价工厂已经成熟的框架

也就是说，复用的是流程框架，不是复用量价的数据执行逻辑。

## 5.4 进化模块流程

无论量价还是财务，进化模块结构都基本一致：

1. Doctor 模块给出优化处方
2. Coder 模块生成优化后的因子变体
3. 平台评估这些变体
4. 本地执行并保存实体文件
5. Referee / 判官决定：
   - `KEEP`
   - `EVOLVE`
   - `PIVOT`
   - `TERMINATE`
6. `KEEP` 因子进入精品库
7. `EVOLVE` 与部分 `PIVOT` 因子进入下一轮

## 6. 保存逻辑与版本语义

每个工厂版本都有两个核心层级：

## 6.1 主注册表

所有成功生成并成功索引的因子，会先进入主注册表：

- `config.registry_csv`

例如：

- 量价 `v6`
- 财务 `v7`

它代表“本版本生成总库”。

## 6.2 精品注册表

判官认为优秀、通常是 `decision == KEEP` 的因子，会同步进入精品库：

- `config.premium_registry_csv`

例如：

- 量价 `v6.1`
- 财务 `v7.1`

它代表“本版本精选精品库”。

## 6.3 正确理解保存流程

是的，可以这样理解：

1. 生成模块产出的因子，先进入主库，例如 `v7`
2. 判官认为好的因子，再进入精品库，例如 `v7.1`
3. 待优化因子进入优化模块继续进化
4. 进化出来的优秀因子，也会继续进入 `v7.1`

所以“财务工厂中大模型觉得好的就保留在 `v7.1`”这个理解是正确的，但更准确地说是：

- **先入 `v7`**
- **再由判官筛到 `v7.1`**

## 7. 什么是当前的真源

### 对量价工厂

当前 Python 模块就是事实标准。

### 对财务工厂

事实标准优先级如下：

1. 已验证 notebook
2. 当前已对齐 notebook 的 `fundamental` Python 模块
3. 更早期的实验性代码

如果另一个 AI 不确定财务生成逻辑应该怎么做，先看 notebook，不要先相信旧碎片代码。

## 8. 财务工厂的关键数据假设

财务工厂不是普通日频面板。

它使用季频快照对齐：

- `04-30`
- `08-30`
- `10-30`

这会直接影响以下算子的含义：

- `Delay`
- `YOY`
- `QOQ`
- `TTM`

任何 AI 如果改财务工厂，都必须保留这个前提，除非明确要整体重构。

## 9. 当前已经完成到什么程度

### 量价工厂

量价工厂已经是成熟线，具备：

- 完整生成
- 完整判官初审
- 完整筛选逻辑
- 完整进化模块
- 完整注册表与精品库存储

### 财务工厂

财务工厂目前的状态是：

- 生成模块：已经尽量按 notebook 对齐
- 总控入口：已经有 `fund_main.py`
- 判官初审：已经接入共享框架
- 进化模块：已经接入财务版 `run_evolutionary_loop_fund`
- 保存逻辑：已经接入主库与精品库语义

但它仍然需要在真实环境里继续跑通验证。

也就是说，现在财务工厂在“结构上已经接通”，但仍然需要运行级验证。

## 10. 当前已知风险与薄弱点

未来接手这个项目的 AI，应该重点注意：

- 仍然存在硬编码 API Key
- 仍然存在硬编码本地/网络路径
- 某些旧文件存在 Windows 编码痕迹
- 当前环境下不一定能直接调用 `git`
- 当前环境下 `python` 命令行为可能受限，不能完全依赖命令行编译检查
- 财务工厂虽然已经接好，但还需要真实跑一轮验证

## 11. 接手 AI 的推荐阅读顺序

如果另一个 AI 接手项目，建议按以下顺序理解：

1. 先读这份文档
2. 读 [`factor_engine/pv_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/pv_main.py)
   理解完整成熟工厂应该怎么调度
3. 读 [`因子工厂jbm_4.1_dj_q (1).ipynb`](</C:/Users/Administrator/Desktop/因子工厂代码/因子工厂jbm_4.1_dj_q (1).ipynb>)
   理解财务工厂前半段生成模块的真实来源
4. 读 [`factor_engine/fund_main.py`](C:/Users/Administrator/Desktop/因子工厂代码/factor_engine/fund_main.py)
   理解 notebook 风格生成模块如何接入共享后半段
5. 再读 `common/config.py`、`common/storage.py`、`optimizer/data_bridge.py`
   理解版本、注册表、精品库与判官桥接

## 12. 接手 AI 不应该做的事

- 不要在没有用户明确要求的情况下，推翻财务 notebook 的生成逻辑
- 不要把财务工厂重新改回普通日频逻辑
- 不要随意改变 `v7` 与 `v7.1` 的语义
- 不要因为 notebook 原本没有判官模块，就把后半段闭环删掉
- 不要贸然回退仓库里无关文件

## 13. 接下来最有价值的任务

如果另一个 AI 要继续推进项目，优先级最高的任务是：

1. 把硬编码路径和 API Key 抽到环境变量或配置文件
2. 真正运行 `fund_main.py` 一轮并修复运行级问题
3. 给量价与财务工厂分别补最小 smoke test
4. 增加结构化日志，至少覆盖：
   - 生成 job id
   - 判官决策
   - 精品库同步
   - 进化分叉结果

## 14. 一句话总结

这是一个双产线因子工厂：

- `price_volume` 是成熟参考实现
- `fundamental` 的生成模块以已验证 notebook 为真源，并接入相同的判官、优化、保存框架

如果你是接手这个仓库的另一个 AI：

- 用 `pv_main.py` 理解完整工厂
- 用 notebook 理解财务生成真相
- 用 `fund_main.py` 理解两者是如何接起来的
