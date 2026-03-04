# MuseGraph vs MiroFish 核查（2026-03-03）

## 对照范围
1. 本体：`MiroFish/backend/app/services/ontology_generator.py` vs `MuseGraph/apps/server-py/app/services/ontology.py`
2. 图谱：`MiroFish/backend/app/services/graph_builder.py` vs `MuseGraph/apps/server-py/app/services/cognee.py` + `routers/cognee_graph.py`
3. 模拟：`MiroFish/backend/app/services/simulation_config_generator.py` + `api/simulation.py` vs `MuseGraph/apps/server-py/app/routers/simulation.py` + `services/oasis.py`
4. 报告：`MiroFish/backend/app/services/report_agent.py` + `api/report.py` vs `MuseGraph/apps/server-py/app/routers/report.py` + `services/oasis.py`

## 已对齐（本轮）
1. 移除本体 fallback/mode：失败不再返回 `CONCEPT/RELATED_TO`，前端不再展示 `Mode`。
2. OASIS 分析/配置/报告改为严格模式：
   - LLM 输出非 JSON 或结构不合法时直接失败。
   - 不再注入默认分析、默认配置、默认报告 markdown。
3. 模拟改为严格 LLM 产物：
   - 不再使用模板帖子/评论 `template_fallback`。
   - 无有效 profile/config/rounds/posts 时直接失败并返回可读错误。
4. 错误语义统一：OASIS 与模拟关键链路把结构性失败映射为 `422`。

## 仍有差距（相对 MiroFish）
1. 报告可观测性不足：
   - 当前 `agent_log` / `console_log` 为轻量行日志。
   - 缺少 MiroFish 的 ReACT 级工具调用日志、章节迭代日志、完整 JSONL 流式日志。
2. 报告生成深度不足：
   - 当前为单次 JSON 报告生成。
   - 缺少“先规划大纲 -> 分章节生成 -> 每章可中断/重试/落盘”的完整流水线。
3. 图谱构建过程可见性不足：
   - 当前偏黑盒（由 cognee 管线驱动）。
   - 缺少 MiroFish 那种 episode 级等待、批次级进度和失败定位信息。
4. 模拟配置可解释性不足：
   - 当前没有单独暴露“配置生成推理链”日志。
   - 缺少类似 MiroFish 的分阶段配置面板与细粒度推理说明。

## 冗余/可清理项
1. `apps/server-py/tests/test_oasis_service.py` 仍包含 fallback 相关用例与导入，需要重写为“严格失败预期”测试。
2. `routers/simulation.py` 中 `_build_run_artifacts`（模板生成）已不再走主链路，建议下一步删除。

## 建议优先级
1. P0：重写 OASIS/Simulation 相关测试，移除 fallback 断言并补充 `422` 场景。
2. P1：报告链路升级为“规划-分章-落盘-可恢复”，补齐章节级进度与日志。
3. P2：图谱构建增加批次级进度与可观测错误上下文。
