# 开发指南

## 1. 开发环境搭建

### 1.1 前置条件

- Python 3.11+
- Git
- Redis
- PostgreSQL

### 1.2 克隆项目

```bash
git clone <repo-url>
cd multi-agent-collaboration-system
```

### 1.3 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate
```

### 1.4 安装依赖

```bash
make dev
# 或
pip install -e ".[dev]"
```

### 1.5 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

## 2. 项目结构

```
multi-agent-collaboration-system/
├── src/                          # 源代码
│   ├── main.py                   # FastAPI入口
│   ├── config.py                 # 配置管理
│   ├── models/                   # 数据模型
│   ├── agents/                   # Agent实现
│   │   ├── planner.py           # Planner Agent
│   │   ├── executor.py          # Executor Agent
│   │   └── reviewer.py          # Reviewer Agent
│   ├── orchestrator/            # LangGraph编排
│   │   ├── graph.py             # 状态图定义
│   │   ├── state.py             # 状态定义
│   │   └── nodes.py             # 节点实现
│   ├── state/                   # 状态管理
│   ├── communication/           # 通信层
│   ├── tools/                   # MCP工具
│   └── api/                     # API路由
├── mcp-servers/                 # MCP服务器
├── tests/                       # 测试
├── docs/                        # 文档
└── scripts/                     # 脚本
```

## 3. 核心概念

### 3.1 Agent架构

- **Planner Agent**: 任务分解，生成DAG
- **Executor Agent**: 任务执行，调用MCP工具
- **Reviewer Agent**: 质量审核，熔断降级

### 3.2 LangGraph状态机

- **StateGraph**: 驱动内部状态流转
- **条件边**: 根据审核结果路由
- **Checkpointer**: 状态持久化

### 3.3 MCP协议

- **MCP Client**: 调用外部工具
- **MCP Server**: 独立工具服务

## 4. 开发流程

### 4.1 创建新Agent

1. 在 `src/agents/` 创建新文件
2. 继承基类或实现标准接口
3. 在 `src/orchestrator/nodes.py` 添加节点
4. 在 `src/orchestrator/graph.py` 注册节点

### 4.2 添加新工具

1. 在 `mcp-servers/` 创建新服务
2. 实现 `/execute` 接口
3. 在 `src/tools/registry.py` 注册工具
4. 更新 `docker-compose.yml`

### 4.3 修改状态

1. 在 `src/orchestrator/state.py` 修改状态定义
2. 更新相关节点实现
3. 更新测试

## 5. 测试

### 5.1 运行测试

```bash
# 运行所有测试
make test

# 运行单元测试
make test-unit

# 运行集成测试
make test-integration
```

### 5.2 编写测试

```python
import pytest
from unittest.mock import AsyncMock

class TestMyAgent:
    @pytest.fixture
    def agent(self):
        return MyAgent()
    
    @pytest.mark.asyncio
    async def test_execute(self, agent):
        result = await agent.execute({"task": "test"})
        assert result.success is True
```

### 5.3 测试覆盖率

```bash
pytest --cov=src --cov-report=html
```

## 6. 代码规范

### 6.1 代码风格

- 使用Ruff进行代码检查和格式化
- 遵循PEP 8规范
- 使用类型注解

```bash
# 代码检查
make lint

# 代码格式化
make format
```

### 6.2 提交规范

```
<type>(<scope>): <subject>

类型：
- feat: 新功能
- fix: 修复
- docs: 文档
- style: 格式
- refactor: 重构
- test: 测试
- chore: 构建/工具

示例：
feat(planner): 添加任务分解功能
fix(executor): 修复MCP调用超时问题
docs(api): 更新API文档
```

## 7. 调试

### 7.1 日志

```python
import structlog

logger = structlog.get_logger()
logger.info("task_started", task_id="123", agent="executor")
```

### 7.2 断点调试

使用VS Code或PyCharm进行断点调试。

### 7.3 Langfuse追踪

配置Langfuse环境变量，查看链路追踪。

## 8. 部署

### 8.1 本地部署

```bash
make run
```

### 8.2 Docker部署

```bash
make docker-build
make docker-up
```

### 8.3 Kubernetes部署

```bash
kubectl apply -f k8s/
```

## 9. 常见问题

### 9.1 Redis连接失败

检查Redis服务是否启动，REDIS_URL配置是否正确。

### 9.2 LLM调用失败

检查OPENAI_API_KEY配置，API配额是否充足。

### 9.3 测试失败

检查测试环境配置，Mock是否正确设置。

## 10. 资源

- [LangGraph文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI文档](https://fastapi.tiangolo.com/)
- [MCP协议](https://modelcontextprotocol.io/)
- [Pydantic文档](https://docs.pydantic.dev/)
