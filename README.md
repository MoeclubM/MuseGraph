# MuseGraph

AI 文本创作/分析系统，使用 Cognee + Neo4j 知识图谱构建实体关系。

## 技术栈

- **后端**: Python / FastAPI
- **前端**: Vue 3 + Vite + Tailwind
- **知识图谱**: Cognee + Neo4j
- **数据库**: PostgreSQL (pgvector) + Redis
- **存储**: 本地持久化文件存储（Docker 卷）
- **包管理**: uv (Python), pnpm (前端)

## 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

### 1. 克隆仓库

```bash
git clone <repository-url>
cd MuseGraph
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件（或在 `docker-compose.yml` 中直接修改）：

```env
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
```

### 3. 启动所有服务

```bash
cd docker
docker compose up -d --build
```

服务启动后：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:4080 |
| Neo4j Browser | http://localhost:17474 |

说明：任务系统状态与上传文件会持久化到 Docker 卷 `task_state_data`
（`/app/.musegraph/task_state.sqlite3` 与 `/app/.musegraph/storage`），
用户离线后返回仍可查询任务进度与结果。

### 4. 初始化数据库

```bash
# 进入 server 容器
docker exec -it musegraph-server bash

# 运行迁移
alembic upgrade head
# 可选：初始化基础配置（不会创建 demo 账号）
python seed.py
```

如需创建管理员账号，请在环境变量中设置：
`SEED_ADMIN_EMAIL`、`SEED_ADMIN_PASSWORD`（可选 `SEED_ADMIN_NICKNAME`）。

## 本地开发

仅启动基础设施（PostgreSQL, Redis, Neo4j）：

```bash
cd docker
docker-compose -f docker-compose.infra.yml up -d
```

后端：

```bash
cd apps/server-py
uv pip install -e "."
uvicorn app.main:app --reload --port 4000
```

前端：

```bash
cd apps/web-vue
pnpm install
pnpm dev
```

## 测试

前端单元测试：

```bash
pnpm --filter @musegraph/web test
```

前端覆盖率（包含最低覆盖率门禁）：

```bash
pnpm --filter @musegraph/web test:coverage
```

## 项目结构

```
MuseGraph/
├── apps/
│   ├── server-py/     # FastAPI 后端
│   └── web-vue/       # Vue 3 前端
├── docker/            # Docker 配置
│   ├── docker-compose.yml
│   ├── docker-compose.infra.yml
│   ├── server-py.Dockerfile
│   ├── web-vue.Dockerfile
│   └── nginx.conf
└── packages/          # 共享包
```

## 许可证

MIT
