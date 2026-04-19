# Phase 1.1 项目结构搭建

## 概述

本模块完成了 FastAPI 项目的基础骨架搭建，包括：

- FastAPI 应用入口
- SQLModel + PostgreSQL 数据库连接配置
- Alembic 数据库迁移工具配置

---

## 目录结构

```
awesome-project/
├── alembic.ini              # Alembic 配置文件
├── alembic/                 # Alembic 迁移目录
│   ├── env.py              # 迁移环境配置
│   ├── script.py.mako      # 迁移脚本模板
│   ├── README
│   └── versions/           # 迁移版本目录
├── src/
│   ├── main.py             # FastAPI 应用入口
│   ├── awesome/            # 项目包
│   │   └── __init__.py
│   ├── common/             # 公共模块
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── config.py   # 配置管理
│   │       └── database.py # 数据库连接
│   ├── datasource/         # 数据源模块
│   │   └── models/
│   │       └── datasource.py
│   └── db/                 # 数据库工具模块
│       ├── __init__.py
│       ├── constant.py
│       └── db_sql_gen.py
├── .env.example            # 环境变量示例
└── pyproject.toml
```

---

## 核心模块说明

### 1. 配置管理 (`src/common/core/config.py`)

使用 `pydantic-settings` 管理配置，支持从 `.env` 文件加载。

**主要配置项：**

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `APP_NAME` | 应用名称 | `awesome-project` |
| `DEBUG` | 调试模式 | `false` |
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql://postgres:postgres@localhost:5432/awesome` |
| `JWT_SECRET_KEY` | JWT 密钥 | `your-secret-key-change-in-production` |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` |
| `LLM_BASE_URL` | LLM API 地址 | `None` |

**使用方式：**

```python
from src.common.core.config import get_settings

settings = get_settings()
print(settings.database_url)
```

---

### 2. 数据库连接 (`src/common/core/database.py`)

基于 SQLModel 和 SQLAlchemy 的数据库连接管理。

**主要功能：**

- `engine` - SQLAlchemy 引擎实例
- `SessionLocal` - Session 工厂
- `init_db()` - 初始化数据库表
- `get_session()` - FastAPI 依赖注入
- `get_db_session()` - 上下文管理器方式
- `Base` - SQLModel 的 MetaData 基类（供 Alembic 使用）

**使用方式：**

```python
# 依赖注入方式
from fastapi import Depends
from sqlalchemy.orm import Session
from src.common.core.database import get_session

@app.get("/users")
def get_users(session: Session = Depends(get_session)):
    ...

# 上下文管理器方式
from src.common.core.database import get_db_session

with get_db_session() as session:
    result = session.query(User).all()
```

---

### 3. FastAPI 应用 (`src/main.py`)

应用入口文件，包含：

- CORS 中间件配置
- 启动事件（`on_startup`）自动创建表
- 健康检查端点 `/health`

**启动方式：**

```bash
# 方式1：直接运行
python -m src.main

# 方式2：使用 uvicorn
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

---

### 4. Alembic 迁移

#### 初始化迁移目录

```bash
# 自动生成初始迁移
alembic revision --autogenerate -m "initial migration"
```

#### 常用命令

| 命令 | 说明 |
|------|------|
| `alembic revision --autogenerate -m "message"` | 生成新迁移 |
| `alembic upgrade head` | 执行最新迁移 |
| `alembic downgrade -1` | 回滚上一版本 |
| `alembic history` | 查看迁移历史 |
| `alembic current` | 查看当前版本 |

---

## 环境配置

### 1. 复制环境变量文件

```bash
cp .env.example .env
```

### 2. 修改 `.env` 中的配置

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/awesome
JWT_SECRET_KEY=your-production-secret-key
```

---

## 验证

### 测试配置加载

```bash
python3 -c "from src.common.core.config import get_settings; print(get_settings().app_name)"
```

### 测试数据库连接

```bash
python3 -c "from src.common.core.database import engine; print('engine created')"
```

### 启动应用

```bash
python -m src.main
# 访问 http://localhost:8000/health 应返回 {"status": "ok"}
```

---

## 后续开发

Phase 1.1 完成后的开发检查清单：

- [x] 初始化 FastAPI 项目
- [x] 配置 SQLModel + PostgreSQL 连接
- [x] 配置 Alembic 数据库迁移

下一阶段（Phase 1.2）将实现用户认证模块。