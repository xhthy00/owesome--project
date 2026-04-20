# Phase 1.4 基础 API 框架

## 概述

本模块实现了基础 API 框架，包括：

- API 路由聚合
- 统一的响应格式
- 错误处理中间件

---

## 目录结构

```
src/
├── main.py                              # FastAPI 入口
├── common/
│   ├── router.py                       # 路由聚合
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── response.py                # 统一响应格式
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── base.py                    # 自定义异常
│   └── middlewares/
│       ├── __init__.py
│       └── exception.py               # 异常处理器
├── system/                             # 用户认证模块
│   └── api/
│       └── system.py
└── datasource/                         # 数据源模块
    └── api/
        └── datasource.py
```

---

## 实现逻辑详解

### 1. 统一响应格式 (`src/common/schemas/response.py`)

所有 API 响应采用统一格式：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

**响应模型：**

```python
class ResponseBase(BaseModel):
    """基础响应模型"""
    code: int = 200           # 状态码
    message: str = "success"  # 消息

class ResponseModel(ResponseBase, Generic[T]):
    """通用响应模型（带数据）"""
    data: Optional[T] = None

class PageData(BaseModel, Generic[T]):
    """分页数据"""
    items: List[T]
    total: int
    page: int
    page_size: int
```

**响应辅助函数：**

```python
def success_response(data=None, message="success") -> dict:
    """成功响应"""
    return {"code": 200, "message": message, "data": data}

def error_response(code=400, message="error", data=None) -> dict:
    """错误响应"""
    return {"code": code, "message": message, "data": data}
```

**响应格式规范：**

| 场景 | code | message | data |
|------|------|---------|------|
| 成功 | 200 | success | 实际数据 |
| 创建成功 | 201 | created | 数据 |
| 参数错误 | 400 | 错误描述 | null |
| 未认证 | 401 | unauthorized | null |
| 资源不存在 | 404 | not found | null |
| 服务器错误 | 500 | internal error | null |

---

### 2. 自定义异常 (`src/common/exceptions/base.py`)

定义应用层异常，统一错误处理：

```python
class AppException(Exception):
    """基础应用异常"""
    def __init__(self, message: str = "Internal server error", code: int = 500):
        self.message = message
        self.code = code

class NotFoundException(AppException):
    """资源不存在"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, code=404)

class BadRequestException(AppException):
    """请求错误"""
    def __init__(self, message: str = "Bad request"):
        super().__init__(message=message, code=400)

class UnauthorizedException(AppException):
    """未认证"""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message=message, code=401)

class ValidationException(AppException):
    """验证错误"""
    def __init__(self, message: str = "Validation error", errors: list = None):
        super().__init__(message=message, code=422)
        self.errors = errors or []
```

**使用示例：**

```python
from src.common.exceptions.base import NotFoundException, BadRequestException

def get_user(user_id: int):
    user = db.query(User).get(user_id)
    if not user:
        raise NotFoundException(f"User {user_id} not found")
    return user
```

---

### 3. 异常处理器 (`src/common/middlewares/exception.py`)

全局异常处理，将异常转换为统一响应格式：

```python
def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        return JSONResponse(
            status_code=200,  # 统一使用 200，数据中带实际状态码
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
            },
        )

    @app.exception_handler(ValidationException)
    async def validation_exception_handler(request, exc: ValidationException):
        return JSONResponse(
            status_code=200,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": {"errors": exc.errors},
            },
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request, exc: ValidationError):
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
            })
        return JSONResponse(
            status_code=200,
            content={
                "code": 422,
                "message": "Validation error",
                "data": {"errors": errors},
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        return JSONResponse(
            status_code=200,
            content={
                "code": 500,
                "message": "Internal server error",
                "data": None,
            },
        )
```

**处理流程：**

```
请求 → 视图函数抛出异常 → 异常处理器捕获 → 转换为统一格式 → 返回响应
```

---

### 4. 路由聚合 (`src/common/router.py`)

集中管理所有 API 路由：

```python
from system.api.system import router as system_router
from datasource.api.datasource import router as datasource_router

def get_all_routers() -> list:
    """获取所有路由"""
    return [
        system_router,
        datasource_router,
    ]

def register_routers(app: FastAPI) -> None:
    """注册路由到应用"""
    for router in get_all_routers():
        app.include_router(router, prefix="/api/v1")
```

**在 main.py 中使用：**

```python
from common.router import register_routers
from common.middlewares.exception import register_exception_handlers

app = FastAPI(...)

# 注册异常处理器
register_exception_handlers(app)

# 注册路由
register_routers(app)
```

---

### 5. 主入口 (`src/main.py`)

```python
"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.core.config import get_settings
from common.core.database import init_db
from common.router import register_routers
from common.middlewares.exception import register_exception_handlers

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 注册异常处理器
register_exception_handlers(app)

# 注册路由
register_routers(app)

@app.get("/health")
def health_check():
    return {"code": 200, "message": "ok", "data": {"status": "ok"}}
```

---

## API 响应示例

### 成功响应

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "name": "test"
  }
}
```

### 错误响应

```json
{
  "code": 404,
  "message": "User 1 not found",
  "data": null
}
```

### 分页响应

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

### 验证错误

```json
{
  "code": 422,
  "message": "Validation error",
  "data": {
    "errors": [
      {"field": "account", "message": "field required"},
      {"field": "password", "message": "string too short"}
    ]
  }
}
```

---

## 现有 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/system/register` | 用户注册 |
| POST | `/api/v1/system/login` | 用户登录 |
| GET | `/api/v1/system/me` | 获取当前用户 |
| GET | `/api/v1/datasource` | 查询数据源列表 |
| GET | `/api/v1/datasource/{id}` | 获取数据源 |
| POST | `/api/v1/datasource` | 创建数据源 |
| PUT | `/api/v1/datasource/{id}` | 更新数据源 |
| DELETE | `/api/v1/datasource/{id}` | 删除数据源 |
| POST | `/api/v1/datasource/{id}/test-connection` | 测试连接 |
| GET | `/health` | 健康检查 |

---

## 验证

### 测试响应格式

```bash
curl http://localhost:8000/health
# 返回: {"code": 200, "message": "ok", "data": {"status": "ok"}}
```

### 测试异常处理

```bash
# 访问不存在的用户
curl http://localhost:8000/api/v1/system/me -H "Authorization: Bearer invalid"
# 返回: {"code": 401, "message": "Invalid or expired token", "data": null}
```

---

## 后续开发

Phase 1.4 完成后的开发检查清单：

- [x] API 路由聚合
- [x] 统一的响应格式
- [x] 错误处理中间件

Phase 1 核心骨架已完成。下一阶段（Phase 2）将实现 LLM 集成和自然语言转 SQL 功能。
