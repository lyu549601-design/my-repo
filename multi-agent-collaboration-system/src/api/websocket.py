"""WebSocket管理器 - 实时进度推送"""

import json
import asyncio
import structlog
from typing import Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from src.communication.event_bus import EventBus, Event

logger = structlog.get_logger()


class WebSocketManager:
    """WebSocket连接管理器
    
    职责：将EventBus的事件广播到WebSocket客户端
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}  # task_id -> [WebSocket]
        self._event_bus: EventBus | None = None
        self._subscribed = False

    async def connect(self, websocket: WebSocket, task_id: str) -> None:
        """接受WebSocket连接"""
        await websocket.accept()

        if task_id not in self._connections:
            self._connections[task_id] = []
        self._connections[task_id].append(websocket)

        logger.info("ws.connected", task_id=task_id, total_connections=len(self._connections[task_id]))

        # 订阅EventBus事件
        if not self._subscribed:
            self._subscribe_to_events()

    async def disconnect(self, websocket: WebSocket, task_id: str) -> None:
        """断开WebSocket连接"""
        if task_id in self._connections:
            self._connections[task_id].remove(websocket)
            if not self._connections[task_id]:
                del self._connections[task_id]
        
        logger.info("ws.disconnected", task_id=task_id)

    async def broadcast(self, task_id: str, message: dict[str, Any]) -> None:
        """向指定任务的所有连接广播消息"""
        connections = self._connections.get(task_id, [])
        if not connections:
            return

        message_json = json.dumps(message, ensure_ascii=False, default=str)
        
        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception:
                disconnected.append(websocket)

        # 清理断开的连接
        for ws in disconnected:
            connections.remove(ws)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        """向所有连接广播消息"""
        for task_id in list(self._connections.keys()):
            await self.broadcast(task_id, message)

    def _subscribe_to_events(self) -> None:
        """订阅EventBus事件"""
        self._subscribed = True

    async def handle_event(self, event: Event) -> None:
        """处理EventBus事件，推送到WebSocket"""
        message = {
            "type": event.event_type,
            "task_id": event.task_id,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
        }
        await self.broadcast(event.task_id, message)

    def get_connections_count(self, task_id: str | None = None) -> int:
        """获取连接数"""
        if task_id:
            return len(self._connections.get(task_id, []))
        return sum(len(conns) for conns in self._connections.values())


# 全局WebSocket管理器实例
websocket_manager = WebSocketManager()
