"""Redis分布式任务认领锁

职责分工：
- LangGraph Checkpointer: 负责图状态快照持久化，支持断点续传
- Redis: 负责分布式Worker认领子任务时的防并发竞争锁
"""

import structlog
from typing import Optional
from datetime import datetime

import redis.asyncio as aioredis

logger = structlog.get_logger()


class RedisTaskLock:
    """基于Redis的分布式任务认领锁"""

    # Lua脚本：原子性认领任务
    CLAIM_SCRIPT = """
    local task_key = KEYS[1]
    local agent_id = ARGV[1]
    local ttl = tonumber(ARGV[2])
    
    -- 检查是否已被认领
    local current_owner = redis.call('HGET', task_key, 'claimed_by')
    if current_owner and current_owner ~= '' then
        if current_owner == agent_id then
            -- 自己认领的，续期
            redis.call('EXPIRE', task_key, ttl)
            return 1
        end
        return 0  -- 被其他人认领
    end
    
    -- 原子性认领
    redis.call('HSET', task_key, 'claimed_by', agent_id)
    redis.call('HSET', task_key, 'claimed_at', ARGV[3])
    redis.call('EXPIRE', task_key, ttl)
    return 1
    """

    # Lua脚本：释放任务锁
    RELEASE_SCRIPT = """
    local task_key = KEYS[1]
    local agent_id = ARGV[1]
    
    local current_owner = redis.call('HGET', task_key, 'claimed_by')
    if current_owner == agent_id then
        redis.call('DEL', task_key)
        return 1
    end
    return 0
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    @classmethod
    def from_url(cls, redis_url: str) -> "RedisTaskLock":
        """从URL创建实例"""
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
        return cls(redis_client)

    async def try_claim(self, task_id: str, agent_id: str, ttl: int = 3600) -> bool:
        """尝试认领任务
        
        Args:
            task_id: 任务ID
            agent_id: Agent ID
            ttl: 锁过期时间（秒），默认1小时
            
        Returns:
            是否认领成功
        """
        try:
            result = await self.redis.eval(
                self.CLAIM_SCRIPT,
                1,
                f"task_lock:{task_id}",
                agent_id,
                str(ttl),
                datetime.utcnow().isoformat(),
            )
            success = result == 1
            
            if success:
                logger.info("redis_lock.claimed", task_id=task_id, agent_id=agent_id)
            else:
                logger.debug("redis_lock.already_claimed", task_id=task_id, agent_id=agent_id)
            
            return success
        except Exception as e:
            logger.error("redis_lock.claim_error", task_id=task_id, error=str(e))
            # 降级策略：Redis不可用时允许执行
            return True

    async def release(self, task_id: str, agent_id: str) -> bool:
        """释放任务锁
        
        Args:
            task_id: 任务ID
            agent_id: Agent ID
            
        Returns:
            是否释放成功
        """
        try:
            result = await self.redis.eval(
                self.RELEASE_SCRIPT,
                1,
                f"task_lock:{task_id}",
                agent_id,
            )
            success = result == 1
            
            if success:
                logger.info("redis_lock.released", task_id=task_id, agent_id=agent_id)
            
            return success
        except Exception as e:
            logger.error("redis_lock.release_error", task_id=task_id, error=str(e))
            return False

    async def get_owner(self, task_id: str) -> Optional[str]:
        """获取当前任务认领者
        
        Args:
            task_id: 任务ID
            
        Returns:
            认领者Agent ID，未认领返回None
        """
        try:
            return await self.redis.hget(f"task_lock:{task_id}", "claimed_by")
        except Exception as e:
            logger.error("redis_lock.get_owner_error", task_id=task_id, error=str(e))
            return None

    async def is_claimed(self, task_id: str) -> bool:
        """检查任务是否已被认领"""
        owner = await self.get_owner(task_id)
        return owner is not None and owner != ""

    async def renew(self, task_id: str, agent_id: str, ttl: int = 3600) -> bool:
        """续期任务锁
        
        Args:
            task_id: 任务ID
            agent_id: Agent ID
            ttl: 新的过期时间（秒）
            
        Returns:
            是否续期成功
        """
        try:
            current_owner = await self.get_owner(task_id)
            if current_owner == agent_id:
                await self.redis.expire(f"task_lock:{task_id}", ttl)
                logger.info("redis_lock.renewed", task_id=task_id, agent_id=agent_id)
                return True
            return False
        except Exception as e:
            logger.error("redis_lock.renew_error", task_id=task_id, error=str(e))
            return False

    async def close(self):
        """关闭Redis连接"""
        await self.redis.close()
