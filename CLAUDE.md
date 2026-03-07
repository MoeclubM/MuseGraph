# MuseGraph 开发指南

## 项目简介

MuseGraph 是一个商业级 AI 文本创作/分析/续写系统，当前默认使用 Zep Cloud 图谱后端构建实体关系。

## 技术栈

- 前端: Vue 3 + Vite + Tailwind
- 后端: Python / FastAPI
- 知识图谱: Zep Cloud（过渡期默认）
- 数据库: PostgreSQL + Redis (Docker 本地部署)
- 存储: 本地持久化文件存储（Docker 卷）
- 包管理: uv (Python), pnpm (前端)

## Docker 开发环境

### 启动基础设施服务 (PostgreSQL, Redis)

```bash
cd docker
docker-compose -f docker-compose.infra.yml up -d
```

### 启动所有服务 (包括应用)

```bash
cd docker
docker-compose up -d
```

### 服务端口

| 服务 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| Redis | 6379 |
| 后端 API | 4000 |
| 前端 Web | 3000 |

### 初始化数据库

首次启动后需要运行迁移和种子数据：

```bash
cd apps/server-py
uv pip install -e "."
alembic upgrade head
python -m app.seed
```

### 构建并启动应用

```bash
cd docker
docker-compose build
docker-compose up -d
```

### 查看日志

```bash
docker-compose logs -f server
docker-compose logs -f web
docker-compose logs -f postgres
```

### 停止服务

```bash
cd docker
docker-compose down
```

### 清理数据

```bash
cd docker
docker-compose down -v  # 同时删除数据卷
```

## 开发命令

> 注意: 不建议本地运行项目，统一使用 Docker

### 本地开发 (仅在需要调试时)

```bash
# 后端
cd apps/server-py
uv pip install -e "."
uvicorn app.main:app --reload --port 4000

# 前端
cd apps/web-vue
pnpm install
pnpm dev
```

## 数据库

### Alembic 操作

```bash
cd apps/server-py

# 运行迁移
alembic upgrade head

# 创建新迁移
alembic revision --autogenerate -m "description"

# 回滚迁移
alembic downgrade -1

# 查看迁移历史
alembic history

# 运行种子数据
python -m app.seed
```

### 数据库连接

```
Host: localhost
Port: 5432
Database: musegraph
User: musegraph
Password: musegraph123
```

### Zep Cloud 配置

```env
GRAPH_BACKEND=zep
ZEP_API_KEY=<your-zep-api-key>
```

## 环境变量

### 后端 (.env)

```env
DATABASE_URL=postgresql+asyncpg://musegraph:musegraph123@localhost:5432/musegraph
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-super-secret-jwt-key
JWT_ALGORITHM=HS256
JWT_EXPIRES_HOURS=168
FILE_STORAGE_ROOT=.musegraph/storage
GRAPH_BACKEND=zep
ZEP_API_KEY=<your-zep-api-key>
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
APP_URL=http://localhost:3000
```

### 前端

```env
VITE_API_URL=http://localhost:4000
```

## 主要功能

1. **用户系统**: 注册/登录/JWT认证
2. **用户等级**: 可自定义用户组 (free/basic/pro/enterprise)
3. **配额管理**: 每日/每月请求限制
4. **模型权限**: 不同等级用户可使用不同AI模型
5. **AI文本**: 创作/续写/分析/重写/摘要
6. **知识图谱**: Zep Cloud 驱动的实体提取/关系构建/可视化
7. **计费系统**: 易支付集成/套餐订阅/余额充值
8. **导出功能**: 支持多种格式导出

## 核心 API 端点

### 认证
- `POST /api/auth/register` - 注册
- `POST /api/auth/login` - 登录
- `POST /api/auth/logout` - 登出
- `GET /api/auth/me` - 获取当前用户

### 用户
- `GET /api/users/:id` - 获取用户信息
- `GET /api/users/:id/usage` - 获取用户使用统计

### 用户组
- `GET /api/groups` - 用户组列表
- `GET /api/groups/me` - 获取当前用户组
- `POST /api/groups/user/:userId` - 更改用户组 (管理员)

### 项目
- `GET /api/projects` - 项目列表
- `POST /api/projects` - 创建项目
- `GET /api/projects/:id` - 获取项目
- `PUT /api/projects/:id` - 更新项目
- `DELETE /api/projects/:id` - 删除项目

### AI 操作
- `POST /api/projects/:id/operation` - 执行AI操作
- `GET /api/ai/models` - 获取可用模型

### 知识图谱 (Zep Cloud)
- `GET /api/projects/:id/graphs` - 图谱状态
- `POST /api/projects/:id/graphs` - 添加文本到图谱
- `POST /api/projects/:id/graphs/search` - 搜索图谱
- `GET /api/projects/:id/graphs/visualization` - 可视化数据
- `DELETE /api/projects/:id/graphs` - 删除图谱

### 支付
- `POST /api/payment/create` - 创建支付订单
- `GET /api/payment/callback` - 支付回调
- `GET /api/payment/order/:orderNo` - 查询订单状态

### 管理后台 (需 ADMIN 角色)
- `GET /api/admin/stats` - 数据统计
- `GET /api/admin/users` - 用户管理
- `GET /api/admin/groups` - 用户组管理
- `GET /api/admin/providers` - AI服务商管理
- `GET /api/admin/pricing` - 定价规则
- `GET /api/admin/plans` - 套餐管理
- `GET /api/admin/orders` - 订单管理
