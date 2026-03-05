# MuseGraph 多项目全结构对比报告（补完版，2026-03-05）

## 1. 对比对象
1. `MuseGraph`（当前主项目）
2. `Ai-Novel`（任务编排、幂等、自动扇出）
3. `MiroFish`（图谱流程可观测、阶段化进度）
4. `AI_NovelGenerator`（章节生成链路与知识回写）

---

## 2. 结论先行（最优方案）
采用 **Hybrid-Plus**：
1. 图谱引擎与增量策略继续以 `MuseGraph` 为主。
2. 任务编排采用 `Ai-Novel` 的“幂等键 + 章节变更扇出 + 去重”思路。
3. 检索增强采用 `AI_NovelGenerator` 的“检索词生成 -> 检索 -> 规则过滤 -> LLM过滤”思路。
4. 交互与可观测采用 `MiroFish` 的“阶段化进度 + 日志化反馈”思路。

---

## 3. 后端结构对比（关键能力）

### 3.1 任务系统
1. `Ai-Novel`：
   - `ProjectTask` 强约束幂等键（唯一约束）：
     `C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/models/project_task.py:32`
   - 章节完成后自动扇出任务总线：
     `C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/services/project_task_service.py:522`
2. `MuseGraph`（本轮前）：
   - 任务持久化完整（内存 + Redis + SQLite）：
     `apps/server-py/app/services/task_state.py:132`
   - 但缺少任务幂等键语义（仅 UUID）：
     `apps/server-py/app/services/task_state.py:391`
3. `MiroFish`：
   - 任务模型含 `progress_detail`：
     `C:/Users/QwQ/Documents/GitHub/MiroFish/backend/app/models/task.py:35`
4. `AI_NovelGenerator`：
   - 无独立统一任务中心，偏脚本/函数串行。

### 3.2 图谱构建与增量
1. `MuseGraph`：
   - 构建模式 `rebuild/incremental`，含章节哈希与删除检测：
     `apps/server-py/app/routers/cognee_graph.py:692`
   - 分段入库 + cognify + memify 超时保护：
     `apps/server-py/app/services/cognee.py:1183`
2. `MiroFish`：
   - 构建流程分阶段显式进度（分块/上传/等待处理/取结果）：
     `C:/Users/QwQ/Documents/GitHub/MiroFish/backend/app/api/graph.py:381`
3. `Ai-Novel`：
   - 图谱自动更新调度使用 `chapter_token` 幂等：
     `C:/Users/QwQ/Documents/GitHub/Ai-Novel/backend/app/services/graph_auto_update_service.py:597`

### 3.3 结构化记忆（角色卡/世界书/术语）
1. `Ai-Novel`：
   - worldbook / characters / memory update 均具调度与幂等：
     - `.../worldbook_auto_update_service.py:555`
     - `.../characters_auto_update_service.py:669`
     - `.../memory_update_service.py:450`
2. `MuseGraph`：
   - 已有角色卡/术语表/世界书数据面，但仍缺统一“编辑后自动扇出索引与图谱更新”总线。

### 3.4 RAG 检索链路
1. `AI_NovelGenerator`：
   - 章节生成前：检索词生成 + 多组向量检索 + 规则处理 + 过滤：
     `C:/Users/QwQ/Documents/GitHub/AI_NovelGenerator/novel_generator/chapter.py:393`
   - 定稿后：摘要/角色状态/向量库统一回写：
     `C:/Users/QwQ/Documents/GitHub/AI_NovelGenerator/novel_generator/finalization.py:21`
2. `MuseGraph`：
   - 已有图谱检索与 rerank，但缺少“写作前查询扩展 + 二次过滤”统一链路入口。

---

## 4. 前端结构对比（交互形态）
1. `Ai-Novel` 页面域完整（writing / rag / worldbook / glossary / task center）：
   `C:/Users/QwQ/Documents/GitHub/Ai-Novel/frontend/src/pages`
2. `MiroFish` 强流程化五步组件（Step1~Step5），进度与日志心智清晰：
   `C:/Users/QwQ/Documents/GitHub/MiroFish/frontend/src/components/Step1GraphBuild.vue`
3. `MuseGraph` 已有项目页 + 任务中心 + 图谱操作分栏，但需要继续提升阶段可解释性与一致性视觉密度。

---

## 5. 当前差距（MuseGraph 相对最优方案）
1. 缺少“统一扇出任务总线”：章节/角色卡/世界书/术语变更后，尚未自动触发 graph/vector/search 的全链路刷新。
2. 缺少“RAG 前置检索增强流水线”：当前更多依赖单段 prompt，查询扩展与过滤策略还不够显式。
3. 缺少“阶段细粒度进度模型”：当前大多是 `progress + message`，但尚未标准化 `progress_detail` 分阶段结构。
4. 已有任务持久化，但本轮前缺幂等去重，重复点击会重复起长任务。

---

## 6. 冗余/可裁剪点
1. UI 与流程存在局部重复状态容器（图谱流程和 OASIS 流程局部状态分散）。
2. 任务相关前端轮询逻辑在多个区域有重复片段，可进一步抽象成统一 composable。

---

## 7. 本轮新增落地（已完成）
1. 图谱/OASIS 任务新增幂等指纹生成与复用在途任务：
   - 指纹构建：`apps/server-py/app/routers/cognee_graph.py:130`
   - 启动前幂等复用：`apps/server-py/app/routers/cognee_graph.py:694`
2. 任务管理器新增按 `idempotency_key` 查找在途任务能力：
   `apps/server-py/app/services/task_state.py:561`
3. 新增回归测试覆盖“复用在途任务，不重复创建 runner”：
   `apps/server-py/tests/test_cognee_graph_extended.py:713`

---

## 8. 路线图（按收益排序）
1. P0：统一“内容变更 -> 任务扇出”总线（graph/vector/search/worldbook/角色卡/术语表）。
2. P0：任务状态标准化 `progress_detail`（阶段 + 子阶段 + 当前处理分片）。
3. P1：写作/续写前引入“检索词扩展 + 规则过滤 + LLM过滤”RAG增强链路。
4. P1：图谱预览层引入“业务实体层/系统结构层”双视图切换，避免 DocumentChunk 等元素干扰用户认知。
5. P2：任务中心增加“同幂等键历史任务折叠”与“重试继承链”展示。

---

## 9. 验证记录
1. 语法校验：
   - `python -m py_compile app/services/task_state.py app/routers/cognee_graph.py tests/test_cognee_graph_extended.py`
2. 回归测试（任务启动与幂等）：
   - `pytest tests/test_cognee_graph_extended.py -q -k "prepare_task_starts or report_task_starts or run_task_starts or reuses_inflight"`
   - 结果：`4 passed`

---

## 10. 全结构量化快照（代码层）

### 10.1 MuseGraph
1. 代码文件总数：`224`（server `94` + web `101`）。
2. 后端分层规模：
   - `routers=12`，`services=15`，`models=6`，`schemas=7`。
3. API 与测试规模：
   - 路由装饰器计数 `135`。
   - 测试文件 `31`，`def test_` 计数 `580`。
4. 迁移与部署：
   - Alembic 迁移 `8`。
   - Docker 相关文件 `5`。

### 10.2 Ai-Novel
1. 代码文件总数：`595`（backend `439` + frontend `156`）。
2. 后端分层规模：
   - `routes=31`，`services=50`，`models=30`，`schemas=27`。
3. API 与测试规模：
   - 路由装饰器计数 `174`。
   - 测试文件 `102`，测试用例 `305`。
4. 迁移与部署：
   - Alembic 迁移 `43`。
   - Docker/compose 相关 `5`。

### 10.3 MiroFish
1. 代码文件总数：`84`（backend `36` + frontend `29`）。
2. 后端分层规模：
   - `api=4`，`services=13`，`models=3`，`utils=5`。
3. API 与测试规模：
   - Flask 路由计数 `60`。
   - 测试文件 `1`（明显偏少）。
4. 部署：
   - Docker 相关 `3`（简化部署）。

### 10.4 AI_NovelGenerator
1. 代码文件总数：`39`（`novel_generator=8`，`ui=15`）。
2. 架构形态：
   - 无 Web API 分层（偏本地 GUI + 脚本工作流）。
3. 测试与部署：
   - 未发现标准测试集。
   - 未提供容器化部署基线。

---

## 11. 结构完整性结论（按层级）
1. `产品层`：Ai-Novel 最完整（页面域和业务域覆盖最广）。
2. `流程层`：MiroFish 的阶段化流程表达最强（用户认知成本最低）。
3. `任务编排层`：Ai-Novel 最成熟（幂等、扇出、去重、队列语义完整）。
4. `图谱引擎层`：MuseGraph 具备最强可演进基础（Cognee + 增量计划 + 新鲜度）。
5. `写作检索层`：AI_NovelGenerator 的“检索词生成->过滤->生成->回写”闭环最清晰。
6. `工程质量层`：Ai-Novel 测试与迁移体系最厚；MuseGraph 次之；MiroFish 与 AI_NovelGenerator 偏功能验证导向。

---

## 12. 对 MuseGraph 的最终“最优拼装方案”
1. 以 MuseGraph 作为底盘：
   - 保留 `FastAPI + Cognee + 增量图谱 + 商业化计费` 主链路。
2. 融合 Ai-Novel 的任务治理：
   - 建立“内容变更统一扇出总线”。
   - 为所有可重入长任务定义 `idempotency_key` 规范和重试链。
3. 融合 MiroFish 的交互与可观测：
   - 将 `progress + message` 升级为 `progress_detail(stage, step, processed, total)`。
   - 前端统一显示阶段条、失败点、恢复动作。
4. 融合 AI_NovelGenerator 的写作前后闭环：
   - 写作前：查询扩展 + 检索 + 规则过滤 + LLM过滤。
   - 写作后：角色/术语/世界书 + 图谱 + 向量索引统一回写任务。

---

## 13. 下一轮执行项（已确定）
1. 新增统一任务扇出入口（章节、角色卡、术语表、世界书四类变更源）。
2. 在任务模型增加 `progress_detail` 并改造图谱/OASIS任务上报。
3. 在写作与续写前接入“检索词扩展 + 过滤”链路（可开关）。

---

## 14. API 结构全量比对（路由拓扑）

### 14.1 MuseGraph（FastAPI）
1. 路由总量高集中在 5 个域文件：
   - `admin.py=31`
   - `projects.py=27`
   - `simulation.py=23`
   - `cognee_graph.py=22`
   - `report.py=16`
2. 路由域覆盖：
   - 账户与登录、项目与章节、角色卡/术语/世界书、图谱与 OASIS、报告与模拟、支付与计费、后台模型与任务管理。
3. 结构特征：
   - “创作主链路”和“图谱主链路”已具备完整 API 面，后台与计费也在同服务内闭环。

### 14.2 Ai-Novel（FastAPI）
1. 路由文件多、域拆分细，前 8 个高频路由文件：
   - `prompts.py=17`
   - `memory.py=15`
   - `auth.py=13`
   - `chapters.py=12`
   - `vector.py=12`
   - `projects.py=11`
   - `tables.py=11`
   - `worldbook.py=11`
2. 结构特征：
   - API 域细分更彻底，便于任务总线挂接与中台化演进。

### 14.3 MiroFish（Flask）
1. 路由集中三文件：
   - `simulation.py=31`
   - `report.py=18`
   - `graph.py=10`
2. 结构特征：
   - 路由规模适中，流程导向明显，但域拆分粒度低于 Ai-Novel。

### 14.4 AI_NovelGenerator
1. 无 Web API 分层（本地 GUI + 脚本驱动）。
2. 可迁移的是“章节生成/检索过滤/回写”函数链，而不是路由结构。

---

## 15. 数据模型结构全量比对

### 15.1 MuseGraph
1. 模型总量适中（计费、项目、用户、运行时、配置五类）：
   - 计费：`Usage`、`Deposit`、`Order`
   - 项目：`TextProject`、`ProjectChapter`、`ProjectCharacter`、`ProjectGlossaryTerm`、`ProjectWorldbookEntry`、`TextOperation`
   - 用户与会话：`User`、`Session`
   - 运行时：`SimulationRuntime`、`ReportRuntime`
   - 配置：`AIProviderConfig`、`PricingRule`、`PaymentConfig`、`PromptTemplate`
2. 结构特征：
   - 已覆盖商业化 + 创作基础 + 运行态，但“任务实体化”仍在任务状态管理层而非 ORM 任务表层。

### 15.2 Ai-Novel
1. 模型谱系最完整（30+），核心域包含：
   - 项目/章节/大纲/写作风格/提示词
   - 结构化记忆（entity/relation/event/foreshadow/evidence/change set）
   - 任务体系（`ProjectTask`、`MemoryTask`、批量任务）
   - RAG/检索（source document/chunk、search index、vector 相关）
2. 结构特征：
   - 任务模型、记忆模型、RAG 模型均实体化，天然适配自动扇出和幂等治理。

### 15.3 MiroFish
1. 模型精简：
   - 项目模型：`Project` + `ProjectManager`
   - 任务模型：`Task` + `TaskManager`
2. 结构特征：
   - 模型少、流程清晰，适合演示和流程可视化，不是重业务域承载型。

### 15.4 AI_NovelGenerator
1. 无后端数据库模型分层，主要是文件与向量库函数。
2. 结构特征：
   - 适合作为“链路算法参考”，不适合作为“系统结构模板”。

---

## 16. 任务系统与自动扇出对比（实现层）

### 16.1 MuseGraph 当前实现
1. 已有任务中心能力：
   - 任务持久化、列表、取消、状态轮询、幂等键复用在途任务。
2. 主要不足：
   - 内容变更后的“统一扇出总线”尚未覆盖全域（章节/角色卡/术语/世界书 -> graph/vector/search）。

### 16.2 Ai-Novel 参考实现
1. 自动扇出关键链路：
   - 章节状态从非 done 变为 done 后，统一调度 `schedule_chapter_done_tasks(...)`。
2. 下游任务覆盖：
   - vector rebuild、search rebuild、worldbook auto update、characters auto update、plot auto update、table ai update、graph auto update、fractal rebuild。
3. 幂等与去重：
   - 任务层与调度层都有 dedupe 逻辑，且任务模型层有幂等键语义。

### 16.3 MiroFish 参考实现
1. 图谱任务分阶段进度表达明确：
   - 构建阶段存在显式分段回调（例如 15%-55%、55%-90%）。
2. 可迁移价值：
   - 更强的进度可解释性与故障定位提示。

### 16.4 AI_NovelGenerator 参考实现
1. 章节链路函数化闭环：
   - 查询扩展/规则过滤/检索上下文拼接 -> 章节生成 -> 定稿回写（摘要/向量）。
2. 可迁移价值：
   - 可作为 MuseGraph 写作前后流水线增强模板。

---

## 17. 前端信息架构全量比对

### 17.1 MuseGraph（Vue）
1. 当前主页面域：
   - 登录/注册、Dashboard、Projects、Project、Graph、Simulation、Report、Interaction、Admin、Pricing、Recharge。
2. 当前组件域：
   - `project/*` 已含编辑器、图谱构建、AI 操作、任务中心、知识库分区。
   - `admin/*` 已做后台模块化拆分。
3. 主要差距：
   - 任务列表与任务阶段说明仍可进一步标准化。
   - RAG 前置链路在交互层仍需更显式步骤化。

### 17.2 Ai-Novel（React）
1. 页面域最完整：
   - writing、rag、worldbook、characters、glossary、search、task center、prompt studio、fractal、preview、reader、analysis 等。
2. 架构特征：
   - “页面域即业务域”，便于扩展复杂中后台写作平台。

### 17.3 MiroFish（Vue）
1. 路由少但流程清晰：
   - `/process/:projectId` 中通过 Step1~Step5 展开全过程。
2. 架构特征：
   - 更偏“流程向导式产品”，认知负担低。

### 17.4 AI_NovelGenerator（GUI）
1. tab 型本地 UI 结构：
   - config/character/summary/chapters 等。
2. 架构特征：
   - 适合单机创作工具，不适合作为 Web 产品 IA 模板。

---

## 18. 完整差异矩阵（MuseGraph 视角，补完）
1. 缺失（P0）：
   - 统一内容变更扇出总线仍未全域接管。
   - `progress_detail` 结构尚未成为全任务强约束。
2. 不完善（P1）：
   - 写作前“查询扩展 + 规则过滤 + LLM过滤”入口仍未系统化。
   - 任务中心缺“同幂等键任务折叠 + 重试继承链”可视化。
3. 冗余（P1）：
   - 局部轮询逻辑、局部状态管理仍有重复片段。
   - 旧页面样式与新米色/深灰主题存在局部不一致。
4. 可直接复用（高收益）：
   - 从 Ai-Novel 复用调度语义与扇出设计。
   - 从 MiroFish 复用阶段化进度展示方式。
   - 从 AI_NovelGenerator 复用检索过滤闭环函数思路。

---

## 19. 下一阶段执行顺序（本轮比对后更新）
1. P0：落统一扇出总线（章节/角色/术语/世界书四类入口）并接入图谱与索引刷新。
2. P0：统一任务状态协议，强制 `progress_detail(stage, step, processed, total)`。
3. P1：接入写作前检索增强链（查询扩展 -> 规则过滤 -> LLM过滤）。
4. P1：任务中心增加幂等折叠与重试链显示。
5. P2：清理重复状态/轮询逻辑，继续收敛全站主题一致性。
