# API文档

## 基础信息

- Base URL: `http://localhost:8000`
- Content-Type: `application/json`
- WebSocket: `ws://localhost:8000/ws/reports/{task_id}`

## 接口列表

### 1. 创建研报任务

**POST** `/api/v1/reports`

提交一个研究主题，系统会自动分解任务并执行。

#### 请求参数

```json
{
  "topic": "2026年中国新能源汽车市场格局分析",
  "priority": "high",
  "constraints": {
    "max_subtasks": 8,
    "max_time": 1800
  }
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| topic | string | 是 | 研究主题，2-500字 |
| priority | string | 否 | 优先级：low/medium/high，默认medium |
| constraints | object | 否 | 约束条件 |

#### 响应

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-03-15T10:00:00Z",
  "estimated_minutes": 20,
  "websocket_url": "ws://localhost:8000/ws/reports/550e8400-e29b-41d4-a716-446655440000"
}
```

### 2. 查询任务状态

**GET** `/api/v1/reports/{task_id}`

查询研报任务的执行状态和进度。

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | string | 任务ID |

#### 响应

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "topic": "2026年中国新能源汽车市场格局分析",
  "status": "executing",
  "progress": 0.5,
  "current_level": 2,
  "total_levels": 5,
  "subtasks": [
    {
      "id": "task_0",
      "name": "行业概览",
      "status": "completed",
      "level": 0,
      "retry_count": 0,
      "error": null
    },
    {
      "id": "task_1",
      "name": "市场规模",
      "status": "executing",
      "level": 1,
      "retry_count": 0,
      "error": null
    }
  ],
  "degraded_tasks": [],
  "error": null,
  "result": null,
  "created_at": "2026-03-15T10:00:00Z",
  "updated_at": "2026-03-15T10:05:00Z"
}
```

### 3. 列出所有任务

**GET** `/api/v1/reports`

列出所有研报任务。

#### 响应

```json
{
  "tasks": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "topic": "2026年中国新能源汽车市场格局分析",
      "status": "completed",
      "created_at": "2026-03-15T10:00:00Z"
    }
  ],
  "total": 1
}
```

### 4. 删除任务

**DELETE** `/api/v1/reports/{task_id}`

删除指定的研报任务。

#### 响应

```json
{
  "message": "任务已删除"
}
```

### 5. 健康检查

**GET** `/health`

检查服务健康状态。

#### 响应

```json
{
  "status": "healthy"
}
```

## WebSocket接口

### 连接

```
ws://localhost:8000/ws/reports/{task_id}
```

### 消息格式

```json
{
  "type": "progress",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "level": 1,
    "completed": ["task_0"],
    "failed": []
  },
  "timestamp": "2026-03-15T10:05:00Z"
}
```

### 事件类型

| 类型 | 说明 |
|------|------|
| plan_created | 任务规划完成 |
| level_executed | 层级执行完成 |
| level_reviewed | 层级审核完成 |
| report_completed | 研报生成完成 |
| report_failed | 研报生成失败 |

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 任务不存在 |
| 500 | 服务器内部错误 |

## 示例

### curl

```bash
# 创建任务
curl -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '{"topic": "2026年中国新能源汽车市场格局分析", "priority": "high"}'

# 查询状态
curl http://localhost:8000/api/v1/reports/{task_id}

# 列出所有任务
curl http://localhost:8000/api/v1/reports
```

### Python

```python
import httpx
import asyncio

async def create_report():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/reports",
            json={
                "topic": "2026年中国新能源汽车市场格局分析",
                "priority": "high"
            }
        )
        return response.json()

# 运行
result = asyncio.run(create_report())
print(result)
```
