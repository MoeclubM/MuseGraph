# MuseGraph 当前架构

本文只描述当前生产路径，不记录已删除的历史实现或兼容路径。

## 1. 总体结构

```text
Vue Web
  │ REST + SSE
  ▼
FastAPI routers
  │
  ├─ project / files / versions / facts
  ├─ agent / skills
  ├─ memory
  ├─ billing / payment / admin
  │
  ▼
Application services
  ├─ Pi Agent tool loop
  ├─ project workspace + embedded Git
  ├─ Cognee memory adapter
  ├─ LiteLLM model gateway
  └─ task state
  │
  ├─ PostgreSQL: users, projects, operations, facts, sessions
  ├─ Redis: sessions, coordination and task cache
  └─ .musegraph: project files, Cognee data and task-state SQLite
```

生产 Agent 只有一条入口：`MuseGraphPiAgent.run_flow()` → `run_tool_loop_flow()`。旧 `AgentOrchestrator` 和服务端长文管线已经移除。

## 2. 后端分层

### API 层

`app/main.py` 组装所有 FastAPI Router。Router 负责认证、权限、请求模型、事务边界和 HTTP/SSE 返回，不承载模型调用或记忆实现。

主要 Router：

- `routers/agent.py`：会话、消息、SSE、Agent 后台任务
- `routers/projects.py`：项目与文档单元
- `routers/project_files.py`：项目工作区文件
- `routers/project_versions.py`：项目记录点与恢复
- `routers/facts.py`：事实和实体
- `routers/memory.py`：Cognee 构建、搜索、图谱和清理
- `routers/skills.py`：项目级 Skills
- `routers/admin.py`：管理后台

### Agent 层

- `services/pi_agent_service.py`：Agent 上下文、工具执行、子代理会话、循环驱动
- `services/pi_tool_loop.py`：工具 JSON Schema、系统提示词、动作解析
- `services/agent/subagent_profiles.py`：角色工具白名单、写入权限、输出 Schema
- `services/agent/skills.py`：项目可见 Skill 的查询和选择
- `services/agent/skill_catalog.py`：内置 Skill 定义
- `services/creative_task_planner.py`：意图与 `pipeline_kind` 推断，只影响提示规则

子代理角色：

| 角色 | 作用 | 可写项目状态 |
|---|---|---|
| planner | 规划执行与结构 | 否 |
| composer | 选择上下文和规则 | 否 |
| writer | 写文档单元 | 是 |
| auditor | 审计并报告问题 | 否 |
| reviser | 按问题修订文档 | 是 |
| evaluator | 评价候选方案 | 否 |
| updater | 提交事实与状态变更 | 是 |
| memory_builder | 构建结构化记忆 | 是 |
| graph_extractor | 提取实体关系 | 是 |

工具调用同时受角色白名单和 `can_write_back` 校验。不存在旧角色别名。

### 记忆层

`services/memory_backend.py` 是应用层稳定接口，当前唯一实现是 `services/cognee_backend.py`。

```text
项目文档 / 事实 / Agent 结构化记忆
  └─ memory_backend
       └─ Cognee add + cognify
            ├─ 语义检索
            └─ 实体关系图谱
```

Cognee 配置由 `COGNEE_DATA_DIR`、`COGNEE_INGEST_TIMEOUT_SECONDS` 和 `COGNEE_LLM_MAX_TOKENS` 控制。聊天与嵌入模型从项目和 Provider 配置解析，不存在内置模型回退。

### 项目工作区

`services/project_files.py` 管理真实文件目录，`services/project_git.py` 为每个项目维护嵌入式 Git 仓库，`services/project_workspace.py` 将数据库状态投影到工作区。所有文件路径必须留在项目 workspace 根目录内。

控制文档 `intent.md`、`focus.md`、`rules.md`、`bible.md` 在项目创建时由当前 text-type pack 初始化。

### 模型与计费

`services/ai.py` 统一处理：

- Provider/模型解析
- LiteLLM 调用与流式输出
- token 与成本记录
- 项目级组件模型路由

TypeScript `packages/ai-adapters` 是共享 SDK adapter，不参与 Python 服务端生产调用。

## 3. Agent 执行

```text
POST /agent/chat
  ├─ 创建 AgentSession / AgentMessage / TextOperation
  ├─ 后台启动 run_pi_agent_flow_background
  ├─ 预取文档、Cognee RAG 与关系图
  └─ 循环
       ├─ 调用 LLM 取得 tool_call 或 finish
       ├─ 校验工具、角色与写权限
       ├─ 执行真实工具并写 AgentStep
       ├─ 必要时启动独立子代理会话
       └─ finish 后持久化 workspace 和 operation
```

`pipeline_kind` 不启动隐藏的服务端管线，只给主 Agent 增加明确规则：

- `long_form_write`：按章写入、构建记忆、按需 auditor/reviser
- `fact_extraction`：updater 提交 delta，由主 Agent 批量应用
- `review_only`：auditor 只读审计
- `simple`：按任务自主选工具

## 4. 前端

Vue 应用使用 Pinia 管理认证、项目、Agent 会话和布局状态。Agent 工作区为三栏结构：

- `AgentSessionSidebar`：会话
- `AgentCenterPanel`：对话、步骤、任务
- `AgentBrowserPanel`：编辑器、知识、实体、Cognee 图谱、版本

Agent SSE 事件写入 store，UI 从持久化的 Session/Step 数据恢复，不依赖仅存在于页面内存的执行状态。

## 5. 数据与部署

Compose 服务：

| 服务 | 作用 | 持久化 |
|---|---|---|
| postgres | 业务数据库 | `postgres_data` |
| redis | 会话与任务协调 | `redis_data` |
| server | FastAPI + Cognee | `task_state_data` |
| web | Nginx 静态站点 | 无 |

Python 镜像用 `uv.lock` 和 `uv sync --frozen` 构建；Node 镜像用根目录 `pnpm-lock.yaml` 和 `pnpm install --frozen-lockfile` 构建。仓库不维护子目录锁文件。

## 6. 设计约束

- 不保留旧后端、旧角色或旧配置别名
- 不吞掉内部错误，不返回 mock success
- 只在 HTTP、文件路径、外部 Provider 等真实边界做校验
- 简单逻辑内联；按 Agent、记忆、工作区、计费等功能拆分
- 数据迁移使用 Alembic 或独立脚本，不在主路径自动迁移
- 测试失败必须暴露真实原因

## 7. 当前热点

`pi_agent_service.py`、`routers/admin.py` 和 `services/ai.py` 仍然较大。后续拆分应沿功能边界进行，并保持现有 Router/Service 接口；不要为了缩短文件创建无业务含义的包装层。
