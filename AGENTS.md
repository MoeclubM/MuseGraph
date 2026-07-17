# MuseGraph 开发指南

## 开发约束

1. 简单逻辑直接内联，非必要不拆分函数或包装层。
2. 写新代码前先搜索并复用现有接口。
3. 信任内部数据，只在 HTTP、文件、Provider 等真实边界校验。
4. 模块按功能拆分，避免单文件持续膨胀。
5. 命令行修改非英文文件前确认 UTF-8 编码。

项目仍处于开发期，不考虑向后兼容。迁移后直接删除旧路径、旧配置和旧角色，不在主代码中加入兼容、自动迁移、静默降级或 mock success。内部失败必须通过异常、日志或失败测试显式暴露。

## 技术栈

- Vue 3 + Vite 8 + Tailwind CSS 4
- Python 3.14 + FastAPI
- 持久化 Agent Worker + LiteLLM
- Cognee 1.4 每项目隔离进程
- PostgreSQL + Redis
- uv + Node 24 + pnpm 11

## 当前生产架构

- `app/services/agent_engine.py`：唯一 Agent 生产运行时
- `app/services/agent/tool_registry.py`：唯一工具 Schema、角色门和处理器注册表
- `app/services/agent/skills.py`：唯一项目 Skill 解析入口
- `app/services/agent/pack_core.py`：严格 Text Pack 加载
- `app/services/agent_workspace.py`：Run 隔离工作区和候选变更
- `app/agent_worker_main.py`：数据库队列、租约、心跳、恢复和取消
- `app/memory_service_main.py`：内部 Memory Service
- `app/services/memory_runtime.py`：每项目 Cognee 子进程
- `app/services/project_files.py`：Git 项目文件
- `app/services/project_git.py`：项目 Git 与内部 bare remote

不存在旧 Chat/Session Agent API、`partial` 成功、SQLite TaskManager、进程内 Agent BackgroundTasks、Hy-Memory、`creative_state.structured_memory` 或旧 Pi SDK 运行时。不要重新引入。

## 权威数据

- Git：文本、控制文档和目录结构
- 每项目 Cognee Dataset：结构化知识
- PostgreSQL：用户、权限、Run、审核、版本指针和审计
- Redis：实时事件与限流，不保存权威任务状态

## Docker

所有构建和测试在 WSL Debian 或容器中执行。构建前：

```bash
cd /mnt/c/Users/QwQ/Documents/GitHub/MuseGraph/docker
docker compose down --remove-orphans
docker system prune -a -f
docker system df
docker compose build
docker compose up -d --wait
```

只有明确重建开发数据时才使用 `docker compose down -v`。

## 依赖与数据库

```bash
cd apps/server-py
uv sync --frozen
uv run alembic upgrade head

cd ../..
pnpm install --frozen-lockfile
```

Docker 后端必须复制 `uv.lock` 并使用 `uv sync --frozen`。前端只使用根目录 `pnpm-lock.yaml`。数据库使用单一当前基线，不加入历史兼容迁移。

## 测试

- PostgreSQL、Redis、Memory、Worker、前端或跨服务测试必须启动真实 Compose。
- E2E 只用 Playwright 访问 `http://127.0.0.1:3010`。
- 不使用接口 mock、jsdom、截图脚本或模板输出代替真实验证。
- 失败时修根因，不加入 fallback、吞错或 fake success。

## 核心 API

- `POST /api/projects/:id/agent/runs`
- `GET /api/projects/:id/agent/runs/:runId`
- `GET /api/projects/:id/agent/runs/:runId/events`
- `GET /api/projects/:id/agent/runs/:runId/changes`
- `POST /api/projects/:id/agent/runs/:runId/review`
- `POST /api/projects/:id/agent/runs/:runId/cancel`
- `GET|POST /api/projects/:id/memory`
- `GET|POST /api/projects/:id/skills`

完整说明见 `ARCHITECTURE.md`。
