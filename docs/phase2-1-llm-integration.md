# Phase 2.1 LLM 集成 (LangChain)

## 概述

本模块使用 LangChain 框架实现 LLM 接口抽象，支持多种 LLM 提供者：

- OpenAI API（GPT-4、GPT-4o-mini 等）
- vLLM（OpenAI 兼容 API）
- Ollama（本地部署，通过 OpenAI 兼容 API）

---

## 目录结构

```
src/
├── llm/                          # LLM 模块
│   ├── __init__.py
│   ├── base.py                  # 消息格式转换
│   ├── openai.py               # OpenAI 实现
│   ├── ollama.py               # Ollama 实现
│   └── service.py               # 服务工厂
├── templates/                    # Prompt 模板
│   ├── __init__.py
│   └── sql_gen_prompt.py       # SQL 生成模板
└── chat/                        # 对话模块
    ├── __init__.py
    ├── models/
    │   ├── __init__.py
    │   └── conversation.py      # 对话模型
    └── schemas.py               # 对话 Schema
```

---

## 实现逻辑详解

### 1. LangChain 消息格式 (`src/llm/base.py`)

LangChain 使用 `BaseMessage` 对象而非字典：

```python
from langchain_core.messages import HumanMessage, SystemMessage

# LangChain 消息格式
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Hello!"),
]
```

提供的辅助函数：

```python
from src.llm.base import get_langchain_messages, parse_history

# 转换 prompts 为 LangChain 消息
messages = get_langchain_messages(
    system_prompt="You are a helpful assistant.",
    user_prompt="Hello!",
    history=[{"role": "user", "content": "Hi"}]  # 可选历史
)
```

---

### 2. OpenAI 实现 (`src/llm/openai.py`)

使用 LangChain 的 `ChatOpenAI`：

```python
from langchain_openai import ChatOpenAI
from src.llm.openai import OpenAILLM

# 创建 LLM 实例
llm = OpenAILLM(
    model="gpt-4o-mini",
    api_key="sk-...",
    base_url="https://api.openai.com/v1",
    temperature=0,
)

# 调用
response = llm.chat(messages)
# 或
response = llm.invoke("Hello!")
```

**支持的参数：**
| 参数 | 说明 |
|------|------|
| `temperature` | 采样温度（0-2） |
| `max_tokens` | 最大 token 数 |
| `top_p` | Top-p 采样 |
| `timeout` | 请求超时（秒） |

---

### 3. Ollama 实现 (`src/llm/ollama.py`)

使用 LangChain 的 `ChatOpenAI` 连接 Ollama（Ollama 提供 OpenAI 兼容 API）：

```python
from src.llm.ollama import OllamaLLM

# 创建 LLM 实例
llm = OllamaLLM(
    model="qwen2.5",
    base_url="http://localhost:11434",
    temperature=0,
)

# 调用方式与 OpenAI 相同
response = llm.chat(messages)
```

**为什么用 ChatOpenAI 连接 Ollama：**
- Ollama 提供 `/v1/chat/completions` 兼容端点
- 使用 `ChatOpenAI` 可以无缝切换 provider
- 无需额外安装 `langchain-ollama`

---

### 4. LLM 服务工厂 (`src/llm/service.py`)

统一创建 LLM 实例：

```python
from src.llm.service import create_llm, get_default_llm, build_chat_messages

# 使用配置文件中的默认配置
llm = create_llm()

# 指定 provider
llm = create_llm(provider="ollama", model="qwen2.5:7b")

# 使用默认实例（单例）
llm = get_default_llm()

# 构建消息
messages = build_chat_messages(
    system_prompt="You are an expert...",
    user_prompt="How many users?",
    history=None
)
```

**配置项（`.env`）：**

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5
```

---

### 5. Prompt 模板 (`src/templates/sql_gen_prompt.py`)

构建 SQL 生成的 Prompt：

```python
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info

# 构建 Schema 描述
schema = build_schema_info([
    {
        "name": "users",
        "comment": "User accounts",
        "fields": [
            {"name": "id", "type": "bigint", "comment": "Primary key"},
            {"name": "name", "type": "varchar(255)", "comment": "User name"},
            {"name": "created_at", "type": "timestamp", "comment": "Creation time"},
        ]
    }
])

# 构建完整 Prompt
system_prompt, user_prompt = build_sql_generation_prompt(
    question="How many users were created today?",
    database_type="pg",
    schema_info=schema,
)

print(system_prompt)
print(user_prompt)
```

**输出示例：**

```
System:
You are an expert SQL generator...

Table: users
Description: User accounts
Fields:
  - id: bigint (Primary key)
  - name: varchar(255) (User name)
  ...

User:
Question: How many users were created today?
```

---

## 使用示例

### 1. 基本调用

```python
from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info

# 创建 LLM
llm = create_llm()

# 构建消息
messages = build_chat_messages(
    system_prompt="You are a helpful assistant.",
    user_prompt="What is 2+2?",
)

# 调用
response = llm.chat(messages)
print(response)
```

### 2. 生成 SQL

```python
from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info

llm = create_llm()

# Schema
schema = build_schema_info([
    {
        "name": "users",
        "comment": "User accounts",
        "fields": [
            {"name": "id", "type": "bigint", "comment": "Primary key"},
            {"name": "name", "type": "varchar(255)", "comment": "User name"},
            {"name": "created_at", "type": "timestamp", "comment": "Creation time"},
        ]
    }
])

# 构建 Prompt
system_prompt, user_prompt = build_sql_generation_prompt(
    question="How many users were created today?",
    database_type="pg",
    schema_info=schema,
)

# 构建消息并调用
messages = build_chat_messages(system_prompt, user_prompt)
sql = llm.chat(messages)
print(sql)  # SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE;
```

### 3. 结构化输出

```python
response_format = {
    "type": "json_object",
    "schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string"},
            "explanation": {"type": "string"}
        }
    }
}

result = llm.chat_with_structured_output(messages, response_format)
# result = {"sql": "SELECT ...", "explanation": "..."}
```

---

## 对话模型 (`src/chat/models/conversation.py`)

```python
class Conversation(SQLModel, table=True):
    """对话会话"""
    id: int
    user_id: int
    datasource_id: int
    title: str
    status: int
    create_time: int
    update_time: int

class Message(SQLModel, table=True):
    """对话消息"""
    id: int
    conversation_id: int
    role: str  # user / assistant / system
    content: str
    sql_query: Optional[str] = None
    query_result: Optional[dict] = None
    create_time: int
```

---

## 配置说明

### Ollama 本地部署

```bash
# 安装 Ollama (macOS)
brew install ollama

# 启动服务
ollama serve

# 拉取模型
ollama pull qwen2.5
# 或
ollama pull deepseek-r1
```

### 环境变量

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5
```

---

## 验证

### 测试 LLM 模块

```bash
python3 -c "
from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info

llm = create_llm()
print('LLM created:', type(llm).__name__)

schema = build_schema_info([{'name': 'test', 'fields': []}])
print('Schema built:', schema[:50])

messages = build_chat_messages('You are helpful.', 'Hello!')
print('Messages:', messages)
"
```

---

## LLM 模块测试

### 1. 测试 LLM 连接

```bash
python3 -c "
from src.llm.service import create_llm

llm = create_llm()
print('LLM type:', type(llm).__name__)
print('Model:', llm.model)

# 测试简单调用
response = llm.invoke('Hello, who are you?')
print('Response:', response)
"
```

### 2. 测试 Chat 接口

```bash
python3 -c "
from src.llm.service import create_llm, build_chat_messages

llm = create_llm()

# 构建消息
messages = build_chat_messages(
    system_prompt='You are a helpful assistant.',
    user_prompt='What is 2 + 2?'
)

# 调用
response = llm.chat(messages)
print('AI Response:', response)
"
```

### 3. 测试 SQL 生成

```bash
python3 -c "
from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info

llm = create_llm()

# 构建 Schema
schema = build_schema_info([
    {
        'name': 'users',
        'comment': 'User accounts table',
        'fields': [
            {'name': 'id', 'type': 'bigint', 'comment': 'Primary key'},
            {'name': 'name', 'type': 'varchar(255)', 'comment': 'User name'},
            {'name': 'email', 'type': 'varchar(255)', 'comment': 'Email'},
            {'name': 'created_at', 'type': 'timestamp', 'comment': 'Creation time'},
        ]
    }
])

# 构建 Prompt
system_prompt, user_prompt = build_sql_generation_prompt(
    question='How many users are there?',
    database_type='pg',
    schema_info=schema,
)

# 构建消息并调用
messages = build_chat_messages(system_prompt, user_prompt)
sql = llm.chat(messages)
print('Generated SQL:', sql)
"
```

### 4. 完整对话测试

```python
# 创建测试文件: tests/test_llm.py

import pytest
from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import build_sql_generation_prompt, build_schema_info


def test_llm_basic():
    """测试 LLM 基本调用"""
    llm = create_llm()
    response = llm.invoke("Say 'Hello'")
    assert isinstance(response, str)
    assert len(response) > 0


def test_llm_chat():
    """测试 chat 接口"""
    llm = create_llm()
    messages = build_chat_messages(
        system_prompt="You are a helpful assistant.",
        user_prompt="What is Python?"
    )
    response = llm.chat(messages)
    assert isinstance(response, str)
    assert "python" in response.lower() or len(response) > 0


def test_sql_generation():
    """测试 SQL 生成"""
    llm = create_llm()

    schema = build_schema_info([
        {
            "name": "users",
            "comment": "User table",
            "fields": [
                {"name": "id", "type": "bigint", "comment": "PK"},
                {"name": "name", "type": "varchar(255)", "comment": "Name"},
            ]
        }
    ])

    system_prompt, user_prompt = build_sql_generation_prompt(
        question="Count all users",
        database_type="pg",
        schema_info=schema,
    )

    messages = build_chat_messages(system_prompt, user_prompt)
    sql = llm.chat(messages)

    # 验证返回的是 SQL
    assert "SELECT" in sql.upper()
    assert "COUNT" in sql.upper() or "FROM" in sql.upper()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])

    # 或直接运行
    # python3 tests/test_llm.py
```

### 预期输出

```
======================== test session starts =========================
collected 3 items

tests/test_llm.py::test_llm_basic PASSED                      [ 33%]
tests/test_llm.py::test_llm_chat PASSED                       [ 66%]
tests/test_llm.py::test_sql_generation PASSED                 [100%]

======================== 3 passed in 5.23s =========================
```

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `Connection refused` | LLM 服务未启动 | 启动 Ollama: `ollama serve` |
| `Authentication Error` | API Key 错误 | 检查 `.env` 中的配置 |
| `Model not found` | 模型未下载 | 拉取模型: `ollama pull qwen2.5` |
| `timeout` | 请求超时 | 增加 timeout 或检查网络 |

---

## 后续开发

Phase 2.1 完成后的开发检查清单：

- [x] LLM 接口抽象（支持 OpenAI / vLLM / Ollama）
- [x] Prompt 模板设计
- [x] LLM 调用封装（LangChain）

下一阶段（Phase 2.2）将实现自然语言 → SQL 生成功能。
