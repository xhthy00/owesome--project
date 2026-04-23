# awesome-project 多 Agent / AWEL 改造落地计划

> 参考对象：`DB-GPT`（`packages/dbgpt-core/src/dbgpt/agent/`）
> 配套文档：`docs/agent_planning_implementation.md`（DB-GPT 原理分析）
> 本文档只讲"我们怎么做"，不重复讲 DB-GPT 原理。

---

## 0. 四项已决策的前置项

| 决策项 | 结论 |
|---|---|
| 依赖方案 | **方案 B：精简自实现**。不引入 `dbgpt-*` pip 依赖，按需复刻 DB-GPT 核心类（约 1500~2000 行代码） |
| Agent 编排 | **固定线性 DAG**：`Planner → DataAnalyst → Charter → Summarizer`；不做分支 / 并行（留作后续扩展） |
| 接口策略 | **单入口统一**：只保留 `POST /api/v1/chat/chat-stream`，通过 `agent_mode` 字段路由；SSE 事件**只增不替**，兼容旧前端 |
| 文档 | 独立写在本文件；不修改 `agent_planning_implementation.md`（它是原理分析） |

---

## 1. 目标与非目标

### 1.1 目标

- 引入 DB-GPT 风格的"Agent + Action + AWEL DAG + GptsMemory"四件套。
- 把现有线性 `SQLGenerator` 流水线升级为多 Agent 协作流水线，**支持复杂问题分解执行**。
- 提供统一的 SSE 事件协议，前端可可视化每个 Agent 的思考 / 执行 / 观察过程。
- 保证旧接口 / 旧前端兼容（通过 `agent_mode=single` 回退）。

### 1.2 目标（追加：Tool/Skill 体系）

- 引入 DB-GPT 风格的 **Tool/Resource 体系**：`BaseTool` / `FunctionTool` / `@tool` 装饰器 / `ToolPack`。
- Agent 可以"装备"工具集，由 LLM 在运行时自主选择并调用工具（对应 DB-GPT 的 `ToolAction` + `ToolAssistantAgent`）。
- 提供一批内置工具（schema 查询、计算、Embedding 检索、最近问题等），可被任一 Agent 引用。
- 工具调用事件全程通过 SSE 流式可观测（`tool_call` / `tool_result`）。

### 1.3 非目标（本轮不做）

- 多角色并行 / 条件分支 DAG（留作后续）。
- 向量化长期记忆（等 `MVP_PLAN.md` Phase 4 Embedding 做完后接）。
- 动态 Agent 装配（配置化 / 前端拖拽编排）。
- 多租户 / 权限隔离 Agent。
- **应用级 Skill 模板**（DB-GPT `/skills/walmart-sales-analyzer` 这种打包好的"场景包"）：作为 Phase G 候选，本轮不实现。
- **MCP（Model Context Protocol）协议接入**：本轮不实现，留作 Phase H。
- **AutoGPT 插件兼容**：不实现。

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ POST /api/v1/chat/chat-stream  ← 统一入口（agent_mode: single | team）          │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┴───────────────────────────┐
          ▼ agent_mode=single                                      ▼ agent_mode=team
   ┌──────────────┐                                       ┌───────────────────────┐
   │ SQLGenerator │ (legacy)                              │    ChatAwelTeam       │
   └──────────────┘                                       │ (AWELBaseManager)     │
                                                          └──────────┬────────────┘
                                                                     │
                        ┌──────────────┬──────────────┬──────────────┼──────────────┐
                        ▼              ▼              ▼              ▼              ▼
                     Planner     DataAnalyst      Charter      Summarizer   [ToolAgent*]
                   (PlanAction) (QuerySqlAction) (ChartAction) (SummaryAct) (ToolAction)
                        │              │              │              │              │
                        └──────────────┴──────────────┴──────────────┴──────────────┘
                                       │                        │
                                       ▼                        ▼
                      ┌────────────────────────────┐  ┌────────────────────┐
                      │  ResourcePack (per-agent)  │  │  ToolPack(registry)│
                      │  ├─ DatasourceResource     │  │  ├─ schema_tool    │
                      │  └─ ToolPack               │──┤  ├─ calc_tool      │
                      └────────────────────────────┘  │  ├─ embedding_tool │
                                                      │  └─ ... (@tool)    │
                                                      └────────────────────┘
                                       │
                                       ▼
                              GptsMemory(plans)  AgentMemory(short-term)
                                       │
                                       ▼
                        gpts_plan / gpts_message / tool_registry(DB)

* ToolAgent 为 Phase F 可选节点；主 4 Agent 也能通过 ResourcePack 装备工具。
```

关键对齐：

| DB-GPT | 本项目位置 |
|---|---|
| `ConversableAgent` | `src/agent/core/base_agent.py` |
| `ManagerAgent` / `AWELBaseManager` | `src/agent/core/base_team.py` / `src/agent/core/awel/team_awel_layout.py` |
| `WrappedAgentOperator` | `src/agent/core/awel/agent_operator.py` |
| `AgentGenerateContext` | `src/agent/core/agent.py::AgentGenerateContext` |
| `Action` / `ActionOutput` | `src/agent/core/action/base.py` |
| `PlannerAgent` / `DataScientistAgent` / `DashboardAssistantAgent` / `SummaryAssistantAgent` | `src/agent/expand/` 下同名（本地名：`PlannerAgent` / `DataAnalystAgent` / `CharterAgent` / `SummarizerAgent`） |
| `GptsMemory` / `GptsPlan` | `src/agent/core/memory/gpts_memory.py` + 表 `gpts_plan` |
| `DBResource` | `src/agent/resource/datasource_resource.py` |
| `Resource` / `ResourcePack` | `src/agent/resource/base.py` / `pack.py` |
| `BaseTool` / `FunctionTool` / `@tool` / `ToolPack` | `src/agent/resource/tool/base.py` / `pack.py` |
| `ToolAction` / `ToolAssistantAgent` | `src/agent/core/action/tool_action.py` / `src/agent/expand/tool_agent.py` |
| 内置 tools（`expand/resources/dbgpt_tool.py` 等） | `src/agent/expand/tools/` 下各模块 |

---

## 3. 目录结构（全部新增，不动 `src/chat/`）

```
src/agent/
├── __init__.py
├── core/
│   ├── agent.py                 # Agent 抽象 + AgentMessage + AgentGenerateContext + AgentReviewInfo
│   ├── base_agent.py            # ConversableAgent：generate_reply (thinking/review/act/verify/retry)
│   ├── base_team.py             # ManagerAgent 基类
│   ├── profile.py               # ProfileConfig (name/role/goal/constraints/desc)  *砍掉 DynConfig 国际化
│   ├── action/
│   │   ├── base.py              # Action 抽象 + ActionOutput
│   │   ├── plan_action.py       # 解析 Planner 输出的规划 JSON → [GptsPlan]
│   │   ├── query_sql_action.py  # 调用 datasource.db 执行 SQL，返回 observation
│   │   ├── chart_action.py      # 根据数据列生成 echarts 配置
│   │   └── summary_action.py    # 整理多步结果为最终回答
│   ├── memory/
│   │   ├── agent_memory.py      # 近 N 轮短期记忆
│   │   └── gpts_memory.py       # 计划 + 跨 Agent 消息持久化
│   └── awel/
│       ├── dag.py               # MapOperator 极简线性 DAG
│       ├── agent_operator.py    # WrappedAgentOperator
│       └── team_awel_layout.py  # ChatAwelTeam(AWELBaseManager)
├── expand/
│   ├── planner_agent.py
│   ├── data_analyst_agent.py    # 对齐 DataScientistAgent：带 correctness_check 自愈
│   ├── charter_agent.py
│   ├── summarizer_agent.py
│   ├── tool_agent.py            # 对齐 ToolAssistantAgent：LLM 自主选工具并调用
│   └── tools/                   # 内置工具集（@tool 装饰的函数）
│       ├── __init__.py          # 自动注册：导出 DEFAULT_TOOLS
│       ├── datasource_tools.py  #   list_tables / describe_table / sample_rows
│       ├── calc_tools.py        #   calculate（表达式求值）
│       ├── embedding_tools.py   #   find_related_tables / find_related_datasources
│       └── history_tools.py     #   recent_questions
├── resource/
│   ├── base.py                  # Resource 抽象 + ResourceType + ResourceParameters
│   ├── pack.py                  # ResourcePack（工具/数据库等资源的组合容器）
│   ├── manage.py                # ResourceManager：按 name 注册/查找工具
│   ├── datasource_resource.py   # 包装现有 crud_datasource + decrypt_conf + db_execute_sql
│   └── tool/
│       ├── base.py              # BaseTool / FunctionTool / ToolParameter / @tool 装饰器
│       ├── pack.py              # ToolPack（继承 ResourcePack），提供 execute / async_execute
│       └── exceptions.py        # ToolNotFoundException / ToolExecutionException
└── util/
    ├── json_parser.py           # 容错 JSON 解析（支持 ```json 代码块 / json5 / 首尾截取）
    ├── function_utils.py        # inspect 函数签名 → ToolParameter（供 @tool 使用）
    └── react_parser.py          # 保留，未来 ReAct 风格输出用
```

---

## 4. 关键数据结构

### 4.1 AgentMessage / AgentGenerateContext / ActionOutput

```python
# src/agent/core/agent.py
@dataclass
class AgentReviewInfo:
    approve: bool = True
    comments: Optional[str] = None


@dataclass
class AgentMessage:
    content: Optional[str] = None
    current_goal: Optional[str] = None
    action_report: Optional["ActionOutput"] = None
    review_info: Optional[AgentReviewInfo] = None
    context: Dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    role: str = "user"                    # user / assistant / system
    sender: Optional[str] = None
    model_name: Optional[str] = None

    @property
    def success(self) -> bool:
        return bool(self.action_report and self.action_report.is_exe_success)


@dataclass
class AgentGenerateContext:
    """DAG 节点之间传递的全部状态。对齐 DB-GPT 同名类。"""
    message: Optional[AgentMessage]
    sender: "Agent"
    reviewer: Optional["Agent"] = None
    memory: Optional["GptsMemory"] = None
    agent_context: Optional["AgentContext"] = None
    rely_messages: List[AgentMessage] = field(default_factory=list)
    last_speaker: Optional["Agent"] = None
    llm_client: Any = None
```

```python
# src/agent/core/action/base.py
class ActionOutput(BaseModel):
    content: str = ""
    is_exe_success: bool = True
    view: Optional[str] = None                # 前端展示（SQL / 表格 / 图表 JSON）
    action: Optional[str] = None              # 动作名
    thoughts: Optional[str] = None            # LLM 思考文本
    phase: Optional[str] = None               # 阶段描述
    observations: Optional[str] = None        # 执行后观察
    next_speakers: Optional[List[str]] = None
    terminate: bool = False
    have_retry: bool = True
    resource_value: Optional[str] = None      # 命中资源值（如 datasource_id）
    extra: Dict[str, Any] = Field(default_factory=dict)
```

### 4.2 GptsPlan（计划表）

```python
# src/agent/core/memory/gpts_memory.py
@dataclass
class GptsPlan:
    conv_id: str
    sub_task_num: int
    sub_task_title: str
    sub_task_content: str
    sub_task_agent: str              # DataAnalyst / Charter / Summarizer ...
    rely: str = ""                   # e.g. "1,2"
    state: str = "TODO"              # TODO | RUNNING | COMPLETE | FAILED | RETRYING
    retry_times: int = 0
    result: Optional[str] = None
```

---

## 5. 主循环（ConversableAgent.generate_reply）

**对齐 DB-GPT `base_agent.py`，精简到 ~120 行。**

```python
class ConversableAgent(BaseAgent):
    profile: ProfileConfig
    llm_config: LlmConfig
    actions: List[Action] = []
    max_retry_count: int = 3

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: "Agent",
        reviewer: Optional["Agent"] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> AgentMessage:
        reply_message = self._init_reply_message(received_message, rely_messages)
        fail_reason: Optional[str] = None

        for retry in range(self.max_retry_count):
            # 1. thinking
            messages = self._build_messages(received_message, rely_messages,
                                            reply_message, fail_reason)
            llm_reply, model = await self.thinking(messages, sender)
            reply_message.content = llm_reply
            reply_message.model_name = model

            # 2. review
            approve, comments = await self.review(llm_reply, self)
            reply_message.review_info = AgentReviewInfo(approve=approve, comments=comments)
            if not approve:
                fail_reason = comments
                continue

            # 3. act
            action_out = await self.act(reply_message, sender, reviewer, **kwargs)
            reply_message.action_report = action_out

            # 4. verify (子类 correctness_check)
            ok, reason = await self.verify(reply_message, sender, reviewer)
            if ok:
                await self.write_memories(received_message, reply_message, action_out)
                return reply_message

            fail_reason = reason

        # 耗尽重试
        reply_message.action_report = reply_message.action_report or ActionOutput(
            is_exe_success=False, content=fail_reason or "Max retry reached",
            have_retry=False,
        )
        return reply_message
```

子类只需实现 `_init_reply_message`（设置 context/Prompt 变量）和 `correctness_check`。

---

## 6. 四个专业 Agent 定义

### 6.1 PlannerAgent

```python
# src/agent/expand/planner_agent.py
class PlannerAgent(ConversableAgent):
    profile = ProfileConfig(
        name="Planner",
        role="Planner",
        goal="理解用户目标，基于可用 Agent 能力与数据源 schema，拆解为可独立执行的子任务。",
        constraints=[
            "每一步都应直接推进用户目标",
            "关注任务依赖和逻辑顺序",
            "合并顺序依赖的连续相同步骤",
            "子任务必须指定执行者：DataAnalyst | Charter | Summarizer",
            "只用严格 JSON 输出，不要多余文本",
        ],
    )
    actions = [PlanAction()]

    async def correctness_check(self, msg) -> Tuple[bool, Optional[str]]:
        out = msg.action_report
        if not out or not out.is_exe_success:
            return False, "规划解析失败，请重新输出严格 JSON"
        plans = json.loads(out.content)
        if not plans:
            return False, "至少需要一个子任务"
        allowed = {"DataAnalyst", "Charter", "Summarizer"}
        for p in plans:
            if p.get("sub_task_agent") not in allowed:
                return False, f"未知执行者 {p.get('sub_task_agent')}，只允许 {allowed}"
        return True, None
```

**输出 JSON 示例**：

```json
[
  {"sub_task_num": 1, "sub_task_title": "查询 Q2 销量", "sub_task_content": "...",
   "sub_task_agent": "DataAnalyst", "rely": ""},
  {"sub_task_num": 2, "sub_task_title": "查询 Q3 销量", "sub_task_content": "...",
   "sub_task_agent": "DataAnalyst", "rely": ""},
  {"sub_task_num": 3, "sub_task_title": "对比图表",     "sub_task_content": "...",
   "sub_task_agent": "Charter",    "rely": "1,2"},
  {"sub_task_num": 4, "sub_task_title": "总结结论",    "sub_task_content": "...",
   "sub_task_agent": "Summarizer", "rely": "1,2,3"}
]
```

### 6.2 DataAnalystAgent（对齐 DataScientistAgent）

```python
class DataAnalystAgent(ConversableAgent):
    profile = ProfileConfig(
        name="DataAnalyst",
        role="DataAnalyst",
        goal="基于数据源 schema 生成正确的 {{dialect}} SQL，执行并返回数据。",
        constraints=[
            "严格使用给定的表结构，不得虚构字段",
            "如需跨表，使用 JOIN；不得编造过滤值",
            "若历史消息中有报错，阅读并修复，不要重复错误",
            "输出 JSON：{\"sql\": \"...\", \"brief\": \"...\"}",
        ],
    )
    actions = [QuerySqlAction()]
    max_retry_count = 5

    def _init_reply_message(self, received, rely_messages=None):
        msg = super()._init_reply_message(received, rely_messages)
        msg.context = {
            "dialect": self.datasource.dialect,
            "schema": self.datasource.get_schema_text(),
        }
        return msg

    async def correctness_check(self, msg) -> Tuple[bool, Optional[str]]:
        out = msg.action_report
        if not out or not out.is_exe_success:
            return False, f"SQL 执行失败：{out.content if out else 'no output'}"
        data = json.loads(out.content)
        if not data.get("columns"):
            return False, "查询结果无列信息"
        return True, None
```

**QuerySqlAction** 内部直接调用现有 `src/datasource/db/db.py::execute_sql`，Prompt 复用 `src/templates/sql_gen_prompt.py::build_sql_generation_prompt`。

### 6.3 CharterAgent（对齐 DashboardAssistantAgent）

```python
class CharterAgent(ConversableAgent):
    profile = ProfileConfig(
        name="Charter",
        role="Charter",
        goal="基于 DataAnalyst 的数据列结构，选择合适的图表类型并给出 echarts 配置。",
        constraints=[
            "支持类型：table | column | bar | line | pie（与前端白名单对齐）",
            "xAxis / yAxis / seriesField 必须是数据列中实际存在的字段",
            "输出 JSON：{\"chart_type\": \"...\", \"chart_config\": {...}}",
        ],
    )
    actions = [ChartAction()]
```

### 6.4 SummarizerAgent

```python
class SummarizerAgent(ConversableAgent):
    profile = ProfileConfig(
        name="Summarizer",
        role="Summarizer",
        goal="整合规划、SQL、数据、图表，用中文回答用户原始问题。",
        constraints=["直接给出结论，不重复中间过程", "无法回答时明确说明"],
    )
    actions = [SummaryAction()]
```

### 6.5 ToolAgent（对齐 ToolAssistantAgent，Phase F 引入）

**用途**：当用户需求不走固定四步 DAG、或需要"工具箱式"自由调用（如辅助查 schema、计算数值、跑 embedding 检索）时，由 `ToolAgent` 循环"LLM 选工具 → 执行 → 观察"直到拿到答案。

```python
# src/agent/expand/tool_agent.py
class ToolAgent(ConversableAgent):
    profile = ProfileConfig(
        name="Toolsmith",
        role="ToolExpert",
        goal=(
            "阅读下方工具清单，理解每个工具的能力与参数，"
            "为达成用户目标选择最合适的工具，并按 JSON 格式输出调用。"
        ),
        constraints=[
            "仔细阅读工具参数定义，从用户目标中提取精确参数值",
            "严格按 JSON 格式输出：{\"thought\": \"...\", \"tool_name\": \"...\", \"args\": {...}}",
            "工具调用失败后读取 observation 再决策，不要重复同一错误",
            "任务达成后调用 terminate 工具结束循环",
        ],
        desc="可用工具清单：\n{{tool_infos}}",    # 由 ToolPack.render_prompt() 动态注入
    )
    actions = [ToolAction()]
    max_retry_count: int = 5       # 对齐 DB-GPT tool agent 的多步推理预算

    def _init_reply_message(self, received, rely_messages=None):
        msg = super()._init_reply_message(received, rely_messages)
        tool_pack = ToolPack.from_resource(self.resource)[0]
        msg.context = {"tool_infos": tool_pack.render_prompt(lang="zh")}
        return msg
```

**两种使用方式**：

1. **内嵌工具进主流程 Agent**（Phase F 主路径）：给 `DataAnalystAgent` / `CharterAgent` 传 `resource=ToolPack([schema_tool, find_related_tables])`，Agent 在自己的 `thinking` 阶段即可调用。
2. **作为 DAG 独立节点**：在 `ChatAwelTeam.agents` 中插入 `ToolAgent`，负责某些由工具完成的子任务（如"查一下 Q2 销售额最高的品类"）。

---

## 7. AWEL 极简实现

```python
# src/agent/core/awel/dag.py
class MapOperator:
    """线性 DAG 节点。对齐 dbgpt.core.awel.MapOperator 最小子集。"""

    def __init__(self, task_name: str = ""):
        self.task_name = task_name
        self._upstream: List[MapOperator] = []
        self._downstream: List[MapOperator] = []

    def __rshift__(self, other: "MapOperator") -> "MapOperator":
        self._downstream.append(other)
        other._upstream.append(self)
        return other

    async def map(self, ctx: AgentGenerateContext) -> AgentGenerateContext:
        raise NotImplementedError

    async def call(self, call_data: AgentGenerateContext) -> AgentGenerateContext:
        chain: List[MapOperator] = []
        cur = self
        while cur._upstream:
            cur = cur._upstream[0]
        while cur:
            chain.append(cur)
            cur = cur._downstream[0] if cur._downstream else None
        ctx = call_data
        for node in chain:
            ctx = await node.map(ctx)
        return ctx
```

```python
# src/agent/core/awel/agent_operator.py
class WrappedAgentOperator(MapOperator):
    def __init__(self, agent: Agent):
        super().__init__(task_name=agent.profile.role)
        self._agent = agent

    async def map(self, input_ctx: AgentGenerateContext) -> AgentGenerateContext:
        if not input_ctx.message:
            raise ValueError("empty message")

        input_message = copy.deepcopy(input_ctx.message)
        input_message.current_goal = f"[{self._agent.profile.role}]: {input_message.content or ''}"

        reply = await self._agent.generate_reply(
            received_message=input_message,
            sender=input_ctx.sender,
            reviewer=input_ctx.reviewer,
            rely_messages=input_ctx.rely_messages,
        )
        if not reply.success:
            raise AgentExecutionError(
                self._agent.profile.role, reply.action_report.content if reply.action_report else "unknown"
            )

        return dataclasses.replace(
            input_ctx,
            message=input_message,
            rely_messages=[*input_ctx.rely_messages, reply],
            last_speaker=self._agent,
        )
```

### 7.5 Tool 体系实现（Phase E 核心）

严格对齐 DB-GPT `agent/resource/tool/`，精简（去掉 i18n / AutoGPT 插件 / MCP）：

```python
# src/agent/resource/tool/base.py
DB_GPT_TOOL_IDENTIFIER = "awesome_tool"

class ToolParameter(BaseModel):
    name: str
    title: str
    type: str                             # "string" / "integer" / "boolean" / "number"
    description: str
    required: bool = True
    default: Optional[Any] = None


class BaseTool(Resource[ToolResourceParameters], ABC):
    @classmethod
    def type(cls) -> ResourceType: return ResourceType.Tool

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def args(self) -> Dict[str, ToolParameter]: ...

    async def get_prompt(self, *, lang="zh", **_) -> Tuple[str, None]:
        """返回供 LLM 使用的中文工具说明：
        calculate: 调用此工具与 calculate API 进行交互。用于表达式计算。
        参数: [{"name":"expression","type":"string","description":"表达式","required":true}]
        """
        parameters = [
            {"name": k, "type": v.type, "description": v.description, "required": v.required}
            for k, v in self.args.items()
        ]
        return (f"{self.name}：{self.description}\n参数：{json.dumps(parameters, ensure_ascii=False)}"), None


class FunctionTool(BaseTool):
    """把普通 Python 函数包装成 Tool。参数从类型注解自动解析。"""
    def __init__(self, name, func, description=None, args=None):
        self._name, self._func = name, func
        self._description = description or (func.__doc__ or "").strip()
        self._args = args or _parse_args_from_signature(func)
        self._is_async = asyncio.iscoroutinefunction(func)

    def execute(self, **kwargs):
        if self._is_async: raise ValueError("use async_execute")
        return self._func(**kwargs)

    async def async_execute(self, **kwargs):
        if self._is_async: return await self._func(**kwargs)
        return self._func(**kwargs)


def tool(*decorator_args, description=None, args=None):
    """@tool 装饰器：把 Python 函数声明为可被 Agent 调用的工具。

    用法：
        @tool(description="表达式计算")
        def calculate(expression: str) -> str:
            return str(eval(expression))
    """
    # 实现逻辑照搬 DB-GPT base.py:232-285，这里不展开
    ...
```

```python
# src/agent/resource/tool/pack.py
class ToolPack(ResourcePack):
    """工具集合容器：按 name 索引，可被 Agent 作为 resource 注入。"""
    def __init__(self, resources: List[Union[BaseTool, ToolFunc]], name="ToolPack"):
        tools = self._to_tools(resources)
        super().__init__(resources=tools, name=name)

    async def async_execute(self, *, resource_name: str, **kwargs):
        tool = self._resources.get(resource_name)
        if not tool: raise ToolNotFoundException(resource_name)
        arguments = {k: v for k, v in kwargs.items() if k in tool.args}
        return await tool.async_execute(**arguments)

    def render_prompt(self, lang="zh") -> str:
        """把所有工具的说明拼成 LLM 可读文本，供 Agent desc 里的 {{tool_infos}} 变量渲染。"""
        return "\n".join([tool.get_prompt(lang=lang)[0] for tool in self.sub_resources])
```

```python
# src/agent/core/action/tool_action.py
class ToolInput(BaseModel):
    tool_name: str
    args: dict = {}
    thought: str

class ToolAction(Action[ToolInput]):
    """LLM 自主选工具 → 调用 → 返回 observation。"""
    @property
    def resource_need(self) -> Optional[ResourceType]: return ResourceType.Tool

    @property
    def ai_out_schema(self) -> str:
        return json.dumps({
            "thought": "对使用工具的思考",
            "tool_name": "要调用的工具名",
            "args": {"arg1": "v1"},
        }, ensure_ascii=False)

    async def run(self, ai_message, resource=None, **kw) -> ActionOutput:
        try:
            param = self._input_convert(ai_message, ToolInput)
        except Exception:
            return ActionOutput(is_exe_success=False, content="工具调用 JSON 解析失败")

        tool_pack = ToolPack.from_resource(self.resource)[0]
        try:
            result = await tool_pack.async_execute(
                resource_name=param.tool_name, **param.args
            )
            terminate = tool_pack.is_terminal(param.tool_name)   # 命中 Terminate 工具就退出循环
            return ActionOutput(
                is_exe_success=True,
                content=str(result),
                observations=str(result),
                thoughts=param.thought,
                action=param.tool_name,
                terminate=terminate,
            )
        except Exception as e:
            return ActionOutput(is_exe_success=False, content=f"工具 {param.tool_name} 执行异常: {e}")
```

### 7.6 内置工具清单（Phase E 交付）

| 名称 | 位置 | 说明 | 目标调用方 |
|---|---|---|---|
| `list_tables(datasource_id)` | `tools/datasource_tools.py` | 列出某数据源所有表名 + 注释 | DataAnalyst / Planner |
| `describe_table(datasource_id, table_name)` | `tools/datasource_tools.py` | 输出表的完整字段结构 | DataAnalyst |
| `sample_rows(datasource_id, table_name, limit=5)` | `tools/datasource_tools.py` | 抽样数据，辅助 LLM 理解语义 | DataAnalyst |
| `calculate(expression)` | `tools/calc_tools.py` | 安全表达式求值（`asteval`） | Summarizer / ToolAgent |
| `find_related_tables(datasource_id, question, top_n=5)` | `tools/embedding_tools.py` | 语义搜索相关表（依赖 `MVP_PLAN.md` Phase 4） | Planner / DataAnalyst |
| `find_related_datasources(user_id, question, top_n=3)` | `tools/embedding_tools.py` | 语义搜索相关数据源 | Planner |
| `recent_questions(datasource_id, limit=10)` | `tools/history_tools.py` | 复用现有 `chat_crud.get_recent_questions` | Planner（做追问感知） |
| `terminate(final_answer)` | `tools/__init__.py` | 终止 ToolAgent 循环的特殊工具 | ToolAgent 专用 |

**每个工具都用 `@tool` 装饰**；`src/agent/expand/tools/__init__.py` 暴露 `DEFAULT_TOOLS: List[BaseTool]`，供 `ResourceManager` 启动时一次性注册。

示例：

```python
# src/agent/expand/tools/datasource_tools.py
from typing_extensions import Annotated, Doc
from src.agent.resource.tool.base import tool

@tool(description="列出数据源下所有表名和表注释")
def list_tables(
    datasource_id: Annotated[int, Doc("数据源 ID")],
) -> str:
    from src.datasource.crud import crud_datasource
    from src.common.core.database import get_db_session
    with get_db_session() as s:
        ds = crud_datasource.get_datasource_by_id(s, datasource_id)
        tables = crud_datasource.list_tables(s, datasource_id)
    return "\n".join(f"- {t.table_name}: {t.table_comment or ''}" for t in tables)
```

---

### 7.7 ChatAwelTeam（承接 AWEL）

```python
# src/agent/core/awel/team_awel_layout.py
class ChatAwelTeam(ManagerAgent):
    agents: List[Agent]

    def get_dag(self) -> MapOperator:
        nodes = [WrappedAgentOperator(a) for a in self.agents]
        for i in range(len(nodes) - 1):
            nodes[i] >> nodes[i + 1]
        return nodes[-1]

    async def act(self, message, sender, reviewer=None, **kw) -> ActionOutput:
        dag_tail = self.get_dag()
        start_ctx = AgentGenerateContext(
            message=message, sender=sender, reviewer=reviewer,
            memory=self.memory, agent_context=self.agent_context,
            llm_client=self.llm_client,
        )
        try:
            final_ctx = await dag_tail.call(call_data=start_ctx)
            last = final_ctx.rely_messages[-1]
            return ActionOutput(
                content=last.content,
                view=last.action_report.view if last.action_report else None,
                is_exe_success=True,
            )
        except Exception as e:
            logger.exception("team DAG failed")
            return ActionOutput(is_exe_success=False, content=str(e), have_retry=False)
```

---

## 8. 与现有代码的对接点

### 8.1 请求入参

```python
# src/chat/schemas.py
class ChatRequest(BaseModel):
    question: str
    datasource_id: int
    conversation_id: Optional[int] = None
    agent_mode: Literal["single", "team"] = "team"   # 新增；默认 team
```

### 8.2 `/chat-stream` 统一入口

```python
# src/chat/api/chat.py
@router.post("/chat-stream")
async def chat_stream(request: ChatRequest, current_user_id: int = 1):
    if request.agent_mode == "single":
        return _stream_single_agent(request, current_user_id)   # 现有实现原样
    return _stream_team(request, current_user_id)               # 新实现
```

### 8.3 Team 流式适配器

```python
async def _stream_team(request, user_id):
    queue = asyncio.Queue()

    def push(event, data): loop.call_soon_threadsafe(queue.put_nowait, (event, data))

    async def on_agent_event(ev: AgentEvent):
        # 在 ConversableAgent 各阶段 hook 里调用
        push(ev.type, ev.payload)

    async def run():
        team = build_chat_team(request, on_agent_event)     # 构造 4 Agent 固定 DAG
        ctx = AgentGenerateContext(
            message=AgentMessage(content=request.question, role="user"),
            sender=UserProxyAgent(),
            memory=build_gpts_memory(request.conversation_id),
        )
        out = await team.act(ctx.message, sender=ctx.sender)
        push("done", {"success": out.is_exe_success})
        queue.put_nowait(SENTINEL)

    asyncio.create_task(run())
    return StreamingResponse(sse_generator(queue), media_type="text/event-stream")
```

### 8.4 SSE 事件协议（向后兼容）

**保留的旧事件**：`step` / `reasoning` / `sql` / `result` / `error` / `done`

**新增事件**：

| event | data | 触发时机 |
|---|---|---|
| `plan` | `{"plans": [GptsPlan, ...]}` | Planner 产出初始计划 |
| `plan_update` | `{"sub_task_num": 1, "state": "COMPLETE", "result": "..."}` | 每个子任务完成/失败 |
| `agent_speak` | `{"role": "DataAnalyst", "thought": "...", "phase": "..."}` | 每个 Agent 的 thinking 完成 |
| `chart` | `{"chart_type": "bar", "chart_config": {...}}` | Charter 完成 |
| `summary` | `{"text": "..."}` | Summarizer 完成 |
| `tool_call` | `{"role": "DataAnalyst", "tool_name": "list_tables", "args": {...}, "thought": "..."}` | Agent 决定调用工具（`ToolAction.run` 进入前） |
| `tool_result` | `{"tool_name": "list_tables", "success": true, "content": "...", "elapsed_ms": 12}` | 工具执行完毕（成功/失败都发） |

旧前端只处理它认识的事件（`step/sql/result/...`），其余忽略，**零破坏**。

### 8.5 持久化接入

- 新建 CRUD `src/agent/core/memory/crud_gpts.py`（对应 `gpts_plan` / `gpts_message` 两张表）。
- 现有 `ConversationRecord` 不动，新增可选字段 `agent_mode VARCHAR(16) DEFAULT 'single'`。
- Alembic 迁移放 `alembic/versions/xxx_add_gpts_tables.py`。

---

## 9. 数据库迁移

```sql
CREATE TABLE gpts_plan (
    id BIGSERIAL PRIMARY KEY,
    conv_id VARCHAR(64) NOT NULL,
    sub_task_num INT NOT NULL,
    sub_task_title TEXT,
    sub_task_content TEXT NOT NULL,
    sub_task_agent VARCHAR(64),
    rely VARCHAR(255) DEFAULT '',
    state VARCHAR(32) DEFAULT 'TODO',
    retry_times INT DEFAULT 0,
    result TEXT,
    create_time TIMESTAMP DEFAULT NOW(),
    update_time TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_gpts_plan_conv ON gpts_plan(conv_id);

CREATE TABLE gpts_message (
    id BIGSERIAL PRIMARY KEY,
    conv_id VARCHAR(64) NOT NULL,
    sender VARCHAR(64) NOT NULL,
    receiver VARCHAR(64) NOT NULL,
    role VARCHAR(32),
    content TEXT,
    action_report JSONB,
    rounds INT DEFAULT 0,
    create_time TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_gpts_message_conv ON gpts_message(conv_id);

ALTER TABLE chat_conversation_record
    ADD COLUMN agent_mode VARCHAR(16) DEFAULT 'single';

-- 工具注册表：**Phase E 不启用**，Phase G 做 UI 管理时再启用
-- 本轮 Phase E 用 Python 硬编码的 DEFAULT_TOOLS + ResourceManager 内存注册中心
CREATE TABLE tool_registry (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    args_schema JSONB,                   -- [{name, type, description, required}...]
    handler VARCHAR(255) NOT NULL,       -- Python 导入路径："src.agent.expand.tools.calc_tools:calculate"
    enabled BOOLEAN DEFAULT TRUE,
    builtin BOOLEAN DEFAULT TRUE,
    create_time TIMESTAMP DEFAULT NOW(),
    update_time TIMESTAMP DEFAULT NOW()
);

-- 可选：工具调用审计（便于排查 LLM 工具误用）
CREATE TABLE tool_call_log (
    id BIGSERIAL PRIMARY KEY,
    conv_id VARCHAR(64),
    agent_role VARCHAR(64),
    tool_name VARCHAR(128),
    args JSONB,
    result TEXT,
    success BOOLEAN,
    elapsed_ms INT,
    create_time TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_tool_call_log_conv ON tool_call_log(conv_id);
```

**迁移时序**：

| 迁移文件 | 所属阶段 |
|---|---|
| `add_gpts_plan_tables.py`（`gpts_plan` + `gpts_message` + `chat_conversation_record.agent_mode`） | Phase C |
| `add_tool_call_log.py`（仅 `tool_call_log`） | Phase E |
| `add_tool_registry.py`（`tool_registry`） | Phase G，本轮不做 |

---

## 10. 分阶段里程碑

> 总工期 ~6.5 周。每阶段交付物独立可验证，**绝不跨阶段并行实现**。
>
> **里程碑关键决策（v3）**：工具最小内核必须随 Agent 内核一起交付（Phase A），因为 Phase B 的 DataAnalyst 就会装备 `ToolPack`，不能等到 Phase E。Phase E 只负责补齐其余工具 + 审计。

### Phase A · Agent 内核 + Tool 最小内核（第 1~1.5 周）

**Agent 核心交付**

- `src/agent/core/` 全部：`agent.py` / `base_agent.py` / `base_team.py` / `profile.py` / `action/base.py` / `memory/agent_memory.py`
- `util/json_parser.py`
- 一个 `EchoAgent` + `UserProxyAgent` 作为冒烟用例

**Tool 最小内核交付**（同期完成，不拆成独立 Phase）

- `src/agent/resource/base.py`（`Resource` / `ResourceType` / `ResourceParameters`）
- `src/agent/resource/pack.py`（`ResourcePack`）
- `src/agent/resource/tool/base.py`（`BaseTool` / `FunctionTool` / `ToolParameter` / `@tool`）
- `src/agent/resource/tool/pack.py`（`ToolPack` + `async_execute` + `render_prompt`）
- `src/agent/resource/tool/exceptions.py`
- `src/agent/util/function_utils.py`（从函数签名+注解 → `ToolParameter`）
- `src/agent/core/action/tool_action.py`（`ToolAction` + `ToolInput`）
- **2 个"必需"内置工具**（其余 5 个推迟到 Phase E）：
  - `src/agent/expand/tools/datasource_tools.py::list_tables`
  - `src/agent/expand/tools/datasource_tools.py::describe_table`
- **不做**：`ResourceManager`、`tool_call_log` 表、审计写入、`terminate` 工具（都延后到 Phase E）

**验证**

```python
# Agent 侧
agent = EchoAgent(llm_config=fake_llm)
reply = await agent.generate_reply(
    AgentMessage(content="hello", role="user"), sender=UserProxyAgent()
)
assert reply.content == "hello"

# Tool 侧
@tool(description="加法")
def add(a: int, b: int) -> int: return a + b

pack = ToolPack([add])
assert await pack.async_execute(resource_name="add", a=1, b=2) == 3
assert "add：加法" in pack.render_prompt(lang="zh")
assert "list_tables" in pack.render_prompt(lang="zh") is False  # 本 pack 没装
```

- 单元测试覆盖：`thinking/review/act/verify` 四阶段 & retry 自优化；`@tool` 三种用法（`@tool` / `@tool("name")` / `@tool("name", description=...)`）；`ToolPack._get_call_args` 过滤未知参数
- **不验证**：端到端集成（留给 Phase B）；内置工具真实连库（留给 Phase B 的 `DatasourceResource`）

### Phase B · DataAnalyst + ToolPack 装备 + 单 Agent 端到端（第 2~2.5 周）

**交付**

- `src/agent/resource/datasource_resource.py`（封装 `crud_datasource` + `decrypt_conf` + `db_execute_sql`）
- `src/agent/core/action/query_sql_action.py`（内部调用 `DatasourceResource.query`）
- `src/agent/expand/data_analyst_agent.py`：
  - 装备 `ToolPack([list_tables, describe_table])` 作为默认 resource
  - Prompt 模板升级：系统提示里追加"你可以使用以下工具按需探查 schema：{{tool_infos}}。若问题涉及的表/字段不明确，先调用工具再生成 SQL。"
  - `_init_reply_message` 注入 `dialect` / `tool_infos` 两个 context 变量
  - `act` 识别"LLM 输出是 tool_name JSON"，委托给 `ToolAction`，执行后把 observation 拼进下一轮 thinking 消息；"LLM 输出是 sql JSON"，走 `QuerySqlAction`
  - `correctness_check`：SQL 执行失败时把报错拼回
- `/chat-stream` 的 `agent_mode` 增加 `"single-v2"` 值（临时）：直接跑 `DataAnalystAgent`，不经 Team
- SSE：**`tool_call` / `tool_result` 事件在此阶段就贯通**（因为 DataAnalyst 要用工具）
- 前端仅兼容即可，不需要做"Agent 时间线"面板（留给 Phase D）

**验证**

- **简单问题**"查询所有学生"：DataAnalyst 直接生成 SQL（schema 足够清楚，无需调工具），SSE 顺序 `agent_speak → sql → result → done`
- **模糊问题**"那张记录学生成绩的表有多少条数据"：DataAnalyst 先 `tool_call(list_tables)` → `tool_result` → `tool_call(describe_table)` → `tool_result` → 生成 SQL → `result`
- **错列名问题**：Agent 3 次重试内自愈
- **回归**：`agent_mode="single"` 走老 `SQLGenerator`，行为零变化

### Phase C · AWEL DAG + 多 Agent（第 3 周）

**交付**

- `src/agent/core/awel/`（dag + agent_operator + team_awel_layout）
- `PlannerAgent` / `CharterAgent` / `SummarizerAgent` 全部
- `PlanAction` / `ChartAction` / `SummaryAction`
- `ChatAwelTeam` + `build_chat_team()` 工厂
- SSE 新事件：`plan` / `plan_update` / `agent_speak` / `chart` / `summary`
- Alembic 迁移 + `gpts_plan` / `gpts_message` CRUD

**验证**

- 复杂问题"对比 Q2/Q3 销量并给出结论"：
  - `plan` 事件 ≥ 1 条，含 4 个子任务
  - `agent_speak` 事件 ≥ 4 次（四个角色都发言）
  - `gpts_plan` 表 4 条记录 state=COMPLETE
  - 最终 `summary` 事件文本非空
- 任一 Agent 失败：SSE `error` 事件正常发出，对应 `gpts_plan.state=FAILED`

### Phase D · 记忆与前端（第 4 周）

**交付**

- `GptsMemory.load_history(conv_id)` → 追问时把前 2 轮 `gpts_message` 转为 `rely_messages` 喂入 Planner
- 前端 `ChatRecord.vue` 新增 "Agent 协作" 时间线面板，展示每个角色的 thought / action / observation
- README / 本文件的"实际运行截图"补充

**验证**

- 连续 3 轮对话，第 3 轮 Planner 输出的 JSON 内引用了前 2 轮结果
- 前端能按 Agent 角色分栏展示事件流

### Phase E · Tool 体系补齐 + 审计 + ToolAgent（第 5~5.5 周）

> Phase A 已交付 Tool 最小内核 + 2 个工具；Phase B 已让 DataAnalyst 装备工具。Phase E 负责"补齐 + 加固"，不再是从零做 Tool。

**交付**

- **其余 5 个内置工具 + terminate**：
  - `tools/datasource_tools.py::sample_rows`
  - `tools/calc_tools.py::calculate`（基于 `asteval`，**禁用 Python `eval`**）
  - `tools/embedding_tools.py::find_related_tables` / `find_related_datasources`（依赖 `MVP_PLAN.md` Phase 4 Embedding，若未就绪则用 LIKE 兜底）
  - `tools/history_tools.py::recent_questions`（复用 `chat_crud.get_recent_questions`）
  - `tools/__init__.py::terminate`（`ToolAgent` 专用的终止工具，对齐 DB-GPT `Terminate` 语义）
- `src/agent/resource/manage.py`（`ResourceManager`）：应用启动时一次性注册 `DEFAULT_TOOLS`，Agent 通过 `resource_manager.get_pack("default")` 取用
- `src/agent/expand/tools/__init__.py::DEFAULT_TOOLS`：Python 硬编码导出所有内置工具（**不做** `tool_registry` DB 表和管理 API —— 按决策推迟到 Phase G）
- **审计链路**：
  - `tool_call_log` Alembic 迁移
  - `ToolAction.run` 成功/失败都写 `tool_call_log`
  - 同名工具连续调用 > 3 次时，Agent `correctness_check` 失败，返回"你已连续 N 次调用 {tool} 但未收敛，请换工具或终止"提示
- `ToolAgent` 实现（6.5 节）：作为可插入 DAG 的独立节点
- `ChatAwelTeam` 支持 `build_chat_team(extra_agents=[tool_agent])`

**验证**

- `DataAnalyst` 在 Phase B 装备工具清单从 `[list_tables, describe_table]` 升级到 `[list_tables, describe_table, sample_rows, find_related_tables]` 后，复杂问题"分析 Q3 销售趋势"能自动先 `find_related_tables` 再 `describe_table` 再生成 SQL
- `ToolAgent` 独立冒烟：给它装 `[calculate, terminate]`，问"帮我算 (15*12)+30"，3 步内终止并返回 210
- 滥用防护：故意让 LLM 连续 4 次调 `list_tables`，第 4 次 Agent 返回 `have_retry=False` 并优雅退出
- `tool_call_log` 表：每次 `tool_call` / `tool_result` 事件对应 1 条记录

### Phase F · 前端工具可视化 + ToolAgent 接入 DAG（第 6 周）

**交付**

- 前端 "Agent 协作" 时间线（Phase D 已完成基础）扩展：工具调用单独渲染为可折叠节点，展示 `thought / tool_name / args / result / elapsed_ms`
- `ChatAwelTeam` 默认 DAG 中**可选**插入 `ToolAgent` 节点（通过 `build_chat_team(enable_tool_agent=True)`）
- 规划阶段：`PlannerAgent` 在规划 JSON 里可以把某些子任务的 `sub_task_agent` 设为 `"ToolExpert"`（即 ToolAgent 角色），由 ToolAgent 调用工具完成该步
- 文档：写清"哪些任务该走 ToolAgent，哪些该让主 Agent 自带工具"的决策指南（放进本文件第 16 节）

**验证**

- 复杂问题"查本月销售最高的 3 个品类，并计算它们的同比增长率"：
  - Planner 规划出 2 个子任务：第 1 个给 `DataAnalyst`，第 2 个给 `ToolExpert`（调 `calculate`）
  - SSE 事件流按时间线正确展示 2 个 Agent + N 次工具调用
- 回归：`enable_tool_agent=False` 时与 Phase C 完全一致

### Phase G（远期，候选，不在本轮）

- **工具 UI 管理**：启用 `tool_registry` 表 + `/api/v1/agent/tools` CRUD + 前端工具市场页（启/禁/查看调用日志）。
- **应用级 Skill 模板**：对齐 DB-GPT `/skills/walmart-sales-analyzer`，允许打包 `prompt + tools + datasource binding + DAG` 为可分发的"技能包"。DB 表 `skill_template`，前端提供 Skill 市场/启用页。
- **MCP 协议接入**：通过 MCP 连接外部工具服务，对齐 DB-GPT `util/mcp_utils.py`。
- 条件分支 DAG（Charter 只在有数值列时触发；Summarizer 结果不满意时回退到 DataAnalyst 再查一次）
- 向量记忆（衔接 Phase 4 Embedding）
- Agent 配置化（数据库配置 → 动态装配 DAG）

---

## 11. 风险与规避

| 风险 | 影响 | 规避策略 |
|---|---|---|
| LLM 输出不稳（Planner JSON 解析失败） | 团队流水线早期全崩 | `util/json_parser.py` 三级容错（代码块抽取 → json5 → 首尾大括号截取）+ `correctness_check` 重试 |
| 4 Agent 串行延迟高 | 用户等待感差 | 全程 SSE 流式 `agent_speak`，让用户实时看到思考过程；简单问题用 `agent_mode=single` 快速路径 |
| Session 跨线程 | SQLAlchemy 异常 | 每个 Agent act 内部 `with get_db_session():`，不跨越 |
| 改动波及前端 | 上线风险 | 旧 SSE 事件全保留；新事件默认开启但前端灰度，通过 Feature Flag 控制 |
| 自实现 DAG 潜在并发 bug | 执行顺序错乱 | 当前只做线性 DAG（单链），`call()` 同步 await；单测覆盖 3/4/5 节点链 |
| DB-GPT 概念过度复刻导致代码膨胀 | 维护成本高 | 严格遵守"只抄本文档列出的 5 个核心类"，`DynConfig` / `Profile i18n` / `AgentManage` 全部砍掉 |
| 老 `/chat-stream` 与新 Team 行为分叉 | 回归 bug | `agent_mode` 路由在最外层分流；`single` 分支代码一行都不改 |
| LLM 输出的 `tool_name` / `args` 与注册清单不匹配 | 工具调用失败，流程卡死 | 三级兜底：`_get_call_args()` 过滤不认识参数 → 失败写入 observation → Agent 下一轮重选工具 |
| 工具滥用（LLM 反复调同一个工具不收敛） | 成本爆炸 / 死循环 | `ToolAgent.max_retry_count=5` + `terminate` 工具 + `tool_call_log` 中连续同名调用 > 3 次时强制终止 |
| `@tool` 装饰函数参数注解不全 | 自动解析出错 | `function_utils.py` 对缺 annotation 的参数报警；编写工具时必须带类型注解 + `Doc(...)` |
| 工具执行阻塞 event loop（同步长任务） | API 卡住 | `ToolPack.async_execute` 对同步 tool 自动走线程池（`asyncio.to_thread`），而非直接调用 |
| 工具权限失控（某工具能 `DROP TABLE`） | 数据损坏 | 约定：所有工具必须只读；写操作类不进入 `DEFAULT_TOOLS`；`tool_call_log` 供审计 |

---

## 12. 成功判据（最终验收）

完成 Phase A-D 后，下述全部成立即视为落地成功：

1. `agent_mode=team` 下，简单问题与 `single` 模式在**语义结果**上等价（SQL 正确、数据一致）。
2. `agent_mode=team` 下，至少 1 个以上复杂问题用例（"对比 / 拆分 / 归因"）能正确拆解为 ≥ 2 个子任务并全部成功。
3. 前端"Agent 协作时间线"能清晰展示 4 个角色的思考与产出。
4. 追问场景：第 N 轮能利用第 N-1 轮的上下文（通过 `rely_messages`）。
5. 代码行数：`src/agent/` 总行数 ≤ **3500 行**（含 Tool 体系，防过度工程）。
6. 单测覆盖率：`src/agent/core/` ≥ 70%，`src/agent/resource/tool/` ≥ 80%。
7. Tool 体系：`@tool` 可声明任意 Python 函数为工具；DataAnalyst 在某复杂问题下**至少会自主调用一次工具**（`tool_call_log` 可查）；`tool_call` / `tool_result` 两事件在前端面板上与 `agent_speak` 一起按时间线正确排列。

---

## 13. 核心文件索引（快速导航）

| 功能 | 文件路径 |
|---|---|
| Agent 接口定义 | `src/agent/core/agent.py` |
| ConversableAgent | `src/agent/core/base_agent.py` |
| ManagerAgent | `src/agent/core/base_team.py` |
| Action 基类 | `src/agent/core/action/base.py` |
| DAG 骨架 | `src/agent/core/awel/dag.py` |
| 团队管理 | `src/agent/core/awel/team_awel_layout.py` |
| Planner | `src/agent/expand/planner_agent.py` |
| DataAnalyst | `src/agent/expand/data_analyst_agent.py` |
| Charter | `src/agent/expand/charter_agent.py` |
| Summarizer | `src/agent/expand/summarizer_agent.py` |
| 数据源资源 | `src/agent/resource/datasource_resource.py` |
| Resource 抽象 | `src/agent/resource/base.py` / `pack.py` / `manage.py` |
| Tool 体系 | `src/agent/resource/tool/base.py` / `pack.py` |
| ToolAction | `src/agent/core/action/tool_action.py` |
| ToolAgent | `src/agent/expand/tool_agent.py` |
| 内置工具 | `src/agent/expand/tools/` |
| GptsMemory | `src/agent/core/memory/gpts_memory.py` |
| 统一入口 | `src/chat/api/chat.py::chat_stream` |

---

## 14. 接下来的动作

Phase A 被确定扩大范围（Agent 内核 + Tool 最小内核），建议拆成两个 PR 推进：

### PR #1：Agent 内核骨架（3~4 天）

1. 建 `src/agent/` 目录
2. `core/agent.py` / `core/base_agent.py` / `core/profile.py`
3. `core/action/base.py`（不含 `ToolAction`）
4. `core/memory/agent_memory.py`
5. `util/json_parser.py`
6. `EchoAgent` + `UserProxyAgent` + 单元测试

### PR #2：Tool 最小内核 + 首批 2 工具（3~4 天）

1. `resource/base.py` / `resource/pack.py` / `resource/tool/*.py`
2. `util/function_utils.py`
3. `core/action/tool_action.py`
4. `expand/tools/datasource_tools.py::list_tables` / `describe_table`
5. 单元测试：`@tool` 三种用法、`ToolPack.render_prompt` / `async_execute`、`ToolAction` 成功/失败/参数过滤

Phase A 完成后再开 PR #3（Phase B）。Phase A 期间不动任何 `src/chat/` 代码；Phase B 开始才产生交集。

## 15. 版本与更新日志

| 版本 | 日期 | 变更 |
|---|---|---|
| v1 | 2026-04-22 | 初版：4 Agent 固定 DAG + 单入口 + 精简自实现（Phase A~D） |
| v2 | 2026-04-22 | 追加 Tool/Skill 体系：`BaseTool`/`FunctionTool`/`@tool`/`ToolPack`/`ToolAction`/`ToolAgent` + 7 个内置工具，新增 Phase E（Tool 内核）、Phase F（工具注入）；SSE 新增 `tool_call`/`tool_result`；DB 新增 `tool_registry`（可选）/`tool_call_log` |
| v3 | 2026-04-22 | 重排里程碑：**Tool 最小内核前置到 Phase A**（DataAnalyst Phase B 即装备工具）；`DEFAULT_TOOLS` Python 硬编码；`tool_registry` 表推迟到 Phase G；Phase E 职责改为"工具补齐 + 审计 + ToolAgent"；Phase F 职责改为"前端可视化 + ToolAgent 接入 DAG"；总工期 4 周 → 6.5 周 |
| v4 | 2026-04-22 | Phase A~B 落地：`src/agent/` 内核 + Tool 体系 + ReActAgent + DataAnalyst + `/chat-stream` `agent_mode` 路由；`agent_mode` 最终值为 `"agent"`(默认) / `"legacy"`；SSE 兑底 `default=str` 防 Decimal/datetime 崩流；新增 `src/agent/smoke.py` CLI 供真实 LLM 冒烟 |
| v5 | 2026-04-22 | Phase C-1 落地：新增 `CharterAgent`（图表推荐）+ `SummarizerAgent`（中文结论）；`agent_mode` 扩展 `"team"`（DataAnalyst → Charter → Summarizer 线性执行）；SSE 新增 `agent_speak` / `chart` / `summary` 事件；Charter 失败自动回落 `table`，Summarizer 失败自动回落 DataAnalyst 原文；`agent_runner.py` 抽出 `_run_data_analyst_phase`，两模式复用 ReAct 段。Planner + `gpts_plan` 表推迟到 Phase C-2。 |
| v6 | 2026-04-22 | Phase C-2 落地：新增 `PlannerAgent`（把问题拆成 1~6 个 sub_task，极简契约 `plans: string[]`）；team 流水线升级为 Planner → N × DataAnalyst → Charter → Summarizer，每个 sub_task 独立 ReAct 上下文（无污染）；SSE 新增 `plan` / `plan_update` 事件；Summarizer 的 prompt 升级为 `{{sub_tasks_block}}`，综合所有 sub_task 结果一次性产出结论；Chart 基于最后一个成功 sub_task；故障分治：Planner/Charter/Summarizer 失败都有回落，部分 sub_task 失败不中断主流程，全部 sub_task 失败才跳过 Chart/Summary。**不做** `gpts_plan` 表和 AWEL DAG 改造——runner sequential 已足够清晰，等真有分叉/并行需求再上。 |
| v7 | 2026-04-22 | Phase C-3 落地：引入请求级 `trace_id` 串联。新增 `src/common/core/trace.py`（`ContextVar` + `new_trace_id` / `trace_scope` + `install_trace_log_factory`）；`src/main.py` 启动时装 LogRecord factory + `basicConfig` 用 `%(trace_id)s` 前缀；`/chat-stream` endpoint 入口生成 12 位 trace_id 并在 `StreamingResponse` 加 `X-Trace-Id` 响应头（**不**污染 SSE payload，向后兼容最好）。agent_runner / react_agent / tool 代码一行未动——ContextVar 是 async-aware，`asyncio.to_thread` 会自动 copy context，子协程/子线程自然继承。新增 8 条 `tests/core/test_trace.py` 单测 + 1 条 `X-Trace-Id` header 回归。价值：并发多请求时能在日志里 `grep <tid>` 拉出单个请求的完整流水；前端报 bug 可贴 tid 排查。 |
| v9.4 | 2026-04-23 | **Phase F 收口：ToolAgent 开关化 + 使用指南**。①新增 `src/agent/expand/chat_awel_team.py`，提供 `build_chat_team(enable_tool_agent=...)` 与 `resolve_sub_task_agent()`；`enable_tool_agent=False` 时即便 Planner 规划了 `ToolExpert` 也统一回退 DataAnalyst，保证与 Phase C 行为等价。②`ChatRequest` 新增 `enable_tool_agent: bool=True`，`/chat-stream` 透传到 `run_team_stream`；team 模式 now 可按请求级开关控制 ToolAgent 接入。③测试补齐：`test_team_disable_tool_agent_falls_back_to_data_analyst`（team runner）+ `test_team_mode_can_disable_tool_agent`（chat-stream 路由透传），确保关闭开关时不会触发 ToolExpert 路由。④文档第 16 节补充 ToolExpert vs DataAnalyst 任务分派建议。|
| v9.3 | 2026-04-23 | **PR-E4 落地：ToolAgent + Planner 分派**。①新增 `src/agent/expand/tool_agent.py`（`ToolExpert` 角色，基于 ReActAgent），默认复用 ResourceManager 的 `default` pack。②Planner 升级为兼容两种 plans 语法：字符串数组（向后兼容）与对象数组（`{task, sub_task_agent}`）；输出 `extra` 新增 `plan_agents`，仅允许 `DataAnalyst` / `ToolExpert` 两种角色，非法值回落 DataAnalyst。③`run_team_stream` 路由升级：每个 sub_task 根据 `sub_task_agent` 选择 `_run_data_analyst_phase` 或 `_run_tool_expert_phase`；`plan` 事件新增 `sub_task_agents`；`plan_update` 增加 `sub_task_agent` 字段，方便前端区分任务执行者。④ToolExpert 事件流与 DataAnalyst 完全对齐（`tool_call/tool_result/final_answer` + `sub_task_index`），前端无需新增协议即可展示。⑤测试：`test_planner.py` 新增对象 plans + `sub_task_agent` 解析回归；`test_team_runner.py` 新增 ToolExpert 路由回归（断言 `calculate` 由 `agent=ToolExpert` 发起且 `sub_task_index` 正确）。全量 174 tests passed。|
| v9.2 | 2026-04-23 | **PR-E3（simple 版）落地：tool_call_log 审计写入（raw SQL + 异步后台）**。按决策不引入 ORM model、不过度扩 scope 到查询 API。①新增 `src/agent/audit/tool_call_log.py`：`log_tool_call_fire_and_forget()` 用 `asyncio.create_task` + `asyncio.to_thread` 后台写库，失败只记 warning，不阻塞主流程；写入内容聚焦你选的聚合字段：`agent_name` / `round_idx` / `sub_task_index`，同时保留 `trace_id` / `tool_name` / `success` / `elapsed_ms` / `args_json` / `result_preview(500)`。②`ToolAction.run` 全路径审计：成功、JSON 解析失败、未知工具、参数不匹配、工具异常都会触发写入；`ReActAgent` 给 `act()` 透传 `round_idx` + `agent_name`，`agent_runner` 透传 `sub_task_index`（team 模式下可按子任务聚合）。③表结构采用启动期自动兜底建表：`src/common/core/database.py::_ensure_tool_call_log_table` 在 `init_db()` 阶段执行 `CREATE TABLE IF NOT EXISTS tool_call_log` + 两个索引（`trace_id`、`created_at`），兼容 PostgreSQL/SQLite。④测试：更新 `tests/agent/test_tool_action.py`（monkeypatch 掉真实写库，验证成功/失败均触发审计且元数据正确）；全量 `172 passed`，变更文件 ruff 全绿。|
| v9.1 | 2026-04-23 | **PR-E2：E-embed + E-resmgr**。①**E-embed**：新增 `find_related_tables(datasource_id, question, limit=10)` 工具——LIKE/token 兜底版（MVP_PLAN Phase 4 embedding 未就绪前的占位；接口不变以便日后平替为向量召回）。分词策略：ASCII 连续段按 word lowercase；中文连续段 2-gram 滑窗；长度 < 2 的 token 过滤以防"的"/"是"/"a" 这类噪声命中所有表。打分 = 在 `name`/`comment`/字段 `name`/字段 `comment` 拼接串里命中的 token 数，按分数降序截前 K 张；完全不命中时返回 `list_tables` 兜底并标注"未命中关键词"——保证 LLM 不会死在这一步。DataAnalyst prompt 加路径分支："表多/关键词明确 → `find_related_tables`；否则 → `list_tables`"。②**E-resmgr**：`src/agent/resource/manager.py` 新增 `ResourceManager` 单例 + `install_default_resources()` 幂等安装 + `get_resource_manager()` 懒构造。在 FastAPI `lifespan` 启动阶段注册名为 `"default"` 的**未绑定模板 pack**；`build_data_analyst` 优先从 manager 取模板再 `.bind(datasource_id, user_id)` 生成请求级新 pack，模板 pack 保持只读共享。防御式兜底：`manager` 里若没有 `default` pack，`build_data_analyst` 会静默触发一次 `install_default_resources`，保证忘了跑 lifespan 的调用路径（单测、CLI 冒烟）不炸。③测试：`test_tool_business.py` +5 条（find_related_tables 排序/英文/兜底/limit 边界/短词过滤）；新增 `test_resource_manager.py` +11 条（注册/重名/replace/单例/幂等/内容正确/模板不带 bindings/build_data_analyst 集成/兜底自动 install）。更新 pack 长度断言为 9（6 业务 + find_related_tables + calculate + terminate）。172 条后端测试全绿，ruff 全过。价值：(a) 表多场景下显著省 token；(b) 把"从哪儿取 pack"这件事集中到 ResourceManager，**为 PR-E4 ToolAgent 按名取 pack 铺路**。遗留决策：E-embed 换向量召回留给 MVP_PLAN Phase 4 完成后做，接口已预留；`find_related_datasources` 暂未用 embedding（沿用全量兜底），同原因。|
| v9 | 2026-04-23 | **PR-E1（Phase E 首块）：E-calc + E-guard**。①**E-calc**：新增 `calculate` 工具（`src/agent/resource/tool/calc.py`，asteval 1.0 驱动），接入 `default_business_tools()`，DataAnalyst prompt 加一条"百分比/同比/均值优先用 calculate"。**⚠️ 开发期实测踩坑**：asteval 的 `minimal=True` **仍默认放行 `open` / `dir`**，外加装了 numpy 时会自动注入 `fromfile` / `loadtxt` 等能读任意文件的函数——`calculate("open('/etc/passwd').read()")` 实测可读文件，等价 RCE。加固方案：(a) 传 `use_numpy=False` 禁 numpy symtable 注入；(b) 显式 pop `_BLOCKED_SYMBOLS`（14 个已知可调用的危险符号：`open`/`dir`/`__import__`/`exec`/`eval`/`compile`/`getattr`/`setattr`/`vars`/`globals`/`locals`/`bytearray`/`bytes`/`super` 等）；(c) asteval 属性访问本身是白名单（dunder 被 `no safe attribute` 拒绝，已 probe），所以只要堵住直接可调用入口就够。每次调用新建 Interpreter 防跨调用符号表串扰。②**E-guard**：`ReActAgent.generate_reply` 维护 `(last_tool_name, streak)`，连续 3 次同工具（仅计成功解析到已知工具的那次；解析失败/未知工具重置）会在**下一轮 observation 前** prepend 一段软警告，推动 LLM 换工具或 terminate。**不强制终止**（max_rounds 仍是硬上限）。警告只进 ReAct 上下文，**不污染** SSE `tool_result` payload——前端需要原始工具信号。③测试：新增 `tests/agent/test_tool_calc.py`（11 条，含"读 /etc/passwd 应被拒"的 RCE regression + 沙盒隔离 + 反射拒绝）+ 2 条 `tests/agent/test_react_agent.py` streak 警告回归（含"SSE payload 不被污染"断言）；更新 `test_tool_business.py` 对默认 pack 长度的断言（8 工具：6 业务 + calculate + terminate）。156 条后端测试全绿。④依赖：`asteval>=1.0` 入 pyproject。价值：NLSQ 后处理算术（同比/环比/百分比）从此用确定性求值器，LLM 心算易错的场景消除；LLM 坏死循环（"我要再看一次 list_tables"）有软性自愈机制。**未来升级 asteval 版本时必须重新 probe symtable**（在 `calc.py` 里留了警示注释）。|
| v8.1 | 2026-04-23 | **Hotfix：修复 schema 探索类问题误报"执行失败"**。场景：用户问"有哪些学生相关的表"/"XX 表的字段是什么"时，DataAnalyst 完全合理地走 `list_tables → describe_table → sample_rows → terminate` 路径，根本不需要 `execute_sql`——但 `_run_data_analyst_phase` 先前把 `is_success` 硬等于 `terminated and state.last_exec_result is not None`，导致：runner 一边发 `error`（agent 模式）/ `plan_update(state=error)` + `error`（team 模式），一边 `final_answer` / `summary` 照常下发，前端就出现"红框执行失败 + 漂亮 markdown 查询结果"的矛盾 UI。**修复**：放宽判定为 `is_success = terminated and bool(reply.content.strip())`——只要 Agent 主动 terminate 并给出了非空结论就算成功，元数据探索是一等公民。下游全部已有兜底：Charter 遇到空 `exec_result` 回落 `chart_type=table`（空 config），`plan_update(ok)` 用 `(... or {}).get("row_count") or 0` 兜底，持久化 `sql=""` 也没问题。新增 2 条回归测试：`test_schema_exploration_without_execute_sql_is_success`（agent 模式）+ `test_team_schema_exploration_without_execute_sql_is_success`（team 模式），总 142 条全绿。|
| v8 | 2026-04-23 | Phase D 落地（后端小补 + 前端 SSE 全对接）：①**后端** `sample_rows` 工具升级加 `where_clause` 可选参数（`sqlglot` 校验单条 SELECT、无 DML / 无 UNION 绕过），DataAnalyst ReAct 现在可做"条件采样"理解枚举值/业务语义；限速上限从 100 → 10（LLM 可见），超额 clamp。②**后端** `_make_forwarder` 为 team 模式的 `tool_call` / `tool_result` / `agent_thought` / `final_answer` 事件 payload 自动注入 `sub_task_index`，前端据此按子任务折叠展示。③**前端** `chat.ts::executeStream` 扩展 SSE 消费层：新增 `onToolCall` / `onToolResult` / `onAgentThought` / `onFinalAnswer` / `onPlan` / `onPlanUpdate` / `onAgentSpeak` / `onChart` / `onSummary` 9 个 handler，`payload` 新增 `agent_mode`；`ChatInput` 加 `el-segmented` 双模式开关（默认 team）。④**前端** `typed.ts::ChatRecord` 扩 `agent_mode` / `plans` / `plan_states` / `chart_config` / `summary` / `tool_calls`，按 `(sub_task_index, round)` 合并 tool_call + tool_result。⑤**前端** `ChatRecord.vue` 新增三个 UI 面板：Plans 面板（子任务进度，running/ok/error 三色）、Tools 面板（按 sub_task 分组显示 thought / args / elapsed / observation）、Summary 气泡（Team 模式的最终结论，高亮在答案上方）；ChartComponent 加 `axesOverride` 可选 prop 消费 Charter 的 `chart_config`，不合法字段自动 fall back 到前端 `inferAxes`。⑥i18n 扩 10 个键（`agent_mode.*` / `plan` / `plan_steps` / `sub_task_label` / `tool_calls` / `tool_calls_count` / `thought` / `observation` / `summary`）。新增测试：5 条 `sample_rows` where 正反用例 + 2 条 `sub_task_index` 契约回归，总计 140 条后端测试全绿；前端 `vue-tsc --noEmit && vite build` 一次通过。价值：Team 模式**真正能在浏览器里跑起来**——用户能看到 Planner 的拆分、每个 sub_task 的 ReAct 痕迹、Charter 的图表推荐、Summarizer 的中文结论；sample_rows 的 where 让复杂 NLSQ 的 SQL 准确率明显提升（可以先 `sample_rows status='active' LIMIT 3` 再写聚合 SQL）。|

## 16. 实战使用（Phase B 落地后可用）

### 16.1 HTTP 调用（前端/curl）

`POST /api/v1/chat/chat-stream` 现在接受 `agent_mode`：

```json
{
  "question": "本月订单最多的前三名用户是谁",
  "datasource_id": 1,
  "conversation_id": 42,
  "agent_mode": "agent",
  "enable_tool_agent": true
}
```

- `agent_mode` 缺省为 `"agent"`，走新的 ReAct DataAnalyst（单 Agent）；
- 设 `"team"` 走 Phase C-1 的线性 DAG：DataAnalyst → Charter → Summarizer；
- `enable_tool_agent` 仅在 `team` 模式生效：`true` 允许 Planner 把子任务分派给 `ToolExpert`；`false` 强制全部回退 `DataAnalyst`（与 Phase C 行为一致）；
- 设 `"legacy"` 回退到原 `SQLGenerator` 路径，**字节级等价于旧实现**；
- 其他值（如 `"wizard"`）直接 422。

SSE 事件流在旧事件（`step` / `sql` / `result` / `error` / `done`）基础上叠加：

**所有 agent 模式共用：**

- `agent_thought`  —— 每轮 LLM 原文；
- `tool_call`      —— 工具调用前（含 `tool` / `args` / `thought`）；
- `tool_result`    —— 工具调用后（含 `success` / `content` / `data` / `elapsed_ms` / `terminate`）；
- `final_answer`   —— `terminate` 工具触发的最终文本。

**仅 `agent_mode="team"` 追加：**

- `agent_speak`    —— Planner / Charter / Summarizer 的开始/结束广播 `{agent, status: "start"|"end"|"error"}`；
- `plan`           —— Planner 一次性给出的完整子任务列表 `{plans: string[], sub_task_agents?: ("DataAnalyst"|"ToolExpert")[]}`；
- `plan_update`    —— 每个 sub_task 执行状态 `{index, state: "running"|"ok"|"error", sub_task?, sub_task_agent?, sql?, row_count?, error?}`；
- `chart`          —— Charter 推荐的 `{chart_type, chart_config: {x, y, title}}`（基于最后一个成功 sub_task）；
- `summary`        —— Summarizer 综合所有 sub_task 的最终中文结论 `{content}`。

team 模式的事件**流水顺序**（典型）：
```
agent_speak(Planner start) → agent_speak(Planner end)
plan
  plan_update(idx=0, running)
    agent_thought / tool_call / tool_result / final_answer  ← 第 1 个 sub_task 的 ReAct
    sql / result                                              ← legacy 兼容
  plan_update(idx=0, ok)
  plan_update(idx=1, running)
    ... 第 2 个 sub_task ...
  plan_update(idx=1, ok)
  ...
agent_speak(Charter start/end) → chart
agent_speak(Summarizer start/end) → summary
done
```

老前端不认识的事件会被静默忽略；`sql` / `result` 由 runner 在 `execute_sql` 成功后**自动补发**，现有渲染逻辑零改动。Charter 的 chart_type 覆盖落库时的 `chart_type`、Summarizer 的结论覆盖落库时的 `reasoning`——前端刷新历史也能看到"team 视角"的答案。

### 16.2 本地冒烟（不起服务 / 不用前端）

```bash
# 确保 .env 配好 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 以及数据库连接
python -m src.agent.smoke -d 1 "本月订单最多的前三名用户是谁"

# 调上限 + 打印完整 observation（适合复杂问题）
python -m src.agent.smoke -d 1 -u 7 --max-rounds 12 --full "..."
```

输出按事件分色、每条带增量耗时（`+Nms`），适合观察：LLM JSON 稳定性、每轮延迟分布、SQL 失败后是否自愈。`persist=False`，不会往 `chat_conversation_record` 写入任何脏数据。

退出码：`0` 正常终止；`1` 未到 `terminate` 或抛异常；`130` Ctrl-C。

### 16.3 冒烟检查清单（上生产前）

- [ ] 简单问题（"用户有多少人"）Agent 4 步内 `terminate`；
- [ ] 模糊问题（"最活跃的 10 个用户"）Agent 能先 `list_tables` → `describe_table` → 再写 SQL；
- [ ] 故意构造坏 SQL（比如让 LLM 猜不存在的列名）能在一轮内自愈；
- [ ] `max_rounds` 触顶时 runner 发 `error` 事件且 `record_id=0`；
- [ ] 前端切到 `agent_mode=legacy` 与切前行为**完全一致**（冒烟用例覆盖）；
- [ ] 真实 LLM 下 JSON 解析失败率观察值 < 5%（若过高需加 few-shot）。

### 16.4 ToolExpert 分派建议（Phase F）

- **优先给 DataAnalyst 的任务：** 需要探查 schema、写 SQL、跑查询、读结果再决策（大多数数据分析问题）。
- **优先给 ToolExpert 的任务：** 已有中间数值、只需做确定性工具后处理（同比/环比/百分比、单位换算、简单多步计算）。
- **不要给 ToolExpert 的任务：** 需要反复试 SQL、依赖复杂业务语义、需要图表推荐上下文（这些更适合 DataAnalyst + Charter）。
- **灰度策略：** 生产初期建议 `enable_tool_agent=false` 观察 1~2 天，确认 Planner 输出稳定后再按会话/租户逐步打开。
- **诊断指标：** 关注 `tool_call_log` 中 `agent_name=ToolExpert` 的成功率、平均轮数、`calculate` 占比；异常升高时先关开关再排查 Planner prompt。
