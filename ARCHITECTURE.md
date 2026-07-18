# MuseGraph 当前架构

本文只描述当前生产路径。项目仍处于开发期，不保留旧接口、旧表、旧运行时或兼容逻辑。

## 1. 权威数据边界

```text
Git project repository
  └─ text, control documents, paths, immutable commits

Per-project Cognee process
  └─ fact, entity, relation, event, constraint, source
     └─ one immutable Dataset per published Agent revision

PostgreSQL
  └─ users, sessions, permissions, Agent runs/events, reviews,
     revision pointers, providers, billing, audit logs, derived indexes

Redis
  └─ SSE notifications and explicit rate-limit counters only
```

Redis、浏览器状态和工作区缓存都不是权威任务存储。Git 文本的语义索引属于可重建派生数据，不与结构化知识 Dataset 混用。

## 2. 部署拓扑

```text
Vue Web
  │ Cookie session + CSRF, REST, SSE Last-Event-ID
  ▼
FastAPI API ─────────────── PostgreSQL
  │                             ▲
  │ internal Bearer             │ database queue + lease
  ▼                             │
Memory Supervisor          Agent Worker
  │
  ├─ project A Cognee process + root + config
  └─ project B Cognee process + root + config

Redis: event wakeups and rate limits
```

API 不访问 Docker Socket，也不在进程内启动 Agent 后台任务。Worker 以数据库租约领取 `queued` Run，持续写心跳；租约过期的 `running` Run 可由新 Worker 重新领取。

## 3. Agent 创作闭环

Run 模式为 `write | analyze | suggest`，状态为：

```text
queued → running → awaiting_review → accepting → completed
                 ├─ failed
                 ├─ cancelled
                 └─ awaiting_review → rejected | conflicted
```

1. API 固定 `base_revision_id`，保存解析后的 Skill 快照与工具集合。
2. Worker 从固定 Git Commit 建立隔离 Run 工作区。
3. Planner 生成严格 `CreationPlan`。
4. Composer 构造带 Git、知识 ID 和来源的 `CreativeContextBundle`。
5. Cognee Recall 返回的知识先由项目 Reranker 排序；上下文快照保存模型、知识 ID 和分数。
6. 每个角色只能调用统一 Tool Registry 中对该角色和 Skill 同时开放的工具。
7. Writer/Reviser 只修改 Run 工作区；知识角色只写候选 `KnowledgeOperation`。
8. Auditor 只读检查，确定性校验验证文件声明、知识引用、计划知识和 required 约束。
9. 成功结果保存为 `ChangeSet` 与 `AgentFinish`，进入 `awaiting_review`。
10. Accept 在项目写锁内构建新 Cognee Dataset、发布 Git Commit 并更新活动版本指针；任一步失败会撤销候选外部写入。
11. Reject 删除隔离工作区；基础版本变化则标记 `conflicted`，不自动合并。

SSE 事件持久化在 `agent_events`，客户端通过 `Last-Event-ID` 从数据库续传。不存在 `partial` 成功、进程内 `BackgroundTasks`、SQLite TaskManager 或启发式自动写文件。

## 4. Tool Registry

`app/services/agent/tool_registry.py` 是唯一工具注册表。每个工具同时定义：

- 名称和说明
- 严格 Pydantic 输入模型
- 处理器
- 可用角色
- `read | file | knowledge` 变更类型

当前工具：

- `list_files`
- `read_file`
- `write_file`
- `delete_file`
- `knowledge_search`
- `knowledge_get`
- `knowledge_upsert`
- `knowledge_delete`

工具 Schema、处理器、角色写门和 Skill 工具集合由合约测试验证。不存在 `web_search`、`fetch_url` 或重复文档写入工具。

## 5. Skill 与 Text Pack

内置 Skill 只在 `skill_catalog.py` 中定义；项目 Skill 只存 `project_skills`，联合唯一键为 `(project_id, slug)`。自定义 Skill 不能覆盖内置 slug，运行时仍受角色工具白名单限制。

唯一解析入口：

```text
resolve_project_skill(project_id, pack_slug, operation, role, requested_slug)
```

选择顺序：

1. 用户显式选择
2. 当前 Text Pack 对 operation/role 的默认 Skill
3. Pack 明确配置的 `general`

每次 Run 保存完整 `ResolvedSkillSnapshot`，后续 Skill 编辑不会改变运行中的任务。六个 Pack 在启动和 CI 中严格校验：

- generic
- novel
- article
- paper
- screenplay
- product_doc

Pack 同时定义默认 Skill、审计维度、允许知识类型、文档单元命名和控制文档模板；错误直接导致启动失败。

## 6. 结构化知识

公开联合类型 `KnowledgeRecord`：

- `fact`
- `entity`
- `relation`
- `event`
- `constraint`
- `source`

所有记录都有稳定 ID、标题、内容、属性、至少一个 `SourceRef` 和修订信息。关系在应用候选变更时验证两端实体存在。

Memory Supervisor 使用 Cognee 1.4 正式接口：

- `remember` 创建不可变版本 Dataset
- `recall` 生成语义上下文
- `forget` 撤销未发布候选 Dataset
- Dataset API 读取原始 KnowledgeRecord

项目分别配置 `memory_llm`、`memory_embedding`、`memory_embedding_dimensions` 和
`memory_reranker`。Embedding 与 Reranker 使用 OpenAI 兼容端点；Cognee LLM 可使用
OpenAI 兼容端点，也可通过 LiteLLM `custom` 适配器使用 Anthropic 兼容端点。Provider
优先级决定同名模型的实际路由，运行中不进行静默 fallback。

`CreativeContextBundle` 携带知识 ID 和来源，Recall 证据只保存稳定 ID，Reranker 证据保存
模型、稳定 ID 和相关性分数。`AgentFinish.used_knowledge_ids` 必须能被确定性校验证明来自
当前上下文。PostgreSQL 不保存重复 facts JSON、Graph 镜像或 `structured_memory` 权威副本。

## 7. Git 与版本

每项目维护一个工作仓库和内部 bare remote。直接编辑器写入会立即产生 Git Commit 和新的 `ProjectRevision`；知识 Dataset 未变化时可复用同一不可变 Dataset。

Agent Accept 同时产生：

- 新 Git Commit
- 新 Cognee Dataset
- 新 `ProjectRevision`
- 新活动版本指针

版本恢复不改写历史：它先创建可审核 Run，用户 Accept 后创建一个新的发布版本。

## 8. 安全

- Cookie-only 会话；数据库只存令牌和 CSRF Token 哈希
- Argon2id 密码哈希
- 密码变更、封禁和删除撤销会话
- owner/editor/viewer 项目权限覆盖文件、知识、Skill、版本和 Agent API
- Provider、支付和邮件密钥使用 AES-256-GCM 环境主密钥加密
- Provider 地址做 DNS/IP 校验，默认拒绝回环、云元数据和内网 SSRF
- 50 MiB 流式上传，校验扩展名、MIME、魔数、压缩路径、压缩比和展开大小
- DOMPurify 清洗 Markdown
- CSP、HSTS（生产）、`nosniff`、Referrer Policy、禁止嵌入
- 注册、登录、密码变更、上传和 Agent 启动使用 Redis 限流
- 管理后台提供运行健康、Worker 租约和安全审计日志
- Cognee 的会话缓存和文件缓存后端被显式禁用；`diskcache` 仅因 Cognee 1.4 的顶层导入保留，不创建或读取可被替换的 Pickle 缓存目录。依赖审计只豁免无修复版本的 `PYSEC-2026-2447`，其余漏洞仍阻塞 CI。

测试环境通过显式 `REGISTRATION_MODE=open` 开放注册；生产启动时拒绝开放注册和不安全 Cookie。

## 9. 数据库与验证

数据库只有一个开发期基线迁移：`001_platform_baseline`。需要迁移旧数据时使用仓库外脚本或手动操作，不在生产路径加入兼容。

验证层级：

1. 合约测试：Schema、Tool Registry、角色、Skill、Pack、知识引用和安全边界。
2. Compose 集成：真实 Web、API、Worker、PostgreSQL、Redis、Git 和多个 Cognee 项目进程。
3. Playwright：只访问真实 `http://127.0.0.1:3010`。
4. Protected Provider：真实模型完成知识检索、多文件创作、审核和双版本发布。
5. CI：锁文件安装、构建、依赖审计、历史密钥扫描和镜像扫描。
