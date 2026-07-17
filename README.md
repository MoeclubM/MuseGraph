# MuseGraph

MuseGraph 是一个以 Git 文本仓库和结构化知识版本为核心的长文本创作平台。每次 Agent 创作先在隔离工作区生成完整变更集，经用户整轮审核后，才同时发布新的 Git Commit 与不可变 Cognee Dataset。

## 架构

- Web：Vue 3、Vite 8、Tailwind CSS 4、Pinia
- API：Python 3.14、FastAPI、SQLAlchemy
- Agent：持久化数据库队列、独立 Worker、LiteLLM、严格 Tool Registry
- 记忆：Cognee 1.4，每项目独立子进程与存储目录
- 数据：PostgreSQL 保存业务状态，Redis 只保存实时事件与限流计数
- 项目：Git 是文本、控制文档与目录结构的唯一权威
- 工具链：uv、Node 24、pnpm 11

完整数据边界和执行流程见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## Docker 开发环境

复制开发环境变量并替换内部随机值：

```bash
cd /mnt/c/Users/QwQ/Documents/GitHub/MuseGraph/docker
cp .env.example .env
```

Provider API Key 不写入文件或仓库，通过管理后台配置。首次或全量重建：

```bash
docker compose down -v --remove-orphans
docker system prune -a -f
docker system df
docker compose build
docker compose up -d --wait
```

正常重建若要保留 PostgreSQL、Git 和 Cognee 数据，不使用 `-v`。

| 服务 | 地址 |
|---|---|
| Web | http://127.0.0.1:3010 |
| API | http://127.0.0.1:4080 |
| 健康检查 | http://127.0.0.1:4080/api/health |

创建显式开发管理员：

```bash
SEED_ADMIN_EMAIL=admin@example.com \
SEED_ADMIN_PASSWORD='replace-with-a-development-password' \
docker compose --profile tools run --rm seed
```

## 验证

后端合约测试：

```bash
cd apps/server-py
uv sync --frozen --extra test
uv run pytest -q
```

前端类型检查和构建：

```bash
pnpm install --frozen-lockfile
pnpm build
```

真实跨服务集成和浏览器 E2E：

```bash
cd docker
docker compose up -d --wait
docker compose --profile test run --rm backend-tests
docker compose --profile test run --rm e2e
```

E2E 只访问真实 `http://127.0.0.1:3010`，不使用接口 mock、jsdom 或模板结果。受保护的真实 Provider 验收通过 `protected-test` profile 显式运行。

## 核心接口

- `POST /api/projects/:id/agent/runs`
- `GET /api/projects/:id/agent/runs/:runId`
- `GET /api/projects/:id/agent/runs/:runId/events`
- `GET /api/projects/:id/agent/runs/:runId/changes`
- `POST /api/projects/:id/agent/runs/:runId/review`
- `POST /api/projects/:id/agent/runs/:runId/cancel`
- `GET|POST /api/projects/:id/memory`
- `POST /api/projects/:id/memory/changes`
- `GET|POST /api/projects/:id/skills`
- `GET /api/projects/:id/skills/resolve/preview`

## License

Apache-2.0
