# Phase 2.2: 自然语言转SQL生成

## 概述

本阶段实现将自然语言问题转换为SQL查询的核心功能，参考SQLBot开源项目的实现模式。系统通过LLM结合精心设计的提示词模板来理解用户意图并生成有效、安全的SQL语句。

## 架构设计

### 组件结构

```
┌─────────────────────────────────────────────────────────────────┐
│                     Chat API 层                                   │
│  /api/v1/chat/generate-sql  - 根据问题生成SQL                    │
│  /api/v1/chat/execute-sql   - 生成并执行SQL                      │
│  /api/v1/chat/validate-sql  - 验证SQL语法                        │
│  /api/v1/chat/format-sql    - 格式化SQL语句                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SQLGenerator 服务层                              │
│  - build_sql_generation_prompt()  - 构建SQLBot风格提示词         │
│  - generate_sql()                  - 主SQL生成逻辑                │
│  - generate_sql_with_retry()       - 带错误反馈的重试机制          │
│  - _get_schema()                   - 获取数据库schema            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              提示词模板层 (sql_gen_prompt.py)                       │
│  - 系统提示词包含SQL生成规则                                       │
│  - 过程检查步骤                                                   │
│  - 数据限制策略（默认1000行）                                     │
│  - 多表字段限定规则                                               │
│  - 图表类型选择规则                                               │
│  - M-Schema格式的数据库结构                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  LLM 服务层 (Phase 2.1)                          │
│  - ChatOpenAI / Ollama 通过LangChain集成                         │
│  - build_chat_messages() - 消息格式处理                          │
│  - create_llm() - LLM工厂类                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 实现过程

### Phase 2.2 实现步骤

#### 第一步：参考代码分析

- 分析SQLBot项目的 `apps/chat/task/llm.py`（LLMService类）
- 研究SQLBot项目的 `templates/template.yaml` 提示词模板
- 确定关键组件：系统提示词、过程检查、JSON响应格式

#### 第二步：提示词模板实现

- 创建 `src/templates/sql_gen_prompt.py`，实现SQLBot风格的提示词
- 实现M-Schema格式用于数据库结构表示
- 添加11阶段验证工作流的"过程检查步骤"
- 集成数据限制策略（默认1000行）
- 添加多表字段限定规则
- 配置图表类型选择逻辑

#### 第三步：SQL生成服务

- 创建 `src/chat/service/sql_generator.py`
- 实现 `SQLGenerator` 类的主生成逻辑
- 添加 `generate_sql_with_retry()` 方法实现自动错误恢复
- 集成 `parse_llm_sql_response()` 进行JSON解析
- 添加 `generate_followup_questions()` 生成追问建议

#### 第四步：SQL验证

- 增强 `src/chat/utils/sql_validator.py`
- 安全检查：仅允许SELECT、禁止危险关键词
- 语法验证：括号匹配、正确格式化
- 添加 `extract_sql()` 处理markdown/代码块
- 添加 `format_sql()` 进行数据库特定格式化

#### 第五步：API端点

- 更新 `src/chat/api/chat.py`，实现4个端点
- 实现统一响应格式
- 添加自定义异常的错误处理
- 集成数据源认证

#### 第六步：Schema定义

- 创建 `src/chat/schemas.py`
- 定义 `ChatRequest` 输入验证模型
- 为所有端点创建结果Schema

## 实现细节

### 1. 提示词模板系统

基于SQLBot的template.yaml，提示词系统包含：

#### 系统提示词组件

**过程检查步骤：**
```xml
<SQL-Generation-Process>
  <step>1. 分析用户问题，确定查询需求</step>
  <step>2. 根据表结构生成基础SQL</step>
  <step>3. 验证SQL中使用的表名和字段名是否在<m-schema>中定义</step>
  <step>4. 应用数据量限制规则（默认限制1000条）</step>
  <step>5. 应用其他规则（引号、别名、格式化等）</step>
  <step>6. 验证SQL语法是否符合<db-engine>规范</step>
  <step>7. 确定图表类型（table/column/bar/line/pie）</step>
  <step>8. 确定对话标题</step>
  <step>9. 生成JSON结果</step>
  <step>10. 验证JSON格式是否正确</step>
  <step>11. 返回JSON结果</step>
</SQL-Generation-Process>
```

**数据限制策略：**
- 默认限制：1000行
- 用户可指定"前10条"等数量
- "所有数据"仍使用1000限制
- 对缺少LIMIT子句零容忍

**多表字段限定规则：**
- 所有字段引用必须用表名/别名限定
- 适用于SELECT、WHERE、GROUP BY、HAVING、ORDER BY、ON子句
- 所有多表查询强制执行

#### M-Schema格式

数据库结构格式化为：
```
# Table: users, 用户账号表
[(id: bigint, 主键, ID), (name: varchar(255), 用户名), (email: varchar(255), 邮箱)]
```

### 2. SQL生成流程

```python
def generate_sql(question, datasource_id, session, ...):
    # 1. 获取数据源并解密配置
    datasource = crud_datasource.get_datasource_by_id(session, datasource_id)
    config = decrypt_conf(datasource.configuration)

    # 2. 获取数据库结构信息
    schema_info = _get_schema(datasource, config, db_type)

    # 3. 构建SQLBot风格的提示词
    system_prompt, user_prompt = build_sql_generation_prompt(
        question=question,
        database_type=db_type,
        schema_info=schema_info,
        ...
    )

    # 4. 调用LLM
    messages = build_chat_messages(system_prompt, user_prompt)
    raw_response = llm.chat(messages)

    # 5. 解析JSON响应
    parse_result = parse_llm_sql_response(raw_response)

    # 6. 验证和格式化SQL
    sql = extract_sql(parse_result["sql"])
    is_valid, error_msg = validate_sql(sql)
    formatted_sql = format_sql(sql, db_type)

    return {
        "sql": sql,
        "is_valid": is_valid,
        "formatted_sql": formatted_sql,
        "tables": parse_result["tables"],
        "chart_type": parse_result["chart_type"],
        "brief": parse_result["brief"],
    }
```

### 3. LLM响应解析

系统解析LLM返回的JSON响应：

**成功响应：**
```json
{
    "success": true,
    "sql": "SELECT * FROM users LIMIT 1000",
    "tables": ["users"],
    "chart-type": "table",
    "brief": "用户列表查询"
}
```

**失败响应：**
```json
{
    "success": false,
    "message": "无法根据提供的表结构生成所需的SQL"
}
```

### 4. SQL验证

`sql_validator.py`中的安全验证：

```python
def validate_sql(sql):
    # 检查危险操作
    dangerous_patterns = [
        r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b',
        r';\s*\w',  # 多语句
        r'--',      # SQL注释
        r'/\*',     # 块注释
        r'\b(EXEC|EXECUTE|xp_|sp_)\b',  # 存储过程
    ]

    # 必须以SELECT开头
    if not sql.upper().startswith('SELECT'):
        return False, "查询必须以SELECT开头"

    # 括号匹配检查
    if sql.count('(') != sql.count(')'):
        return False, "括号不匹配"
```

## API接口

### POST /api/v1/chat/generate-sql

根据自然语言问题生成SQL。

**请求：**
```json
{
    "question": "查询所有用户信息",
    "datasource_id": 1
}
```

**响应：**
```json
{
    "code": 200,
    "message": "SQL generated successfully",
    "data": {
        "sql": "SELECT * FROM users LIMIT 1000",
        "is_valid": true,
        "error": "",
        "formatted_sql": "SELECT *\nFROM users\nLIMIT 1000",
        "tables": ["users"],
        "chart_type": "table",
        "brief": "用户列表查询"
    }
}
```

### POST /api/v1/chat/execute-sql

生成并执行SQL。

**请求：**
```json
{
    "question": "查询用户数量",
    "datasource_id": 1
}
```

**响应：**
```json
{
    "code": 200,
    "message": "Query executed successfully",
    "data": {
        "sql": "SELECT COUNT(*) FROM users LIMIT 1000",
        "error": "",
        "result": {
            "columns": ["count"],
            "rows": [[100]],
            "row_count": 1
        },
        "tables": ["users"],
        "chart_type": "table"
    }
}
```

### POST /api/v1/chat/validate-sql

验证SQL但不执行。

**请求：**
```json
{
    "question": "SELECT * FROM users"
}
```

**响应：**
```json
{
    "code": 200,
    "message": "SQL validation completed",
    "data": {
        "is_valid": true,
        "error": ""
    }
}
```

### POST /api/v1/chat/format-sql

格式化SQL语句。

**请求：**
```json
{
    "question": "SELECT * FROM users WHERE id = 1",
    "datasource_id": 1
}
```

**响应：**
```json
{
    "code": 200,
    "message": "SQL formatted successfully",
    "data": {
        "original_sql": "SELECT * FROM users WHERE id = 1",
        "formatted_sql": "SELECT *\nFROM users\nWHERE id = 1",
        "db_type": "pg"
    }
}
```

## 数据库Schema支持

### PostgreSQL

Schema查询语句：
```sql
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
```

### MySQL

Schema查询语句：
```sql
SHOW TABLES
SELECT TABLE_COMMENT FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
DESCRIBE `{table_name}`
```

## 图表类型选择

根据SQLBot规则，系统推荐以下图表类型：

| 图表类型 | 使用场景 | SQL要求 |
|----------|----------|---------|
| table | 原始数据展示 | 任意SELECT |
| column | 分类对比 | 维度 + 至少一个指标 |
| bar | 分类对比（水平） | 维度 + 至少一个指标 |
| line | 时间趋势 | 时间维度 + 指标 |
| pie | 占比展示 | 一个分类 + 一个指标 |

## 错误处理

### 生成错误

| 错误 | 原因 | 处理方式 |
|------|------|----------|
| `Datasource not found` | 无效的datasource_id | 返回错误，不重试 |
| `LLM call failed` | API/网络错误 | 重试 |
| `JSON解析失败` | LLM响应格式问题 | 带错误上下文重试 |
| `Only SELECT queries allowed` | 安全验证失败 | 返回验证错误 |

### 执行错误

| 错误 | 原因 | 处理方式 |
|------|------|----------|
| `Connection failed` | 数据库不可达 | 返回连接错误 |
| `SQL execution failed` | 语法/运行时错误 | 返回错误信息 |

## 安全措施

1. **SQL注入防护**
   - 仅允许SELECT查询
   - 禁止多语句
   - 禁止注释（-- 或 /* */）
   - 禁止存储过程

2. **数据访问控制**
   - 数据源配置加密存储
   - 连接凭证安全存储
   - 强制行数限制（默认1000）

3. **输入验证**
   - 问题长度限制
   - 数据源归属验证
   - 会话管理

## 重试机制

`generate_sql_with_retry()` 方法实现自动重试：

```python
result = generate_sql(question, datasource_id, session)
retry_count = 0
while not result["is_valid"] and retry_count < max_retries:
    # 在提示词中包含之前的错误
    result = generate_sql(
        question=question,
        datasource_id=datasource_id,
        session=session,
        custom_prompt=f"请注意：你之前生成的SQL有误，错误原因：{error_msg}"
    )
    retry_count += 1
```

## 关键实现决策

| 决策 | 理由 |
|------|------|
| M-Schema格式 | 遵循SQLBot约定，LLM友好 |
| 1000行限制 | 防止过度数据检索，平衡性能和功能 |
| JSON响应解析 | SQLBot结构化格式便于错误处理 |
| 带错误上下文重试 | 帮助LLM在后续尝试中纠正错误 |
| 图表类型推荐 | 使前端能够渲染适当的可视化 |

## 文件结构

```
src/
├── chat/
│   ├── api/
│   │   └── chat.py              # API端点
│   ├── service/
│   │   └── sql_generator.py     # SQL生成服务
│   ├── utils/
│   │   └── sql_validator.py      # SQL验证工具
│   ├── models/
│   │   └── conversation.py       # 会话模型
│   └── schemas.py                # Pydantic schemas
├── templates/
│   └── sql_gen_prompt.py         # SQL生成提示词
├── llm/
│   ├── base.py                   # 基础LLM工具
│   ├── openai.py                 # OpenAI实现
│   ├── ollama.py                 # Ollama实现
│   └── service.py                # LLM工厂
└── datasource/
    ├── db/
    │   └── db.py                 # 数据库操作
    └── crud/
        └── crud_datasource.py    # 数据源CRUD
```

## 代码示例

**SQLGenerator服务：**
```python
class SQLGenerator:
    def __init__(self, llm=None):
        self.llm = llm or create_llm()

    def generate_sql(self, question, datasource_id, session, ...):
        # 1. 获取数据源并解密配置
        datasource = crud_datasource.get_datasource_by_id(session, datasource_id)
        config = decrypt_conf(datasource.configuration)

        # 2. 获取数据库结构信息
        schema_info = self._get_schema(session, datasource, config, db_type)

        # 3. 使用SQLBot模板构建提示词
        system_prompt, user_prompt = build_sql_generation_prompt(...)

        # 4. 调用LLM
        messages = build_chat_messages(system_prompt, user_prompt)
        raw_response = self.llm.chat(messages)

        # 5. 解析和验证
        parse_result = parse_llm_sql_response(raw_response)
        sql = extract_sql(parse_result.get("sql", ""))
        is_valid, error_msg = validate_sql(sql)

        return {"sql": sql, "is_valid": is_valid, ...}
```

**API端点：**
```python
@router.post("/generate-sql")
def generate_sql(request: ChatRequest, session: Session = Depends(get_session)):
    generator = SQLGenerator()
    result = generator.generate_sql(
        question=request.question,
        datasource_id=request.datasource_id,
        session=session,
    )
    if not result["is_valid"]:
        return success_response(data=result, message="SQL generation failed")
    return success_response(data=result, message="SQL generated successfully")
```

## 测试

### 手动测试

```bash
# 生成SQL
curl -X POST http://localhost:8000/api/v1/chat/generate-sql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "查询所有用户", "datasource_id": 1}'

# 执行SQL
curl -X POST http://localhost:8000/api/v1/chat/execute-sql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question": "查询用户数量", "datasource_id": 1}'
```

## 参考资料

- SQLBot实现：`/Users/tanghaoyu/develop/git-repo/opensource/SQLBot-main/backend/apps/chat/task/llm.py`
- SQLBot模板：`/Users/tanghaoyu/develop/git-repo/opensource/SQLBot-main/backend/templates/template.yaml`
- SQLBot API路由：`/Users/tanghaoyu/develop/git-repo/opensource/SQLBot-main/backend/apps/chat/api/chat.py`
