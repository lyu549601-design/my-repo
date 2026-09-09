"""事件总线 - 仅用于外部广播

职责边界：
- EventBus/WebSocket: 仅作为副产物，用于向前端实时广播任务进度与状态上报
- 不参与内部任务调度，内部流转完全由LangGraph StateGraph驱动
"""

import asyncio
import structlog
from typing import Callable, Any
from pydantic import BaseModel, Field
from datetime import datetime
from collections import defaultdict

logger = structlog.get_logger()


class Event(BaseModel):
    """事件定义"""
    event_type: str
    task_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EventBus:
    """事件总线，仅用于外部广播，不参与内部任务调度
    
    使用场景：
    - 向WebSocket前端广播任务进度
    - 向监控系统发送指标
    - 向日志系统发送事件
    
    不使用场景：
    - 内部任务调度（由LangGraph负责）
    - Agent间通信（由LangGraph状态流转负责）
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._event_history: list[Event] = []
        self._max_history: int = 1000

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数（异步）
        """
        self._subscribers[event_type].append(handler)
        logger.debug("event_bus.subscribed", event_type=event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """取消订阅"""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            logger.debug("event_bus.unsubscribed", event_type=event_type)

    async def publish(self, event: Event) -> None:
        """发布事件（广播给所有订阅者）
        
        Args:
            event: 事件对象
        """
        # 记录历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # 异步通知所有订阅者
        handlers = self._subscribers.get(event.event_type, [])
        if handlers:
            results = await asyncio.gather(
                *[self._safe_call_handler(handler, event) for handler in handlers],
                return_exceptions=True,
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "event_bus.handler_error",
                        event_type=event.event_type,
                        handler=str(handlers[i]),
                        error=str(result),
                    )

        logger.debug(
            "event_bus.published",
            event_type=event.event_type,
            task_id=event.task_id,
            handlers_count=len(handlers),
        )

    async def _safe_call_handler(self, handler: Callable, event: Event) -> Any:
        """安全调用处理器"""
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(event)
            else:
                return handler(event)
        except Exception as e:
            logger.error("event_bus.handler_exception", error=str(e))
            raise

    def get_history(
        self,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """获取事件历史
        
        Args:
            task_id: 过滤任务ID
            event_type: 过滤事件类型
            limit: 返回数量限制
            
        Returns:
            事件列表
        """
        events = self._event_history

        if task_id:
            events = [e for e in events if e.task_id == task_id]

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events[-limit:]

    def clear_history(self) -> None:
        """清空事件历史"""
        self._event_history.clear()

    def get_subscribers_count(self, event_type: str | None = None) -> int:
        """获取订阅者数量"""
        if event_type:
            return len(self._subscribers.get(event_type, []))
        return sum(len(handlers) for handlers in self._subscribers.values())
