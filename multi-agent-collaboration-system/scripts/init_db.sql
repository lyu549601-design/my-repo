-- 数据库初始化脚本

-- 创建数据库（如果不存在）
-- CREATE DATABASE multiagent;

-- 连接到数据库
\c multiagent;

-- 创建任务表
CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(36) PRIMARY KEY,
    topic TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    plan JSONB,
    subtasks JSONB,
    execution_levels JSONB,
    current_level INTEGER DEFAULT 0,
    completed_results JSONB DEFAULT '{}',
    final_result JSONB,
    error TEXT,
    degraded_tasks JSONB DEFAULT '[]',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);

-- 创建事件表
CREATE TABLE IF NOT EXISTS events (
    event_id SERIAL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
