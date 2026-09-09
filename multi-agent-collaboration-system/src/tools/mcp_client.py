"""MCP协议客户端 - 负责与各MCP Server通信

MCP调用流程：
1. Executor Agent 构造 MCPRequest
2. MCPClient.call() 发送请求到对应的 MCP Server
3. MCP Server 执行工具逻辑，返回 MCPResponse
4. Executor Agent 处理结果或异常
"""

import time
import structlog
from typing import Any

import httpx

from src.models.task import MCPRequest, MCPResponse, MCPErrorCode

logger = structlog.get_logger()


class MCPToolError(Exception):
    """MCP工具调用异常"""

    def __init__(self, tool: str, error_code: MCPErrorCode, message: str):
        self.tool = tool
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{tool}] {error_code}: {message}")


class MCPConnectionError(MCPToolError):
    """MCP连接异常"""
    pass


class MCPTimeoutError(MCPToolError):
    """MCP超时异常"""
    pass


class MCPClient:
    """MCP协议客户端，负责与各MCP Server通信
    
    调用流程：
    1. 检查工具是否存在
    2. 发送请求到对应的MCP Server
    3. 处理响应或异常
    4. 返回MCPResponse
    
    异常处理：
    - 连接失败：MCPConnectionError，可重试
    - 超时：MCPTimeoutError，可重试
    - 工具不存在：MCPToolError，不可重试
    - 执行错误：MCPToolError，视情况重试
    """

    def __init__(self, server_configs: dict[str, dict[str, str]]):
        """
        Args:
            server_configs: MCP Server配置映射
                {
                    "web_search": {"url": "http://search-mcp:8080"},
                    "financial_api": {"url": "http://finance-mcp:8080"},
                    ...
                }
        """
        self.server_configs = server_configs
        self.clients: dict[str, httpx.AsyncClient] = {}

    async def initialize(self) -> None:
        """初始化HTTP客户端连接池"""
        for tool_name, config in self.server_configs.items():
            self.clients[tool_name] = httpx.AsyncClient(
                base_url=config["url"],
                headers={
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                trust_env=False,
            )
            logger.info("mcp_client.initialized", tool=tool_name, url=config["url"])

    async def call(self, request: MCPRequest) -> MCPResponse:
        """调用MCP Server执行工具
        
        Args:
            request: MCP请求
            
        Returns:
            MCP响应
            
        Raises:
            MCPConnectionError: 连接失败
            MCPTimeoutError: 调用超时
            MCPToolError: 工具调用错误
        """
        # 1. 检查工具是否存在
        if request.tool not in self.clients:
            return MCPResponse(
                success=False,
                error_code=MCPErrorCode.TOOL_NOT_FOUND.value,
                error_message=f"工具 {request.tool} 未注册",
            )

        client = self.clients[request.tool]
        start_time = time.time()

        try:
            logger.info(
                "mcp_client.call_start",
                tool=request.tool,
                request_id=request.request_id,
            )

            # 2. 发送请求到MCP Server
            response = await client.post(
                "/execute",
                json={
                    "tool": request.tool,
                    "params": request.params,
                    "request_id": request.request_id,
                },
                timeout=request.timeout,
            )

            latency = (time.time() - start_time) * 1000

            # 3. 处理响应
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "mcp_client.call_success",
                    tool=request.tool,
                    latency_ms=latency,
                )
                return MCPResponse(
                    success=True,
                    result=data.get("result"),
                    latency_ms=latency,
                )
            elif response.status_code == 404:
                return MCPResponse(
                    success=False,
                    error_code=MCPErrorCode.TOOL_NOT_FOUND.value,
                    error_message=f"工具 {request.tool} 在MCP Server上不存在",
                    latency_ms=latency,
                )
            elif response.status_code == 429:
                return MCPResponse(
                    success=False,
                    error_code=MCPErrorCode.RATE_LIMITED.value,
                    error_message="MCP Server限流，请稍后重试",
                    latency_ms=latency,
                )
            else:
                return MCPResponse(
                    success=False,
                    error_code=MCPErrorCode.EXECUTION_ERROR.value,
                    error_message=f"MCP Server返回错误: {response.status_code}",
                    latency_ms=latency,
                )

        except httpx.ConnectError as e:
            raise MCPConnectionError(
                tool=request.tool,
                error_code=MCPErrorCode.CONNECTION_FAILED,
                message=f"无法连接到MCP Server: {str(e)}",
            )
        except httpx.TimeoutException as e:
            raise MCPTimeoutError(
                tool=request.tool,
                error_code=MCPErrorCode.TIMEOUT,
                message=f"MCP工具调用超时: {str(e)}",
            )
        except Exception as e:
            raise MCPToolError(
                tool=request.tool,
                error_code=MCPErrorCode.EXECUTION_ERROR,
                message=f"未知错误: {str(e)}",
            )

    async def close(self) -> None:
        """关闭所有连接"""
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()
        logger.info("mcp_client.closed")

    def get_available_tools(self) -> list[str]:
        """获取可用工具列表"""
        return list(self.clients.keys())

    def is_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        return tool_name in self.clients
