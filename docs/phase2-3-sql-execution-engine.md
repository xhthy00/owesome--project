# Phase 2.3: SQL 执行引擎

## 概述

SQL 执行引擎负责连接目标数据库、执行生成的 SQL 语句并返回查询结果。本模块基于 SQLBot 参考实现，提供了数据库连接管理、SQL 执行、结果格式化和错误处理功能。

## 架构设计

### 组件结构

```
┌─────────────────────────────────────────────────────────────────┐
│                     API 层                                        │
│  /api/v1/chat/execute-sql   - 生成并执行SQL                      │
│  /api/v1/datasource/test-connection - 测试数据源连接             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SQL 执行引擎层 (db.py)                           │
│  - execute_sql()              - SQL执行入口                      │
│  - check_sql_read()          - SQL只读检查                      │
│  - convert_value()            - 值类型转换                       │
│  - test_db_connection()      - 连接测试                         │
│  - get_schema_info()          - 获取数据库结构                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  数据库连接层                                     │
│  - PostgreSQL (psycopg2)                                         │
│  - MySQL (pymysql)                                              │
└─────────────────────────────────────────────────────────────────┘
```

## 实现细节

### 1. SQL 执行入口

```python
def execute_sql(db_type: str, config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """
    Execute SQL on database.

    流程:
    1. 检查SQL是否为只读操作
    2. 根据数据库类型调用对应的执行函数
    3. 转换结果为JSON可序列化格式

    Returns:
        (success, message, result)
    """
    # 检查SQL是否为只读
    if not check_sql_read(sql, db_type):
        return False, "SQL can only contain read operations (SELECT)", None

    if db_type == "pg":
        return execute_postgresql_sql(config, sql)
    elif db_type == "mysql":
        return execute_mysql_sql(config, sql)
    else:
        return False, f"Unsupported database type: {db_type}", None
```

### 2. SQL 只读检查

使用 sqlglot 库解析 SQL 语句，确保只执行 SELECT 查询：

```python
def check_sql_read(sql: str, db_type: str) -> bool:
    """
    检查SQL是否为只读操作。

    使用sqlglot解析SQL，检测是否存在写操作：
    - INSERT, UPDATE, DELETE
    - CREATE, DROP, ALTER
    - MERGE, COPY

    Args:
        sql: SQL语句
        db_type: 数据库类型 (pg/mysql)

    Returns:
        True if SQL is read-only
    """
    try:
        from sqlglot import parse
        from sqlglot import expressions as exp

        dialect = "mysql" if db_type == "mysql" else None
        statements = parse(sql, dialect=dialect)

        write_types = (
            exp.Insert, exp.Update, exp.Delete,
            exp.Create, exp.Drop, exp.Alter,
            exp.Merge, exp.Copy
        )

        for stmt in statements:
            if stmt is None:
                continue
            if isinstance(stmt, write_types):
                return False

        return True
    except Exception as e:
        return True  # 解析失败时默认放行，由执行时处理错误
```

### 3. 值类型转换

将数据库返回的特殊类型转换为 JSON 可序列化格式：

```python
def convert_value(value: Any, datetime_format: str = 'space') -> Any:
    """
    转换Python值为JSON可序列化类型。

    支持的类型转换：
    - bytes -> str/int/bool
    - Decimal -> float
    - datetime -> str (ISO格式或空格分隔格式)
    - date -> str (ISO格式)
    - time -> str
    - timedelta -> str
    - None -> None
    """
    if value is None:
        return None

    if isinstance(value, bytes):
        # 处理BIT字段等
        if len(value) <= 8:
            try:
                int_val = int.from_bytes(value, 'big')
                if int_val in (0, 1):
                    return bool(int_val)
                return int_val
            except:
                pass

        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return value.decode('latin-1')

    elif isinstance(value, Decimal):
        return float(value)

    elif isinstance(value, datetime):
        if datetime_format == 'iso':
            return value.isoformat()
        else:
            if value.hour == 0 and value.minute == 0 and value.second == 0:
                return value.strftime('%Y-%m-%d')
            return value.strftime('%Y-%m-%d %H:%M:%S')

    elif isinstance(value, date):
        return value.isoformat()

    elif isinstance(value, time):
        return str(value)

    elif isinstance(value, timedelta):
        return str(value)

    return value
```

### 4. PostgreSQL 执行

```python
def execute_postgresql_sql(config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """Execute SQL on PostgreSQL with proper result formatting."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("username", "postgres"),
            password=config.get("password", ""),
            database=config.get("database", "postgres"),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            # 转换值为JSON可序列化格式
            converted_rows = []
            for row in rows:
                converted_row = [convert_value(v) for v in row]
                converted_rows.append(converted_row)

            result = {
                "columns": columns,
                "rows": converted_rows,
                "row_count": len(rows),
            }
        else:
            conn.commit()
            result = {"row_count": cursor.rowcount}

        cursor.close()
        conn.close()

        return True, "Success", result
    except Exception as e:
        return False, f"SQL execution failed: {str(e)}", None
```

### 5. MySQL 执行

```python
def execute_mysql_sql(config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """Execute SQL on MySQL with proper result formatting."""
    try:
        import pymysql

        conn = pymysql.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config.get("username", "root"),
            password=config.get("password", ""),
            database=config.get("database", ""),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute(sql)

        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            # 转换值为JSON可序列化格式
            converted_rows = []
            for row in rows:
                converted_row = [convert_value(v) for v in row]
                converted_rows.append(converted_row)

            result = {
                "columns": columns,
                "rows": converted_rows,
                "row_count": len(rows),
            }
        else:
            conn.commit()
            result = {"row_count": cursor.rowcount}

        cursor.close()
        conn.close()

        return True, "Success", result
    except Exception as e:
        return False, f"SQL execution failed: {str(e)}", None
```

### 6. 连接测试

```python
def test_db_connection(db_type: str, config: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """
    测试数据库连接。

    Returns:
        (success, message, version)
    """
    if db_type == "pg":
        return test_postgresql_connection(config)
    elif db_type == "mysql":
        return test_mysql_connection(config)
    else:
        return False, f"Unsupported database type: {db_type}", None
```

### 7. Schema 信息获取

```python
def get_schema_info(db_type: str, config: Dict[str, Any]) -> list:
    """
    获取数据库Schema信息。

    Returns:
        List of table info dicts:
        [
            {
                "name": "users",
                "comment": "User table",
                "fields": [
                    {"name": "id", "type": "bigint", "comment": "Primary key"},
                    {"name": "name", "type": "varchar(255)", "comment": "Name"},
                ]
            },
            ...
        ]
    """
```

#### PostgreSQL Schema 查询

```sql
-- 获取表列表
SELECT c.relname AS table_name,
       COALESCE(d.description, '') AS table_comment
FROM pg_catalog.pg_class c
LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_description d ON d.objoid = c.oid AND d.objsubid = 0
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'v', 'p', 'm')
  AND c.relname NOT LIKE 'pg_%'
  AND c.relname NOT LIKE 'sql_%'
ORDER BY c.relname

-- 获取字段列表
SELECT a.attname AS column_name,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       COALESCE(col_description(c.oid, a.attnum), '') AS column_comment
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = %s
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum
```

#### MySQL Schema 查询

```sql
-- 获取表列表
SHOW TABLES

-- 获取表注释
SELECT TABLE_COMMENT FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s

-- 获取字段列表
DESCRIBE `{table_name}`
```

## 错误处理

### 错误类型及处理方式

| 错误类型 | 原因 | 处理方式 |
|----------|------|----------|
| 连接失败 | 主机不可达、端口错误、认证失败 | 返回连接错误信息 |
| 超时错误 | 查询执行时间过长 | 设置 connect_timeout |
| SQL语法错误 | SQL语句不正确 | 返回具体错误信息 |
| 权限错误 | 用户权限不足 | 返回权限错误信息 |
| 写操作拒绝 | 执行了非SELECT操作 | 拦截并返回错误 |

### 错误响应格式

```python
# 执行失败
return False, "SQL execution failed: {error_message}", None

# 成功
return True, "Success", {
    "columns": ["col1", "col2"],
    "rows": [[val1, val2], [val3, val4]],
    "row_count": 2
}
```

## API 接口

### POST /api/v1/datasource/test-connection

测试数据源连接。

**请求：**
```json
{
    "type": "pg",
    "config": {
        "host": "localhost",
        "port": 5432,
        "username": "postgres",
        "password": "password",
        "database": "testdb",
        "timeout": 30
    }
}
```

**响应：**
```json
{
    "code": 200,
    "message": "Connection successful",
    "data": {
        "success": true,
        "message": "Connection successful",
        "version": "PostgreSQL 16.1"
    }
}
```

### 执行结果格式

```json
{
    "columns": ["id", "name", "score"],
    "rows": [
        [1, "张三", 85.5],
        [2, "李四", 92.0]
    ],
    "row_count": 2
}
```

## 文件结构

```
src/
├── datasource/
│   ├── db/
│   │   └── db.py          # SQL执行引擎
│   └── crud/
│       └── crud_datasource.py  # 数据源CRUD
└── chat/
    ├── api/
    │   └── chat.py         # 聊天API
    └── service/
        └── sql_generator.py    # SQL生成服务
```

## 实现过程

### Phase 2.3 实现步骤

1. **参考SQLBot实现**
   - 分析 `apps/db/db.py` 中的核心函数
   - 学习 SQL 只读检查机制 (check_sql_read)
   - 学习值类型转换 (convert_value)

2. **增强现有实现**
   - 添加 `check_sql_read()` 函数使用 sqlglot
   - 添加 `convert_value()` 函数处理特殊类型
   - 增强错误处理，返回详细错误信息

3. **类型转换支持**
   - bytes -> str/int/bool
   - Decimal -> float
   - datetime -> str
   - date -> str
   - time -> str
   - timedelta -> str

## 测试

### 单元测试

```python
# 测试值转换
from src.datasource.db.db import convert_value
from decimal import Decimal
from datetime import datetime

assert convert_value(None) is None
assert convert_value(Decimal("1.5")) == 1.5
assert convert_value(datetime(2024, 1, 15, 10, 30, 0)) == "2024-01-15 10:30:00"

# 测试SQL只读检查
from src.datasource.db.db import check_sql_read

assert check_sql_read("SELECT * FROM users", "pg") == True
assert check_sql_read("INSERT INTO users VALUES (1)", "pg") == False
assert check_sql_read("UPDATE users SET name = 'test'", "mysql") == False
```

### 集成测试

```bash
# 测试PostgreSQL连接
curl -X POST http://localhost:8000/api/v1/datasource/test-connection \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type": "pg", "config": {"host": "localhost", "port": 5432, "username": "postgres", "password": "password", "database": "testdb"}}'
```

## 参考资料

- SQLBot DB实现：`/Users/tanghaoyu/develop/git-repo/opensource/SQLBot-main/backend/apps/db/db.py`
- SQLGlot文档：https://sqlglot.readthedocs.io/