"""MCP工具注册表 - 管理可用工具"""

import structlog
from typing import Any

logger = structlog.get_logger()


class MCPToolRegistry:
    """MCP工具注册表
    
    管理所有可用的MCP工具，提供工具查询和验证功能
    """

    # 默认工具定义
    DEFAULT_TOOLS = {
        "web_search": {
            "name": "web_search",
            "description": "网页实时搜索",
            "params": ["query", "num_results"],
            "server": "search",
        },
        "financial_api": {
            "name": "financial_api",
            "description": "金融数据查询（股票、财报）",
            "params": ["symbol", "data_type", "period"],
            "server": "financial",
        },
        "data_cleaner": {
            "name": "data_cleaner",
            "description": "数据清洗与格式化",
            "params": ["data", "rules"],
            "server": "cleaner",
        },
        "sentiment_analyzer": {
            "name": "sentiment_analyzer",
            "description": "舆情分析",
            "params": ["text", "language"],
            "server": "cleaner",
        },
        "chart_generator": {
            "name": "chart_generator",
            "description": "图表生成",
            "params": ["data", "chart_type", "options"],
            "server": "cleaner",
        },
        "patent_api": {
            "name": "patent_api",
            "description": "专利数据查询",
            "params": ["query", "filters"],
            "server": "search",
        },
    }

    def __init__(self, custom_tools: dict[str, dict[str, Any]] | None = None):
        """
        Args:
            custom_tools: 自定义工具定义，会覆盖默认工具
        """
        self.tools = {**self.DEFAULT_TOOLS}
        if custom_tools:
            self.tools.update(custom_tools)
        
        logger.info("registry.initialized", tools_count=len(self.tools))

    def register(self, tool_name: str, tool_config: dict[str, Any]) -> None:
        """注册新工具
        
        Args:
            tool_name: 工具名称
            tool_config: 工具配置
        """
        self.tools[tool_name] = tool_config
        logger.info("registry.tool_registered", tool=tool_name)

    def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info("registry.tool_unregistered", tool=tool_name)

    def is_available(self, tool_name: str) -> bool:
        """检查工具是否可用
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否可用
        """
        return tool_name in self.tools

    def get_tool(self, tool_name: str) -> dict[str, Any] | None:
        """获取工具配置
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具配置，不存在返回None
        """
        return self.tools.get(tool_name)

    def get_all_tools(self) -> dict[str, dict[str, Any]]:
        """获取所有工具"""
        return self.tools.copy()

    def get_tools_by_server(self, server_name: str) -> list[dict[str, Any]]:
        """按服务器获取工具
        
        Args:
            server_name: 服务器名称
            
        Returns:
            工具列表
        """
        return [
            tool for tool in self.tools.values()
            if tool.get("server") == server_name
        ]

    def validate_tool_params(self, tool_name: str, params: dict[str, Any]) -> bool:
        """验证工具参数
        
        Args:
            tool_name: 工具名称
            params: 参数
            
        Returns:
            是否有效
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False

        required_params = tool.get("params", [])
        return all(param in params for param in required_params)
