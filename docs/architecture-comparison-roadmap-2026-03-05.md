# MuseGraph 全结构对比与最优方案路线图（2026-03-05）

## 1. 对比范围
1. 当前项目：`MuseGraph`（本体、RAG图谱、可视化、任务系统、计费、自动更新）
2. 参考项目：`Ai-Novel`（任务编排/幂等/结构化记忆）
3. 参考项目：`AI_NovelGenerator`（检索过滤链路/定稿后知识回写）
4. 参考项目：`MiroFish`（图谱构建阶段化进度与前端可观测）

---

## 2. 结构化对比结论

### 2.1 MuseGraph 已具备的核心能力
1. 增量/重建图谱计划器与章节哈希判定：`apps/server-py/app/routers/cognee_graph.py:562`
2. 图谱构建分段入库（chunk+overlap）与 cognify/memify：`apps/server-py/app/services/cognee.py:1183`
3. 图谱预览结构节点过滤与裁剪：`apps/server-py/app/services/cognee.py:660`
4. 任务持久化（内存+Redis+SQLite）：`apps/server-py/app/services/task_state.py:391`
5. LLM 统一计费上下文：`apps/server-py/app/services/ai.py:65`

### 2.2 Ai-Novel 可迁移优势
1. 章节完成后自动扇出多任务（worldbook/characters/graph/vector/search/fractal）：`C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/services/project_task_service.py:522`
2. ProjectTask 幂等键 + 唯一约束：`C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/models/project_task.py:32`
3. graph auto update 采用 `chapter_token` 防抖与去重：`C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/services/graph_auto_update_service.py:619`
4. memory update 的 propose/apply 双阶段幂等：`C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/services/memory_update_service.py:450`

### 2.3 AI_NovelGenerator 可迁移优势
1. 章节生成前“检索词生成 -> 检索 -> 规则过滤 -> LLM过滤”：`C:/Users/QwQ/Documents/GitHub/AI_NovelGenerator/novel_generator/chapter.py:222`
2. 定稿后统一回写摘要/角色状态/向量库：`C:/Users/QwQ/Documents/GitHub/AI_NovelGenerator/novel_generator/finalization.py:21`
3. 向量增量更新：`C:/Users/QwQ/Documents/GitHub/AI_NovelGenerator/novel_generator/vectorstore_utils.py:182`

### 2.4 MiroFish 可迁移优势
1. 图谱构建阶段化进度（分块、建图、等待处理、取结果）：`C:/Users/QwQ/Documents/GitHub/MiroFish/backend/app/api/graph.py:378`
2. 任务模型支持 `progress_detail`：`C:/Users/QwQ/Documents/GitHub/MiroFish/backend/app/models/task.py:35`
3. 前端按阶段显示与日志化反馈：`C:/Users/QwQ/Documents/GitHub/MiroFish/frontend/src/components/Step2EnvSetup.vue:863`

---

## 3. 最优方案选择（最终选型）

采用 **Hybrid 方案**：
1. **核心引擎保留 MuseGraph**（Cognee 图谱/RAG 与现有计费体系不动）
2. **任务编排引入 Ai-Novel 思路**（章节变更自动扇出、幂等键、防重）
3. **检索前后处理引入 AI_NovelGenerator 思路**（查询扩展+二次过滤）
4. **可观测性引入 MiroFish 思路**（阶段进度/原因可视化）

不采用的部分：
1. 不迁移 Ai-Novel 的 dev-inline 队列回退（会弱化生产语义）
2. 不迁移 MiroFish 的重脚本式全量流程（与当前服务化接口冲突）

---

## 4. 问题分级（MuseGraph 当前）

### P0 问题（立即治理）
1. 章节手动保存后，用户感知不到图谱是否已同步，易误判“仅首次构建”。
2. 图谱任务完成后，前端未展示 `changed/added/modified/removed` 结果，解释性不足。
3. 图谱可视化接口异常与“真实空图”可观测性仍需增强。

### P1 问题（短期）
1. 章节变更后的自动扇出仍不完整（graph/vector/search/worldbook/术语表/角色链路）
2. 结构化记忆（worldbook/角色卡/术语表）与图谱增量同步仍偏人工触发

### P2 问题（中期）
1. 任务阶段明细不足（目前主要是百分比+message）
2. 大规模文本与高并发场景下的进度真实性和失败恢复策略仍可增强

---

## 5. 路线图（持续推进）

### 阶段 A（已开始，P0）
1. 图谱构建结果解释化（前端展示 mode + changed/added/modified/removed + reason）
2. 保存章节后触发增量图谱刷新（避免“保存后图谱不更新”）
3. 建立对比报告与执行基线（本文件）

### 阶段 B（P0，下一步）
1. 图谱状态条：`已同步/已过期/同步中`，并显示“上次同步范围与时间”（已完成前端判定版，后端状态字段待补）
2. 可视化接口错误显式化（区分空图与后端失败）
3. RAG 依赖操作前的“图谱过期提醒 + 一键增量更新”

### 阶段 C（P1）
1. 章节变更自动扇出任务（graph/vector/search）
2. 角色卡/术语表/世界书变更触发 RAG 索引与图谱更新
3. 任务幂等键规范化（章节token + 任务类型 + 版本）

### 阶段 D（P2）
1. 任务 `progress_detail` 分阶段模型（解析、分块、抽取、融合、索引）
2. 图谱视图支持“语义节点/结构节点”切换与过滤
3. 增强增量图谱策略（编辑/删除章节下的更细粒度更新）

---

## 6. 本轮已落地（执行证明）

1. 新增图谱构建摘要模型与提取逻辑：
   - `apps/web-vue/src/views/ProjectView.vue:160`
   - `apps/web-vue/src/views/ProjectView.vue:964`
2. 任务结果写回摘要并拼接到构建消息：
   - `apps/web-vue/src/views/ProjectView.vue:1180`
3. 右侧图谱区新增“Last graph build”摘要展示：
   - `apps/web-vue/src/views/ProjectView.vue:3545`
4. `handleSave` 改为保存后触发增量图谱刷新：
   - `apps/web-vue/src/views/ProjectView.vue:1921`
   - `apps/web-vue/src/views/ProjectView.vue:1931`
5. 新增图谱新鲜度状态条（`Graph syncing / stale / up to date`）：
   - `apps/web-vue/src/views/ProjectView.vue:360`
   - `apps/web-vue/src/views/ProjectView.vue:2430`
   - `apps/web-vue/src/views/ProjectView.vue:3569`
6. 前端构建验证通过：`pnpm --filter @musegraph/web build`
7. `GET /graphs` 返回权威图谱新鲜度状态（fresh/stale/syncing/no_ontology/empty）与差异计数：
   - `apps/server-py/app/routers/cognee_graph.py:302`
   - `apps/server-py/app/routers/cognee_graph.py:1900`
8. 图谱可视化异常显式化（后端不再吞错为空图，路由区分 502/500）：
   - `apps/server-py/app/services/cognee.py:1529`
   - `apps/server-py/app/routers/cognee_graph.py:1972`
9. 前端接入 `getGraphStatus` 并用后端权威状态覆盖启发式 freshness 判定：
   - `apps/web-vue/src/api/graph.ts:159`
   - `apps/web-vue/src/types/index.ts:266`
   - `apps/web-vue/src/views/ProjectView.vue:157`
10. GraphView 增加“加载失败”状态（与“空图”分离）：
   - `apps/web-vue/src/views/GraphView.vue:15`
11. 图谱/OASIS 任务增加幂等键与在途任务复用（防止重复点击重复起任务）：
   - `apps/server-py/app/routers/cognee_graph.py:130`
   - `apps/server-py/app/routers/cognee_graph.py:694`
12. 任务管理器增加按 `idempotency_key` 检索在途任务能力：
   - `apps/server-py/app/services/task_state.py:561`
13. 新增幂等任务复用回归测试：
   - `apps/server-py/tests/test_cognee_graph_extended.py:713`
14. 本轮后端验证：
   - `python -m py_compile app/services/task_state.py app/routers/cognee_graph.py tests/test_cognee_graph_extended.py`
   - `pytest tests/test_cognee_graph_extended.py -q -k "prepare_task_starts or report_task_starts or run_task_starts or reuses_inflight"`（`4 passed`）

---

## 7. 下一批执行清单（已排定）
1. 章节与结构化记忆变更后的统一任务扇出（graph/vector/search）
2. 任务幂等键规范化扩展到“章节token + 任务类型 + 版本 + 数据范围”
3. 任务 `progress_detail` 分阶段模型（解析、分块、抽取、融合、索引）

> 执行策略：按阶段 B -> C 顺序推进，每完成一个子项更新本报告“已落地”区。

---

## 8. 补完报告
已输出完整版结构对比与选型报告：`docs/full-structure-comparison-2026-03-05.md`

补充说明：完整版报告已追加“全结构量化快照（文件规模/API规模/测试规模/迁移规模）”与“最终拼装方案”，可直接作为后续迭代基线。

---

## 9. 本轮继续补完（完整结构层）
1. 已在补完报告新增“API 路由拓扑全量比对”（四项目统一维度）。
2. 已新增“数据模型谱系比对”（模型域、任务实体化程度、可迁移边界）。
3. 已新增“任务系统与自动扇出实现层比对”（幂等/去重/阶段进度/回写闭环）。
4. 已新增“前端 IA 全量比对”（页面域、流程域、任务中心形态）。
5. 已输出“完整差异矩阵 + 更新后的执行顺序”，用于下一轮直接落地开发。
