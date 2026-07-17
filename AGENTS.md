# MuseGraph 开发指南

## 开发约束

1. 简单逻辑直接内联，非必要不拆分函数或包装层。
2. 写新代码前先搜索并复用现有接口。
3. 信任内部数据，只在 HTTP、文件、Provider 等真实边界校验。
4. 模块按功能拆分，避免单文件持续膨胀。
5. 命令行修改非英文文件前确认 UTF-8 编码。

项目仍处于开发期，不考虑向后兼容。迁移后直接删除旧路径、旧配置和旧角色，不在主代码中加入兼容、自动迁移、静默降级或 mock success。

内部失败必须通过异常、日志或失败测试显式暴露。若安全或隐私要求必须增加边界规则，需要明确记录并由用户确认。

## 技术栈

- Vue 3 + Vite 8 + Tailwind CSS 4
- Python 3.12 + FastAPI
- Pi Agent + LiteLLM
- Cognee 项目记忆与关系图谱
- PostgreSQL + Redis
- uv + pnpm

## 当前生产架构

- `app/services/pi_agent_service.py`：唯一 Agent 生产运行时
- `app/services/pi_tool_loop.py`：工具 Schema、提示词、动作解析
- `app/services/agent/subagent_profiles.py`：子代理权限和输出契约
- `app/services/agent/skills.py`：项目级 Skills
- `app/services/memory_backend.py`：记忆接口
- `app/services/cognee_backend.py`：唯一记忆实现
- `app/services/project_files.py`：项目文件
- `app/services/project_git.py`：项目内嵌 Git
- `app/services/project_workspace.py`：数据库到工作区投影

不存在 `AgentOrchestrator`、Hy-Memory、`reviewer` 别名或 `run_long_form_pipeline`。不要重新引入。

## 子代理角色

| Role | 写入权限 | 用途 |
|---|---|---|
| planner | 否 | 规划 |
| composer | 否 | 选择上下文 |
| writer | 是 | 写文档 |
| auditor | 否 | 审计 |
| reviser | 是 | 修订 |
| evaluator | 否 | 评价 |
| updater | 是 | 事实与状态变更 |
| memory_builder | 是 | 结构化记忆 |
| graph_extractor | 是 | 实体关系 |

运行时同时执行工具白名单、写入门和 finish output schema 校验。

## Text-type packs

`app/services/agent/packs/*.yaml` 提供默认 Skill、auditor 维度、文档单元命名和控制文档模板。内置：

- generic
- novel
- article
- paper
- screenplay
- product_doc

Pack 文件错误应直接失败，不自动回退到其他 Pack。

## Docker

所有构建和测试在 WSL Debian 或容器中执行。

构建前强制执行：

```bash
cd /mnt/c/Users/QwQ/Documents/GitHub/MuseGraph/docker
docker compose down --remove-orphans
docker system prune -a -f
docker system df
docker compose build
docker compose up -d
```

不要使用 `docker compose down -v`，除非用户明确要求清空 PostgreSQL、Redis 和任务数据。

端口：

| 服务 | Host | Container |
|---|---:|---:|
| PostgreSQL | 5432 | 5432 |
| Redis | 6379 | 6379 |
| API | 4080 | 4000 |
| Web | 3010 | 3000 |

## 依赖

Python：

```bash
cd apps/server-py
uv sync --frozen
```

Node：

```bash
pnpm install --frozen-lockfile
```

Docker 后端必须复制 `uv.lock` 并使用 `uv sync --frozen`。前端只使用根目录 `pnpm-lock.yaml`。

## 数据库

```bash
cd apps/server-py
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
uv run python seed.py
```

开发数据库默认值：

```text
postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph
```

## 环境变量

```env
DATABASE_URL=postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph
REDIS_URL=redis://localhost:6379
FILE_STORAGE_ROOT=.musegraph/storage
TASK_STATE_SQLITE_PATH=.musegraph/task_state.sqlite3
COGNEE_DATA_DIR=.musegraph/cognee
COGNEE_INGEST_TIMEOUT_SECONDS=300
COGNEE_LLM_MAX_TOKENS=8192
APP_URL=http://localhost:3010
```

Provider API Key 和模型列表通过 Admin API 配置，不提交到仓库。

## 测试

- 所有测试命令在 WSL Debian 或 Docker 中运行。
- PostgreSQL、Redis、后端、前端或跨服务测试必须启动真实 Compose 服务。
- E2E 只用 Playwright 访问 `http://127.0.0.1:3010`。
- 运行 E2E 前确认 `/api/health` 连续可用。
- 不用接口 mock、jsdom、截图脚本或伪造通过代替真实浏览器验证。
- 测试失败时修根因，不加入 fallback、吞错或 mock success。

## 核心 API

- `POST /api/projects/:id/agent/chat`
- `GET /api/projects/:id/agent/chat/:sessionId/stream`
- `POST /api/projects/:id/agent/suggest`
- `GET|POST|DELETE /api/projects/:id/memory`
- `POST /api/projects/:id/memory/search`
- `GET /api/projects/:id/memory/visualization`
- `GET|POST /api/projects/:id/skills`
- `POST /api/projects/:id/skills/:slug/toggle`

完整运行时说明见 `ARCHITECTURE.md`。
