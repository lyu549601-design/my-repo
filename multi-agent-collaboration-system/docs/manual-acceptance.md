# 手动部署与验收指南

本文以 Windows + PowerShell 为例。推荐使用 Docker Compose 一键启动全部服务，因为 PostgreSQL 已切换到 pgvector 镜像。

## 0. 前置条件

- 已安装 Docker Desktop，并确认 Docker 正在运行。
- 已安装 Python 3.11+，且 `python` 命令可用。
- 有可用的 `OPENAI_API_KEY`。没有 `SERPAPI_KEY` 和 `TUSHARE_TOKEN` 也能跑通，搜索和金融接口会返回模拟数据。

## 1. 准备环境变量

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填写：

```env
OPENAI_API_KEY=sk-你的DeepSeek Key
OPENAI_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com/v1

POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=multiagent
```

记忆系统相关参数已默认：

```env
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DIM=512
MEMORY_TOKEN_BUDGET=1600
MEMORY_RETRIEVAL_TOP_K=3
```

注意：DeepSeek 官方 API 不提供 Embedding 接口，所以向量检索使用本地 `BAAI/bge-small-zh-v1.5`，对话与摘要生成全部走 `deepseek-v4-flash`。

## 2. 构建并启动服务

```powershell
docker compose up -d --build
```

启动后包含：

| 服务 | 地址 |
|------|------|
| API Gateway | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs |
| Agent 记忆服务 | http://localhost:8084 |
| 记忆服务文档 | http://localhost:8084/docs |
| Search MCP | http://localhost:8081 |
| Financial MCP | http://localhost:8082 |
| Cleaner MCP | http://localhost:8083 |
| Redis | localhost:6379 |
| PostgreSQL + pgvector | localhost:5432 |

首次运行记忆写入时，记忆服务容器会自动下载本地中文 Embedding 模型 `BAAI/bge-small-zh-v1.5`，需要几十秒到几分钟，请耐心等待日志中出现 `memory.evidence_stored`。

记忆服务也可以独立启动：双击 `D:\xm\agent-memory-service\启动.bat`，或在其目录下执行 `docker compose up -d --build`。

## 3. 验证服务健康

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

健康接口应返回：

```json
{"status":"healthy"}
```

## 4. 提交一个研报任务

```powershell
$body = @{ topic = "2026年中国新能源汽车市场格局" } | ConvertTo-Json
$resp = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/reports `
  -ContentType "application/json" `
  -Body $body

$taskId = $resp.task_id
$taskId
```

轮询任务状态：

```powershell
do {
  Start-Sleep -Seconds 5
  $status = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reports/$taskId"
  Write-Host $status.status
} while ($status.status -notin @("completed", "failed"))

$status.status
$status.result.content
```

也可以直接在浏览器打开 http://localhost:8000/docs，用 `POST /api/v1/reports` 提交。

## 5. 验收记忆系统

### 5.1 检查证据摘要写入

任务运行期间，打开另一个终端：

```powershell
docker compose logs -f api-gateway | Select-String "memory.evidence_stored"
```

应该看到每个成功子任务至少一条 `memory.evidence_stored` 日志。

### 5.2 检查 Reviewer 上下文与 Token 预算

```powershell
docker compose logs -f api-gateway | Select-String "reviewer.context_built"
```

日志应包含 `tokens_used`、`token_budget`、`truncated`、`top_memories`。验收标准：

- `token_budget` 为 1600。
- `tokens_used` 不高于 1600。
- `truncated` 说明内容超预算时被压缩。

### 5.3 检查一致性检查不再是写死的 0.9

运行测试即可验证：

```powershell
python -m pytest tests/unit/test_reviewer.py -q
```

### 5.4 检查重试反馈闭环（可选）

临时把 `.env` 中 `QUALITY_THRESHOLD` 改成 `1.0`，重启 API：

```powershell
docker compose up -d --force-recreate api-gateway
```

再次提交一个任务，查看日志：

```powershell
docker compose logs -f api-gateway | Select-String "reviewer.feedback_stored"
docker compose logs -f api-gateway | Select-String "memory.feedback_stored"
```

应能看到失败任务的重试反馈被写入记忆。验收结束后把阈值改回 `0.8` 并重启。

### 5.5 检查任务结束后记忆清理

任务完成后执行：

```powershell
docker compose exec postgres psql -U postgres -d multiagent -c "SELECT count(*) FROM memory_chunks;"
```

验收标准：该 `task_id` 对应的记忆行数为 0，说明 `clear_task` 生命周期清理生效。

### 5.6 检查混合检索

当前单元测试覆盖了中文分词与 Top-3 排序：

```powershell
python -m pytest tests/unit/test_retriever.py -q
```

Top-3 召回 92% 的正式验证需要按方案文档第 12 节构造评测集，生产数据上线后统计。

## 6. 回归测试

```powershell
python -m pytest -q
```

预期结果：全部通过。

## 7. 停止服务

```powershell
docker compose down
```

如需保留数据卷，`down` 不会删除数据；需要彻底清理时使用 `docker compose down -v`。
