# MuseGraph

MuseGraph 是一个面向长文本创作、分析和协作写作的 AI 工作区。生产运行时由 Pi Agent 工具循环驱动，项目语义记忆与关系图谱由 Cognee 构建，模型调用统一经 LiteLLM 路由。

## 技术栈

- 前端：Vue 3、Vite 8、Tailwind CSS 4、Pinia
- 后端：Python 3.12、FastAPI、SQLAlchemy
- Agent：Pi Agent、多角色子代理、项目级 Skills
- 记忆：Cognee
- 数据：PostgreSQL、Redis、本地项目工作区
- 包管理：uv、pnpm

## Docker 启动

项目统一在 WSL Debian 中构建和测试。重新构建前必须清理旧镜像和构建缓存，但不删除数据卷：

```bash
cd /mnt/c/Users/QwQ/Documents/GitHub/MuseGraph/docker
docker compose down --remove-orphans
docker system prune -a -f
docker system df
docker compose build
docker compose up -d
```

服务地址：

| 服务 | 地址 |
|---|---|
| Web | http://127.0.0.1:3010 |
| API | http://127.0.0.1:4080 |
| API 健康检查 | http://127.0.0.1:4080/api/health |

首次启动后执行：

```bash
docker exec musegraph-server alembic upgrade head
docker exec musegraph-server python seed.py
```

管理员启动参数通过 Compose 环境变量设置：

```env
SEED_ADMIN_EMAIL=admin@example.com
SEED_ADMIN_PASSWORD=replace-me
SEED_ADMIN_NICKNAME=Administrator
```

模型 Provider、API Key、聊天模型和嵌入模型均通过 Admin → Providers 配置，不写入仓库。

## 关键环境变量

```env
DATABASE_URL=postgresql+asyncpg://musegraph:musegraph123@postgres:5432/musegraph
REDIS_URL=redis://redis:6379
FILE_STORAGE_ROOT=/app/.musegraph/storage
TASK_STATE_SQLITE_PATH=/app/.musegraph/task_state.sqlite3
COGNEE_DATA_DIR=/app/.musegraph/cognee
COGNEE_INGEST_TIMEOUT_SECONDS=300
COGNEE_LLM_MAX_TOKENS=8192
APP_URL=http://localhost:3010
```

## 开发命令

依赖由锁文件固定：

```bash
cd apps/server-py
uv sync --frozen

cd ../..
pnpm install --frozen-lockfile
```

本地调试仅在必要时使用：

```bash
cd apps/server-py
uv run uvicorn app.main:app --reload --port 4000

cd apps/web-vue
pnpm dev
```

## 验证

生产镜像构建、健康检查和 E2E 都在 WSL/Docker 中执行。E2E 必须访问真实服务，不使用接口 mock 或伪造结果：

```bash
cd docker
docker compose build
docker compose up -d

curl -fsS http://127.0.0.1:4080/api/health
curl -fsSI http://127.0.0.1:3010/

cd ..
pnpm install --frozen-lockfile
pnpm --dir apps/web-vue test:e2e:docker
```

运行 Playwright 前先确认 `/api/health` 连续可用。

## 目录

```text
apps/server-py/   FastAPI、Agent、Cognee、数据库迁移
apps/web-vue/     Vue 工作区与 Playwright E2E
packages/         共享 TypeScript 类型与 AI adapters
docker/           Compose、镜像和 Nginx 配置
scripts/          管理、导入与真实服务 smoke 脚本
```

更完整的运行时说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## License

Apache-2.0
